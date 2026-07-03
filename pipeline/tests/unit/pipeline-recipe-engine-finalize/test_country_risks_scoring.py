"""
Unit tests for country_risks.py scoring logic (#375, #377 V1.9.1 Fix C).

Covers:
- severity_weight lookup (known + unknown categories)
- zscore_per_country (multi-pred countries, single-pred passthrough)
- rank_fusion (RRF with and without missing keys)
- risk_tier_label (V1.9.1 3-layer hybrid: Layer 1 regular, Layer 2 crisis,
  Layer 3 composite promotion)
- load_scoring_config (file present + fallback to DEFAULT_SCORING_CONFIG)
- _to_int_safe / _to_float_safe robustness
- compute_country_risks end-to-end with a stubbed Athena
- write_country_risks_json S3 call (assert via mock)
"""

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Load the module directly from the Lambda dir (no package install)
_MODULE_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "lambdas"
    / "pipeline-recipe-engine-finalize"
    / "country_risks.py"
)
_spec = importlib.util.spec_from_file_location("country_risks", _MODULE_PATH)
country_risks = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(country_risks)


def _cat(salience, severity):
    """Shorthand for category_scores dict entries."""
    return {"salience_score": salience, "severity_tier": severity}


# ─── severity_weight ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "category,expected",
    [
        ("civil_war_and_insurgency", 1.0),
        ("interstate_war", 1.0),
        ("currency_crisis", 0.8),
        ("elections_and_voting", 0.6),
        ("government_formation", 0.4),
        ("environmental_policy", 0.2),
        ("infrastructure_project", 0.05),
        ("some_future_category_not_yet_classified", 0.3),  # default
        ("", 0.3),
    ],
)
def test_severity_weight(category, expected):
    assert country_risks.severity_weight(category) == expected


# ─── zscore_per_country ───────────────────────────────────────────────


def test_zscore_per_country_multi_pred():
    preds = {
        (1, "a"): 10.0,
        (1, "b"): 20.0,
        (1, "c"): 30.0,
        (2, "a"): 5.0,
        (2, "b"): 15.0,
    }
    out = country_risks.zscore_per_country(preds)
    assert out[(1, "b")] == pytest.approx(0.0, abs=1e-6)
    assert out[(1, "a")] < 0 and out[(1, "c")] > 0
    assert out[(2, "a")] == pytest.approx(-1.0, abs=1e-6)
    assert out[(2, "b")] == pytest.approx(1.0, abs=1e-6)


def test_zscore_per_country_single_pred_passthrough():
    preds = {(99, "only"): 42.5}
    out = country_risks.zscore_per_country(preds)
    assert out == {(99, "only"): 42.5}


def test_zscore_per_country_empty():
    assert country_risks.zscore_per_country({}) == {}


def test_zscore_per_country_all_equal_uses_floor_std():
    preds = {(1, "a"): 5.0, (1, "b"): 5.0, (1, "c"): 5.0}
    out = country_risks.zscore_per_country(preds)
    for v in out.values():
        assert abs(v) < 1e-3


# ─── rank_fusion ──────────────────────────────────────────────────────


def test_rank_fusion_both_sources():
    recipe = {(1, "a"): 10.0, (1, "b"): 5.0}
    persist = {(1, "a"): 1.0, (1, "b"): 2.0}
    out = country_risks.rank_fusion(recipe, persist)
    assert (1, "a") in out and (1, "b") in out
    assert out[(1, "a")] == pytest.approx(out[(1, "b")])


def test_rank_fusion_missing_in_one_source():
    recipe = {(1, "a"): 10.0, (1, "b"): 5.0}
    persist = {(1, "a"): 1.0}
    out = country_risks.rank_fusion(recipe, persist)
    assert (1, "a") in out and (1, "b") in out
    assert out[(1, "a")] > out[(1, "b")]


def test_rank_fusion_empty():
    assert country_risks.rank_fusion({}, {}) == {}


# ─── risk_tier_label — V1.9.1 Layer 1/2 stratified thresholds ───────


@pytest.mark.parametrize(
    "salience,severity,expected",
    [
        # Layer 2: crisis (sev >= 1.0)
        (1.4, 1.0, "HIGH"),  # at crisis HIGH threshold
        (1.5, 1.0, "HIGH"),  # above crisis HIGH
        (1.0, 1.0, "MODERATE"),  # at crisis MODERATE floor
        (0.9, 1.0, "INDICATIVE"),  # below crisis MODERATE
        # Layer 1: regular (sev < 1.0) — HIGH raised to 2.0
        (2.0, 0.6, "HIGH"),  # at regular HIGH threshold (NEW: 2.0)
        (2.1, 0.6, "HIGH"),  # above regular HIGH
        (1.625, 0.6, "MODERATE"),  # prior V1.8.1 HIGH cut now MODERATE
        (1.5, 0.6, "MODERATE"),  # regular MODERATE
        (1.3, 0.6, "MODERATE"),  # at regular MODERATE floor
        (1.29, 0.6, "INDICATIVE"),  # just below regular MODERATE
        (0.0, 0.3, "INDICATIVE"),  # floor
    ],
)
def test_risk_tier_label_stratified(salience, severity, expected):
    """Layer 1/2: stratified thresholds on top category only (no composite)."""
    assert country_risks.risk_tier_label([_cat(salience, severity)]) == expected


def test_risk_tier_label_empty_returns_indicative():
    assert country_risks.risk_tier_label([]) == "INDICATIVE"


def test_risk_tier_label_crisis_preserves_ukraine_iran():
    """Regression guard (#339): Ukraine/Iran around salience=1.17 in a crisis
    category must land in MODERATE (not INDICATIVE)."""
    assert country_risks.risk_tier_label([_cat(1.17, 1.0)]) == "MODERATE"


# ─── risk_tier_label — V1.9.1 Layer 3 composite promotion ───────────


def test_risk_tier_label_venezuela_composite_promotion():
    """Venezuela-like: 3 categories above floor, severities [0.6, 0.8, 0.4].
    At least one (0.8) clears the severity gate → HIGH via composite."""
    cats = [
        _cat(1.66, 0.6),
        _cat(1.45, 0.8),
        _cat(1.35, 0.4),
    ]
    assert country_risks.risk_tier_label(cats) == "HIGH"


def test_risk_tier_label_denmark_no_promotion():
    """Denmark-like: 1 category above floor at 1.67 with sev 0.6, rest below.
    Composite doesn't fire (only 1 above floor); top below REGULAR_HIGH 2.0
    → INDICATIVE? No — top_salience 1.67 >= REGULAR_MODERATE 1.3 → MODERATE.
    Spec says 'INDICATIVE' but that conflicts with Layer 1/2 moderate floor.
    Re-reading spec: 'top below REGULAR_HIGH 2.0, composite doesn't fire' →
    The spec literally says INDICATIVE; but 1.67 still sits above the 1.3
    MODERATE floor. Using the layered logic as defined, this is MODERATE.
    Test the MODERATE outcome (the correct behavior per the layered spec)."""
    cats = [
        _cat(1.67, 0.6),
        _cat(1.1, 0.4),
        _cat(0.9, 0.2),
    ]
    # Top 1.67 < REGULAR_HIGH 2.0, >= REGULAR_MODERATE 1.3 → MODERATE.
    # Composite: only 1 cat >= 1.3 floor → no promotion.
    assert country_risks.risk_tier_label(cats) == "MODERATE"


def test_risk_tier_label_cape_verde_shape():
    """Cape Verde-like: same shape as Denmark — single elections spike.
    Must NOT reach HIGH (this is the #376 face-validity bug being fixed)."""
    cats = [
        _cat(1.67, 0.6),  # elections_and_voting-like
        _cat(0.9, 0.4),
        _cat(0.5, 0.2),
    ]
    assert country_risks.risk_tier_label(cats) != "HIGH"


def test_risk_tier_label_syria_crisis_layer2():
    """Syria-like: top at 1.58 with severity 1.0 → HIGH via Layer 2 (crisis)."""
    cats = [_cat(1.58, 1.0), _cat(1.2, 0.8)]
    assert country_risks.risk_tier_label(cats) == "HIGH"


def test_risk_tier_label_multi_moderate_no_severity_gate():
    """>=2 categories above 1.3 floor but NONE has severity >= 0.8 — must NOT
    promote via composite. Stays at Layer 1/2 outcome."""
    cats = [
        _cat(1.5, 0.6),
        _cat(1.4, 0.6),
        _cat(1.35, 0.4),
    ]
    # Composite: 3 above floor, but max severity 0.6 < 0.8 → no promotion.
    # Layer 1/2: top 1.5 < REGULAR_HIGH 2.0, >= 1.3 → MODERATE.
    assert country_risks.risk_tier_label(cats) == "MODERATE"


def test_risk_tier_label_composite_disabled_via_config():
    """If composite_rule.enabled is False, Venezuela-like case falls to
    Layer 1/2 only (top 1.66, sev 0.6 < 1.0, below REGULAR_HIGH 2.0 → MODERATE)."""
    cfg = {
        "thresholds": {
            "CRISIS_HIGH": 1.4,
            "REGULAR_HIGH": 2.0,
            "CRISIS_MODERATE": 1.0,
            "REGULAR_MODERATE": 1.3,
        },
        "composite_rule": {"enabled": False},
    }
    cats = [_cat(1.66, 0.6), _cat(1.45, 0.8), _cat(1.35, 0.4)]
    assert country_risks.risk_tier_label(cats, cfg) == "MODERATE"


# ─── load_scoring_config ─────────────────────────────────────────────


def test_load_scoring_config_missing_file_falls_back():
    cfg = country_risks.load_scoring_config(path="/nonexistent/path/missing.json")
    # When all candidates fail (path + no env + missing repo-relative file in
    # some execution contexts), DEFAULT_SCORING_CONFIG is returned.
    # Note: repo-relative candidate may succeed; in that case the loaded
    # config has the same structure as DEFAULT. Check structure either way.
    assert "thresholds" in cfg
    assert cfg["thresholds"]["REGULAR_HIGH"] == 2.0
    assert cfg["thresholds"]["CRISIS_HIGH"] == 1.4
    assert cfg["composite_rule"]["min_salience_floor"] == 1.3


def test_load_scoring_config_default_when_no_file():
    """DEFAULT_SCORING_CONFIG is returned when no path resolves."""
    # Test the fallback object directly (no file I/O).
    cfg = country_risks.DEFAULT_SCORING_CONFIG
    assert cfg["thresholds"]["REGULAR_HIGH"] == 2.0
    assert cfg["thresholds"]["CRISIS_HIGH"] == 1.4
    assert cfg["thresholds"]["REGULAR_MODERATE"] == 1.3
    assert cfg["thresholds"]["CRISIS_MODERATE"] == 1.0
    assert cfg["composite_rule"]["enabled"] is True
    assert cfg["composite_rule"]["min_categories_above_salience"] == 2
    assert cfg["composite_rule"]["min_salience_floor"] == 1.3
    assert cfg["composite_rule"]["min_severity_for_at_least_one"] == 0.8


def test_load_scoring_config_reads_real_v191_json():
    """Explicit path to the real V1.9.1.json loads with expected values.

    Skips cleanly when qgi-data isn't checked out alongside qgi-pipeline
    (e.g. single-repo CI job). DEFAULT_SCORING_CONFIG test below covers the
    embedded-fallback path; this test covers real-file loading when the
    multi-repo workspace is present.
    """
    # Resolve from test file location: qgi-pipeline/tests/unit/.../test_*.py
    # up 4 levels to qgi-6.0, then into qgi-data/scoring/V1.9.1.json.
    real_path = Path(__file__).resolve().parent.parent.parent.parent.parent / "qgi-data" / "scoring" / "V1.9.1.json"
    if not real_path.exists():
        pytest.skip(
            f"qgi-data not checked out alongside qgi-pipeline "
            f"(tried {real_path}); skipping cross-repo config-load test. "
            f"DEFAULT_SCORING_CONFIG fallback is covered separately."
        )
    cfg = country_risks.load_scoring_config(path=str(real_path))
    assert cfg["_meta"]["scoring_version"] == "V1.9.1"
    assert cfg["thresholds"]["REGULAR_HIGH"] == 2.0
    assert cfg["thresholds"]["CRISIS_HIGH"] == 1.4
    assert cfg["composite_rule"]["enabled"] is True


# ─── coerce helpers ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "inp,expected",
    [
        (None, None),
        ("", None),
        ("abc", None),
        ("5", 5),
        ("5.7", 5),
        ("100", 100),
        (42, 42),
    ],
)
def test_to_int_safe(inp, expected):
    assert country_risks._to_int_safe(inp) == expected


@pytest.mark.parametrize(
    "inp,expected",
    [
        (None, None),
        ("", None),
        ("abc", None),
        ("5", 5.0),
        ("5.7", 5.7),
        ("1e3", 1000.0),
    ],
)
def test_to_float_safe(inp, expected):
    assert country_risks._to_float_safe(inp) == expected


# ─── compute_country_risks integration (stubbed Athena) ──────────────


class _StubAthena:
    def __init__(self, canned):
        self.canned = canned
        self.queries = []
        self._next_id = 0

    def run(self, sql):
        self.queries.append(sql)
        self._next_id += 1
        return f"qid-{self._next_id}"

    def rows(self, query_id):
        idx = int(query_id.split("-")[1]) - 1
        sql = self.queries[idx]
        for keyword, rows in self.canned.items():
            if keyword in sql:
                return rows
        return []


def test_compute_country_risks_minimal():
    canned = {
        "FROM qgi_data.countries": [
            {"id": "1", "name_1": "Testland", "alpha_2": "TL"},
        ],
        "WHERE category_normalized IS NOT NULL GROUP BY country_id": [
            {"country_id": "1", "category_normalized": "elections_and_voting", "y": "2024"},
        ],
        "WHERE year BETWEEN 2023 AND 2025": [
            {"country_id": "1", "category_normalized": "elections_and_voting", "c": "3"},
        ],
        "FROM qgi_data.scdis": [
            {"country_a_id": "1", "p": "10"},
        ],
        "FROM qgi_data.recipes": [
            {"country_a_id": "1", "event_category": "elections_and_voting", "c": "5", "a": "0.85", "i": "4"},
        ],
    }
    athena = _StubAthena(canned)
    payload = country_risks.compute_country_risks(athena.run, athena.rows)

    assert payload["version"] == "V1.9.1"
    assert payload["total_countries"] == 1
    assert "1" in payload["countries"]
    entry = payload["countries"]["1"]
    assert entry["name"] == "Testland"
    assert entry["alpha_2"] == "TL"
    assert entry["curated"] is True
    assert "S" in entry["tiers"]
    s_cats = entry["tiers"]["S"]["top_categories"]
    assert len(s_cats) == 1
    assert s_cats[0]["category"] == "elections_and_voting"
    assert s_cats[0]["severity_tier"] == 0.6
    assert entry["overall_risk_tier"] in {"HIGH", "MODERATE", "INDICATIVE"}


def test_compute_country_risks_empty_returns_skeleton():
    athena = _StubAthena({})
    payload = country_risks.compute_country_risks(athena.run, athena.rows)
    assert payload["total_countries"] == 0
    assert payload["countries"] == {}
    assert payload["version"] == "V1.9.1"
    assert "S" in payload["tiers"] and "XL" in payload["tiers"]


def test_compute_country_risks_uncurated_country_flagged():
    canned = {
        "FROM qgi_data.countries": [
            {"id": "500", "name_1": "Neverland", "alpha_2": "NL"},
        ],
        "WHERE category_normalized IS NOT NULL GROUP BY country_id": [],
        "WHERE year BETWEEN 2023 AND 2025": [],
        "FROM qgi_data.scdis": [],
        "FROM qgi_data.recipes": [],
    }
    athena = _StubAthena(canned)
    payload = country_risks.compute_country_risks(athena.run, athena.rows)
    assert payload["total_countries"] == 0


# ─── write_country_risks_json (S3 mock) ───────────────────────────────


def test_write_country_risks_json_calls_s3():
    athena = _StubAthena({})
    s3 = MagicMock()
    summary = country_risks.write_country_risks_json(athena.run, athena.rows, s3, "test-bucket")
    s3.put_object.assert_called_once()
    kwargs = s3.put_object.call_args.kwargs
    assert kwargs["Bucket"] == "test-bucket"
    assert kwargs["Key"] == "dashboard/country-risks.json"
    assert kwargs["ContentType"] == "application/json"
    parsed = json.loads(kwargs["Body"].decode("utf-8"))
    assert parsed["version"] == "V1.9.1"
    assert summary["countries"] == 0
    assert summary["curated"] == len(country_risks.CURATED_IDS)
    assert "bytes" in summary and summary["bytes"] > 0
