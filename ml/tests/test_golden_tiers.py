"""Golden test set for country-tier regression guard (#379).

Loads the live `country-risks.json` artefact and asserts every canonical
country's `overall_risk_tier` matches the human-adjudicated expectation
in `country_tier_expectations.json`.

Skips cleanly (not fails) if the artefact isn't readable locally — that
path is covered by CI against the S3 copy post-pipeline-run.

Sign-off on any expectation change: Marcus (Methodology 1). Quarterly
review cadence per #379.
"""
from __future__ import annotations

import json
import os
import pathlib

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
EXPECTATIONS_PATH = pathlib.Path(__file__).parent / "golden" / "country_tier_expectations.json"

# Candidate locations for the live country-risks.json artefact, in priority order.
# In CI: expect a downloaded copy at QGI_COUNTRY_RISKS_PATH.
# Locally: a generated file in the ml working dir.
ARTEFACT_CANDIDATES = [
    os.environ.get("QGI_COUNTRY_RISKS_PATH"),
    REPO_ROOT / "qgi-ml" / "country-risks.json",
    REPO_ROOT / "qgi-frontend" / "data" / "country-risks.json",
    REPO_ROOT / ".tmp" / "country-risks.json",
]


def _load_country_risks():
    for candidate in ARTEFACT_CANDIDATES:
        if not candidate:
            continue
        p = pathlib.Path(candidate)
        if p.exists() and p.is_file():
            try:
                with open(p) as f:
                    return json.load(f), str(p)
            except (json.JSONDecodeError, OSError):
                continue
    return None, None


def _load_expectations():
    with open(EXPECTATIONS_PATH) as f:
        return json.load(f)["expectations"]


# ─── Module-level fixtures ───────────────────────────────────────────
MIN_SCORING_VERSION = "V1.9.1"  # golden set authored against Fix C


def _version_meets_minimum(version_str, minimum=MIN_SCORING_VERSION):
    """Crude version comparator for QGI scoring strings like 'V1.9.1', 'V1.8.1'."""
    if not version_str or not version_str.startswith("V"):
        return False
    def tupleize(s):
        return tuple(int(x) for x in s.lstrip("V").split(".") if x.isdigit())
    try:
        return tupleize(version_str) >= tupleize(minimum)
    except (ValueError, AttributeError):
        return False


@pytest.fixture(scope="module")
def country_risks():
    data, source = _load_country_risks()
    if data is None:
        pytest.skip(
            "country-risks.json not found locally. Run the scoring pipeline or "
            "export QGI_COUNTRY_RISKS_PATH=/path/to/country-risks.json. "
            f"Checked: {[str(c) for c in ARTEFACT_CANDIDATES if c]}"
        )
    version = data.get("version", "")
    if not _version_meets_minimum(version):
        pytest.skip(
            f"country-risks.json at {source} is scoring version {version!r} "
            f"which is pre-{MIN_SCORING_VERSION}. Golden expectations are "
            f"calibrated for V1.9.1 Fix C; failures against older data are "
            f"expected and not actionable. Run the V1.9.1 pipeline and re-test."
        )
    return data, source


@pytest.fixture(scope="module")
def expectations():
    return _load_expectations()


# ─── The actual test ─────────────────────────────────────────────────
def _find_country_by_key(risks_data, country_key, alpha_2):
    """Match a country record by slug (e.g., 'cape_verde') or alpha_2 code."""
    countries = risks_data.get("countries", {})
    target_name_lc = country_key.replace("_", " ").lower()
    for cid, entry in countries.items():
        name_lc = entry.get("name", "").lower()
        if entry.get("alpha_2", "").upper() == alpha_2.upper():
            return entry
        if name_lc == target_name_lc:
            return entry
    return None


@pytest.mark.parametrize("country_key", sorted(_load_expectations().keys()))
def test_golden_country_tier(country_risks, expectations, country_key):
    data, _source = country_risks
    spec = expectations[country_key]
    expected = spec["expected_tier"]
    allowed = set(expected) if isinstance(expected, list) else {expected}

    entry = _find_country_by_key(data, country_key, spec["alpha_2"])
    if entry is None:
        pytest.skip(
            f"Country '{country_key}' (alpha_2={spec['alpha_2']}) not in "
            f"country-risks.json — out-of-scope for this scoring run."
        )

    actual = entry.get("overall_risk_tier")
    assert actual in allowed, (
        f"Golden-tier regression: {country_key} "
        f"(alpha_2={spec['alpha_2']}) expected tier in {sorted(allowed)}, "
        f"got {actual!r}. Rationale: {spec['rationale']}"
    )


# ─── Sanity ──────────────────────────────────────────────────────────
def test_expectations_file_is_valid():
    exp = _load_expectations()
    assert len(exp) >= 15, f"Golden set must have ≥15 countries, has {len(exp)}"
    for key, spec in exp.items():
        expected = spec["expected_tier"]
        labels = expected if isinstance(expected, list) else [expected]
        for label in labels:
            assert label in {"HIGH", "MODERATE", "INDICATIVE"}, (
                f"Invalid expected tier {label!r} for {key}"
            )
        assert "rationale" in spec and spec["rationale"]
        assert "alpha_2" in spec and len(spec["alpha_2"]) == 2
