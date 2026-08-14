"""Unit tests for generate_country_risks.py pure functions.

Covers:
  - zscore_per_country()
  - rank_fusion()
  - risk_tier_label()  (V1.9.1 Fix C)
  - severity_weight()
  - load_severity_tiers()
  - load_scoring_config()

No AWS calls. Deterministic, offline-only.

#373 script test coverage audit.
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import sys

import pytest

# ---------------------------------------------------------------------------
# Import the module under test. The module runs load_severity_tiers() at
# import time (module-level SEVERITY_TIERS = load_severity_tiers()). Point
# QGI_SEVERITY_TIERS_PATH at the real file so import succeeds cleanly.
# ---------------------------------------------------------------------------
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SEVERITY_TIERS_PATH = REPO_ROOT / "data-tools" / "reference" / "category_severity_tiers.json"
SCORING_CONFIG_PATH = REPO_ROOT / "data-tools" / "scoring" / "V1.9.1.json"

# Set env vars before importing so the module-level call picks them up.
if SEVERITY_TIERS_PATH.exists():
    os.environ.setdefault("QGI_SEVERITY_TIERS_PATH", str(SEVERITY_TIERS_PATH))
if SCORING_CONFIG_PATH.exists():
    os.environ.setdefault("QGI_SCORING_CONFIG_PATH", str(SCORING_CONFIG_PATH))

# Add the scripts/ directory to sys.path so the bare module is importable.
SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import generate_country_risks as gcr  # noqa: E402  (after sys.path patch)

# Convenience alias for the default config used throughout.
DEFAULT_CFG = gcr.DEFAULT_SCORING_CONFIG


# ===========================================================================
# Helpers
# ===========================================================================

def _approx(val, expected, tol=1e-9):
    return abs(val - expected) < tol


# ===========================================================================
# zscore_per_country()
# ===========================================================================

class TestZscorePerCountry:

    def test_single_country_three_categories_mean_zero_std_one(self):
        """Z-scores for one country should have mean 0 and std 1."""
        preds = {
            (1, "civil_war_and_insurgency"): 3.0,
            (1, "elections_and_voting"): 5.0,
            (1, "economic_reform"): 1.0,
        }
        result = gcr.zscore_per_country(preds)
        vals = list(result.values())
        mean = sum(vals) / len(vals)
        std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
        assert abs(mean) < 1e-9, f"Expected mean~0, got {mean}"
        assert abs(std - 1.0) < 1e-9, f"Expected std~1, got {std}"

    def test_single_country_three_categories_values(self):
        """Verify exact z-score values for a known distribution."""
        preds = {
            (1, "civil_war_and_insurgency"): 3.0,
            (1, "elections_and_voting"): 5.0,
            (1, "economic_reform"): 1.0,
        }
        result = gcr.zscore_per_country(preds)
        # mean=3, std=math.sqrt(8/3)
        mean = 3.0
        std = (8 / 3) ** 0.5
        assert _approx(result[(1, "civil_war_and_insurgency")], (3.0 - mean) / std)
        assert _approx(result[(1, "elections_and_voting")], (5.0 - mean) / std)
        assert _approx(result[(1, "economic_reform")], (1.0 - mean) / std)

    def test_single_category_returned_unchanged(self):
        """A single (country, category) pair should be returned as-is (len < 2 branch)."""
        preds = {(7, "mass_protest"): 2.5}
        result = gcr.zscore_per_country(preds)
        assert result == {(7, "mass_protest"): 2.5}

    def test_multiple_countries_normalized_independently(self):
        """Two countries must each normalize to mean=0, std=1 independently."""
        preds = {
            (1, "civil_war_and_insurgency"): 10.0,
            (1, "elections_and_voting"): 20.0,
            (2, "civil_war_and_insurgency"): 1.0,
            (2, "elections_and_voting"): 3.0,
        }
        result = gcr.zscore_per_country(preds)
        c1_vals = [result[(1, "civil_war_and_insurgency")], result[(1, "elections_and_voting")]]
        c2_vals = [result[(2, "civil_war_and_insurgency")], result[(2, "elections_and_voting")]]
        for vals, name in [(c1_vals, "country 1"), (c2_vals, "country 2")]:
            m = sum(vals) / len(vals)
            s = (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5
            assert abs(m) < 1e-9, f"{name} mean ~0 expected, got {m}"
            assert abs(s - 1.0) < 1e-9, f"{name} std ~1 expected, got {s}"

    def test_all_equal_within_country_no_divzero(self):
        """All-equal scores: std is clamped to 1e-6, all z-scores should be ~0."""
        preds = {
            (3, "economic_reform"): 4.0,
            (3, "elections_and_voting"): 4.0,
            (3, "mass_protest"): 4.0,
        }
        result = gcr.zscore_per_country(preds)
        for z in result.values():
            assert abs(z) < 1e-3, f"Expected z~0 for equal scores, got {z}"

    def test_two_countries_no_cross_contamination(self):
        """One country's z-score should not influence the other's raw scores."""
        preds = {
            (10, "civil_war_and_insurgency"): 100.0,
            (10, "elections_and_voting"): 200.0,
            (11, "civil_war_and_insurgency"): 0.1,
            (11, "elections_and_voting"): 0.2,
        }
        result = gcr.zscore_per_country(preds)
        # Both countries have 2 symmetric values; z-scores should be ±1 or ±something.
        # Key property: sign matches relative magnitude within each country.
        assert result[(10, "elections_and_voting")] > result[(10, "civil_war_and_insurgency")]
        assert result[(11, "elections_and_voting")] > result[(11, "civil_war_and_insurgency")]
        # The magnitudes between the two countries must NOT be equal to each other's raw
        # scores — confirm country 10 and 11 have the same z-scores (both 2-element symmetric)
        assert abs(result[(10, "elections_and_voting")] - result[(11, "elections_and_voting")]) < 1e-9

    def test_empty_input(self):
        """Empty preds must return empty dict."""
        assert gcr.zscore_per_country({}) == {}


# ===========================================================================
# rank_fusion()
# ===========================================================================

class TestRankFusion:

    def test_perfect_overlap_rrf_math(self):
        """Both dicts have same 2 keys; verify exact RRF formula with k=60."""
        recipe = {(1, "a"): 10.0, (1, "b"): 5.0}
        persist = {(1, "a"): 3.0, (1, "b"): 1.0}
        result = gcr.rank_fusion(recipe, persist, k=60)
        # (1, "a") has recipe_rank=1, persist_rank=1
        expected_a = 1 / (60 + 1) + 1 / (60 + 1)
        # (1, "b") has recipe_rank=2, persist_rank=2
        expected_b = 1 / (60 + 2) + 1 / (60 + 2)
        assert _approx(result[(1, "a")], expected_a)
        assert _approx(result[(1, "b")], expected_b)

    def test_recipe_only_entry_uses_max_rank_for_persist(self):
        """Key present only in recipe_preds: persist rank = max_rank (n+1)."""
        recipe = {(1, "a"): 10.0, (1, "b"): 5.0}
        persist = {(1, "a"): 3.0}  # (1, "b") is absent
        result = gcr.rank_fusion(recipe, persist, k=60)
        all_keys = {(1, "a"), (1, "b")}
        max_rank = len(all_keys) + 1  # = 3
        # (1, "b"): recipe_rank=2, persist_rank=max_rank=3
        expected_b = 1 / (60 + 2) + 1 / (60 + max_rank)
        assert _approx(result[(1, "b")], expected_b)

    def test_persist_only_entry_uses_max_rank_for_recipe(self):
        """Key present only in persist_preds: recipe rank = max_rank."""
        recipe = {(1, "a"): 10.0}
        persist = {(1, "a"): 3.0, (1, "b"): 1.0}  # (1, "b") absent from recipe
        result = gcr.rank_fusion(recipe, persist, k=60)
        all_keys = {(1, "a"), (1, "b")}
        max_rank = len(all_keys) + 1  # = 3
        # (1, "b"): recipe_rank=max_rank=3, persist_rank=2
        expected_b = 1 / (60 + max_rank) + 1 / (60 + 2)
        assert _approx(result[(1, "b")], expected_b)

    def test_default_k_is_60(self):
        """rank_fusion called without k uses k=60."""
        recipe = {(1, "a"): 1.0}
        persist = {(1, "a"): 1.0}
        result_default = gcr.rank_fusion(recipe, persist)
        result_explicit = gcr.rank_fusion(recipe, persist, k=60)
        assert result_default == result_explicit

    def test_empty_inputs_return_empty(self):
        """Both empty: result must be empty dict with no crash."""
        assert gcr.rank_fusion({}, {}) == {}

    def test_all_keys_present_in_output(self):
        """Output must contain union of both input key sets."""
        recipe = {(1, "a"): 5.0, (1, "b"): 3.0}
        persist = {(1, "b"): 2.0, (1, "c"): 1.0}
        result = gcr.rank_fusion(recipe, persist)
        assert set(result.keys()) == {(1, "a"), (1, "b"), (1, "c")}

    def test_higher_rank_gives_higher_score(self):
        """Rank-1 in both dimensions should score higher than rank-2 in both."""
        recipe = {(1, "a"): 10.0, (1, "b"): 5.0}
        persist = {(1, "a"): 3.0, (1, "b"): 1.0}
        result = gcr.rank_fusion(recipe, persist)
        assert result[(1, "a")] > result[(1, "b")]


# ===========================================================================
# risk_tier_label()  — V1.9.1 Fix C
# ===========================================================================

class TestRiskTierLabel:

    def test_empty_list_returns_indicative(self):
        assert gcr.risk_tier_label([]) == "INDICATIVE"

    def test_syria_class_civil_war_high_via_layer2(self):
        """civil_war_and_insurgency salience 1.58 with severity 1.0 -> HIGH (Layer 2 crisis threshold 1.4)."""
        scores = [{"salience_score": 1.58, "severity_tier": 1.0}]
        assert gcr.risk_tier_label(scores, DEFAULT_CFG) == "HIGH"

    def test_cape_verde_class_single_elections_moderate(self):
        """elections_and_voting salience 1.67, severity 0.6, single category -> MODERATE (Layer 1, not crisis)."""
        # severity < 1.0 → Layer 2 doesn't fire; Layer 3 needs >=2 categories; Layer 1 at 2.0
        scores = [{"salience_score": 1.67, "severity_tier": 0.6}]
        # 1.67 < REGULAR_HIGH(2.0), >= REGULAR_MODERATE(1.3) -> MODERATE
        assert gcr.risk_tier_label(scores, DEFAULT_CFG) == "MODERATE"

    def test_venezuela_class_composite_high_via_layer3(self):
        """3 categories >= 1.3 salience, one with severity >= 0.8 -> HIGH via Layer 3 composite."""
        scores = [
            {"salience_score": 1.5, "severity_tier": 0.8},  # triggers min_severity
            {"salience_score": 1.4, "severity_tier": 0.6},
            {"salience_score": 1.3, "severity_tier": 0.4},
        ]
        assert gcr.risk_tier_label(scores, DEFAULT_CFG) == "HIGH"

    def test_low_salience_all_below_moderate_cut(self):
        """All salience below REGULAR_MODERATE threshold -> INDICATIVE."""
        scores = [
            {"salience_score": 0.8, "severity_tier": 0.6},
            {"salience_score": 0.5, "severity_tier": 0.4},
        ]
        assert gcr.risk_tier_label(scores, DEFAULT_CFG) == "INDICATIVE"

    def test_layer1_regular_high_exact_boundary(self):
        """Salience exactly at REGULAR_HIGH(2.0), severity < 1.0 -> HIGH."""
        scores = [{"salience_score": 2.0, "severity_tier": 0.6}]
        assert gcr.risk_tier_label(scores, DEFAULT_CFG) == "HIGH"

    def test_layer2_crisis_high_exact_boundary(self):
        """Salience exactly at CRISIS_HIGH(1.4), severity >= 1.0 -> HIGH."""
        scores = [{"salience_score": 1.4, "severity_tier": 1.0}]
        assert gcr.risk_tier_label(scores, DEFAULT_CFG) == "HIGH"

    def test_layer2_crisis_moderate(self):
        """Crisis category between CRISIS_MODERATE(1.0) and CRISIS_HIGH(1.4) -> MODERATE."""
        scores = [{"salience_score": 1.2, "severity_tier": 1.0}]
        assert gcr.risk_tier_label(scores, DEFAULT_CFG) == "MODERATE"

    def test_layer3_requires_min_severity_in_above_floor_set(self):
        """Layer 3 fires only when at least one of the floor-meeting categories has severity >= 0.8."""
        # Both above floor but neither meets min_severity -> should not fire Layer 3
        scores = [
            {"salience_score": 1.5, "severity_tier": 0.6},
            {"salience_score": 1.4, "severity_tier": 0.6},
        ]
        # Max salience 1.5 < REGULAR_HIGH(2.0), >= REGULAR_MODERATE(1.3) -> MODERATE
        assert gcr.risk_tier_label(scores, DEFAULT_CFG) == "MODERATE"

    def test_layer3_requires_two_categories_at_floor(self):
        """Only one category above min_salience_floor: Layer 3 must NOT fire."""
        scores = [
            {"salience_score": 1.5, "severity_tier": 0.8},  # above floor + severity OK
            {"salience_score": 1.0, "severity_tier": 0.8},  # below floor
        ]
        # Layer 3: only 1 above floor -> doesn't fire
        # Layer 1: 1.5 < 2.0, >= 1.3 -> MODERATE
        assert gcr.risk_tier_label(scores, DEFAULT_CFG) == "MODERATE"

    def test_config_override_lowers_crisis_high(self):
        """Custom config with lower CRISIS_HIGH should promote a score that default would only MODERATE."""
        custom_cfg = {
            "thresholds": {
                "CRISIS_HIGH": 1.0,   # lowered from 1.4
                "REGULAR_HIGH": 2.0,
                "CRISIS_MODERATE": 0.5,
                "REGULAR_MODERATE": 1.3,
            },
            "composite_rule": {"enabled": False},
        }
        # Salience 1.2, crisis severity: default gives MODERATE; custom gives HIGH
        scores = [{"salience_score": 1.2, "severity_tier": 1.0}]
        assert gcr.risk_tier_label(scores, DEFAULT_CFG) == "MODERATE"
        assert gcr.risk_tier_label(scores, custom_cfg) == "HIGH"

    def test_config_none_uses_default(self):
        """Passing config=None should fall back to DEFAULT_SCORING_CONFIG."""
        scores = [{"salience_score": 1.58, "severity_tier": 1.0}]
        assert gcr.risk_tier_label(scores, None) == gcr.risk_tier_label(scores, DEFAULT_CFG)


# ===========================================================================
# severity_weight()
# ===========================================================================

class TestSeverityWeight:

    def test_civil_war_tier_1(self):
        """civil_war_and_insurgency is in tier 1.0."""
        assert gcr.severity_weight("civil_war_and_insurgency") == pytest.approx(1.0)

    def test_mass_protest_tier_0_8(self):
        """mass_protest is in tier 0.8."""
        assert gcr.severity_weight("mass_protest") == pytest.approx(0.8)

    def test_elections_tier_0_6(self):
        """elections_and_voting is in tier 0.6."""
        assert gcr.severity_weight("elections_and_voting") == pytest.approx(0.6)

    def test_government_formation_tier_0_4(self):
        """government_formation is in tier 0.4."""
        assert gcr.severity_weight("government_formation") == pytest.approx(0.4)

    def test_infrastructure_project_tier_0_05(self):
        """infrastructure_project is in suppressed tier 0.05."""
        assert gcr.severity_weight("infrastructure_project") == pytest.approx(0.05)

    def test_unknown_category_default_0_3(self):
        """Any unmapped category returns default 0.3."""
        assert gcr.severity_weight("completely_unknown_category_xyz") == pytest.approx(0.3)

    def test_empty_string_returns_default(self):
        assert gcr.severity_weight("") == pytest.approx(0.3)


# ===========================================================================
# load_severity_tiers()
# ===========================================================================

class TestLoadSeverityTiers:

    def test_explicit_path_loads_correctly(self):
        if not SEVERITY_TIERS_PATH.exists():
            pytest.skip("qgi-data severity tiers file not present")
        tiers = gcr.load_severity_tiers(path=str(SEVERITY_TIERS_PATH))
        assert isinstance(tiers, dict)
        assert len(tiers) > 0
        # Spot-check a known category
        assert tiers.get("civil_war_and_insurgency") == pytest.approx(1.0)

    def test_env_var_override(self, tmp_path):
        """QGI_SEVERITY_TIERS_PATH overrides the default cross-repo path."""
        fake_data = {
            "tiers": {
                "0.9": {"categories": ["test_category"]},
            }
        }
        fake_file = tmp_path / "fake_severity.json"
        fake_file.write_text(json.dumps(fake_data))
        old_env = os.environ.get("QGI_SEVERITY_TIERS_PATH")
        try:
            os.environ["QGI_SEVERITY_TIERS_PATH"] = str(fake_file)
            # Call without explicit path so env var is used
            tiers = gcr.load_severity_tiers()
            assert tiers.get("test_category") == pytest.approx(0.9)
        finally:
            if old_env is None:
                os.environ.pop("QGI_SEVERITY_TIERS_PATH", None)
            else:
                os.environ["QGI_SEVERITY_TIERS_PATH"] = old_env

    def test_missing_all_paths_returns_empty_dict(self, tmp_path, monkeypatch):
        """When all candidate paths miss, returns {} (T17 #310 silent-failure fix).

        Monkeypatching load_severity_tiers so all three candidate paths resolve
        to nonexistent locations — the legacy relative path exists in this
        monorepo layout, so we must pass an explicit nonexistent path AND clear
        the env var AND mock __file__ to point somewhere the relative path
        won't resolve. Achieved by calling a patched variant that only sees the
        explicit (missing) path.
        """
        monkeypatch.delenv("QGI_SEVERITY_TIERS_PATH", raising=False)
        missing = str(tmp_path / "nonexistent.json")
        # Temporarily patch the module's __file__ so the legacy relative path
        # resolves to a path that also doesn't exist.
        orig_file = gcr.__file__
        monkeypatch.setattr(gcr, "__file__", str(tmp_path / "fake_module.py"), raising=False)
        try:
            result = gcr.load_severity_tiers(path=missing)
        finally:
            gcr.__file__ = orig_file
        assert result == {}


# ===========================================================================
# load_scoring_config()
# ===========================================================================

class TestLoadScoringConfig:

    def test_explicit_path_loads_correctly(self):
        if not SCORING_CONFIG_PATH.exists():
            pytest.skip("qgi-data scoring config not present")
        cfg = gcr.load_scoring_config(path=str(SCORING_CONFIG_PATH))
        assert cfg["thresholds"]["CRISIS_HIGH"] == pytest.approx(1.4)
        assert cfg["thresholds"]["REGULAR_HIGH"] == pytest.approx(2.0)
        assert cfg["composite_rule"]["enabled"] is True

    def test_env_var_override(self, tmp_path):
        """QGI_SCORING_CONFIG_PATH env var is honoured."""
        custom_cfg = {
            "thresholds": {
                "CRISIS_HIGH": 0.5,
                "REGULAR_HIGH": 1.0,
                "CRISIS_MODERATE": 0.2,
                "REGULAR_MODERATE": 0.4,
            },
            "composite_rule": {"enabled": False},
        }
        fake_file = tmp_path / "custom_scoring.json"
        fake_file.write_text(json.dumps(custom_cfg))
        old_env = os.environ.get("QGI_SCORING_CONFIG_PATH")
        try:
            os.environ["QGI_SCORING_CONFIG_PATH"] = str(fake_file)
            cfg = gcr.load_scoring_config()
            assert cfg["thresholds"]["CRISIS_HIGH"] == pytest.approx(0.5)
        finally:
            if old_env is None:
                os.environ.pop("QGI_SCORING_CONFIG_PATH", None)
            else:
                os.environ["QGI_SCORING_CONFIG_PATH"] = old_env

    def test_all_paths_miss_returns_default_config(self, tmp_path, monkeypatch):
        """When all candidate paths miss, falls back to DEFAULT_SCORING_CONFIG.

        Same monorepo-resolution problem as the severity-tiers equivalent:
        patch __file__ so the legacy relative path doesn't resolve.
        """
        monkeypatch.delenv("QGI_SCORING_CONFIG_PATH", raising=False)
        missing = str(tmp_path / "ghost.json")
        orig_file = gcr.__file__
        monkeypatch.setattr(gcr, "__file__", str(tmp_path / "fake_module.py"), raising=False)
        try:
            cfg = gcr.load_scoring_config(path=missing)
        finally:
            gcr.__file__ = orig_file
        # Fallback must match the embedded default on the keys that matter
        assert cfg["thresholds"] == gcr.DEFAULT_SCORING_CONFIG["thresholds"]
        assert cfg["composite_rule"]["enabled"] == gcr.DEFAULT_SCORING_CONFIG["composite_rule"]["enabled"]

    def test_default_config_has_required_keys(self):
        """DEFAULT_SCORING_CONFIG has all keys risk_tier_label needs."""
        cfg = gcr.DEFAULT_SCORING_CONFIG
        assert "thresholds" in cfg
        assert "composite_rule" in cfg
        for key in ("CRISIS_HIGH", "REGULAR_HIGH", "CRISIS_MODERATE", "REGULAR_MODERATE"):
            assert key in cfg["thresholds"], f"Missing threshold key: {key}"


# ===========================================================================
# #201 Refinement 3: compute_per_category_caps()
# ===========================================================================

class TestComputePerCategoryCaps:

    def _countries_data_from_pairs(self, pairs):
        """Helper: convert [(cid, tier, category, salience), ...] to nested dict."""
        out = {}
        for cid, tier, cat, salience in pairs:
            out.setdefault(cid, {}).setdefault(tier, []).append({
                'category': cat,
                'salience_score': salience,
                'severity_tier': 0.5,
                'recipe_count': 10,
            })
        return out

    def test_uncapped_when_below_min_observations(self):
        """A category with fewer than min_observations entries is uncapped."""
        # 5 countries × 1 tier × 1 category = 5 observations on civil_war
        pairs = [(i, 'S', 'civil_war_and_insurgency', float(i)) for i in range(5)]
        data = self._countries_data_from_pairs(pairs)
        caps = gcr.compute_per_category_caps(data, percentile=0.95, min_observations=20)
        assert caps['civil_war_and_insurgency'] is None

    def test_capped_when_above_min_observations(self):
        """A category with 20+ entries gets a numeric cap at p95."""
        # 25 countries × 1 tier × 1 category = 25 observations
        pairs = [(i, 'S', 'mass_protest', float(i)) for i in range(25)]
        data = self._countries_data_from_pairs(pairs)
        caps = gcr.compute_per_category_caps(data, percentile=0.95, min_observations=20)
        # Sorted scores: [0, 1, 2, ..., 24]. p95 idx = round(0.95 * 24) = 23.
        # scores_sorted[23] = 23.0
        assert caps['mass_protest'] == 23.0

    def test_p100_returns_max(self):
        """Percentile 1.0 returns the maximum observation."""
        pairs = [(i, 'S', 'fiscal_policy', float(i)) for i in range(30)]
        data = self._countries_data_from_pairs(pairs)
        caps = gcr.compute_per_category_caps(data, percentile=1.0, min_observations=20)
        assert caps['fiscal_policy'] == 29.0

    def test_per_category_independence(self):
        """Two categories compute caps independently."""
        # 30 entries each for civil_war (high range) and elections (low range)
        pairs = [(i, 'S', 'civil_war_and_insurgency', float(i + 100)) for i in range(30)]
        pairs += [(i, 'S', 'elections_and_voting', float(i)) for i in range(30)]
        data = self._countries_data_from_pairs(pairs)
        caps = gcr.compute_per_category_caps(data, percentile=0.95, min_observations=20)
        # Different distributions → different caps
        assert caps['civil_war_and_insurgency'] > caps['elections_and_voting']
        assert caps['civil_war_and_insurgency'] == 128.0  # idx round(0.95*29)=28; scores[28]=128
        assert caps['elections_and_voting'] == 28.0


class TestApplyPerCategoryCaps:

    def test_clips_above_cap_in_place(self):
        """salience_score above cap is clipped to cap; below cap untouched."""
        data = {
            1: {'S': [
                {'category': 'civil_war_and_insurgency', 'salience_score': 5.0,
                 'severity_tier': 1.0, 'recipe_count': 10},
                {'category': 'civil_war_and_insurgency', 'salience_score': 0.5,
                 'severity_tier': 1.0, 'recipe_count': 10},
            ]},
        }
        caps = {'civil_war_and_insurgency': 2.0}
        clipped = gcr.apply_per_category_caps(data, caps)
        assert clipped == 1  # only the 5.0 row clipped
        assert data[1]['S'][0]['salience_score'] == 2.0  # clipped to cap
        assert data[1]['S'][1]['salience_score'] == 0.5  # untouched

    def test_none_cap_is_noop(self):
        """A None cap (insufficient observations) doesn't clip anything."""
        data = {
            1: {'S': [
                {'category': 'rare_event', 'salience_score': 100.0,
                 'severity_tier': 1.0, 'recipe_count': 1},
            ]},
        }
        caps = {'rare_event': None}
        clipped = gcr.apply_per_category_caps(data, caps)
        assert clipped == 0
        assert data[1]['S'][0]['salience_score'] == 100.0  # unchanged

    def test_unknown_category_skipped(self):
        """Salience for a category absent from the caps dict is left alone."""
        data = {
            1: {'S': [
                {'category': 'novel_category', 'salience_score': 99.0,
                 'severity_tier': 0.5, 'recipe_count': 10},
            ]},
        }
        caps = {}  # novel_category not in caps
        clipped = gcr.apply_per_category_caps(data, caps)
        assert clipped == 0
        assert data[1]['S'][0]['salience_score'] == 99.0


# ===========================================================================
# main() severity-tiers guard — #422 Bug 3
# ===========================================================================

class TestMainSeverityTiersGuard:

    def test_empty_severity_tiers_raises_runtime_error(self, monkeypatch):
        """#422 Bug 3: main() must refuse to run when SEVERITY_TIERS is empty.

        Without this guard, every category falls through to severity_weight()'s
        default 0.3, producing a uniform-salience country-risks.json with no
        alarm. Same class as the 2026-04-22 finalize-Lambda silent-failure.
        """
        monkeypatch.setattr(gcr, "SEVERITY_TIERS", {})
        monkeypatch.setattr(
            sys, "argv", ["generate_country_risks.py", "--bucket", "test-bucket"]
        )
        with pytest.raises(RuntimeError, match="category_severity_tiers.json"):
            gcr.main()

    def test_non_empty_severity_tiers_does_not_raise_on_guard(self, monkeypatch):
        """Non-empty SEVERITY_TIERS passes the guard (any subsequent AWS error is separate)."""
        monkeypatch.setattr(gcr, "SEVERITY_TIERS", {"civil_war_and_insurgency": 1.0})
        monkeypatch.setattr(
            sys, "argv", ["generate_country_risks.py", "--bucket", "test-bucket"]
        )
        # Guard should pass. Execution will fail later at boto3/Athena; we only
        # care that the failure is NOT the guard's RuntimeError.
        with pytest.raises(Exception) as exc_info:
            gcr.main()
        assert "refusing to score" not in str(exc_info.value)
