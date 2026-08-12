"""Unit tests for top10_per_tier.py.

#422 Bug 5 (2026-04-24): top10_per_tier.py used to execute Athena queries
at module import time, which made it unimportable in offline test contexts.
Refactored into a callable main(); this test file now verifies the module
imports cleanly and the pure functions (zscore_per_country, rank_fusion)
produce the expected results.

The pure functions are duplicated in generate_country_risks.py and
run_backtest.py, where they have thorough test coverage (#422 Bug 6
flags the duplication for consolidation). We keep minimal sanity checks
here to catch drift if someone edits one copy without updating the others.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import top10_per_tier as t10  # noqa: E402


# ===========================================================================
# Module import (Bug 5 regression guard)
# ===========================================================================

class TestModuleImport:

    def test_module_imports_without_aws_calls(self):
        """The bare import above must succeed. Any regression that re-adds
        module-scope Athena queries would make this test crash during
        collection — not fail here."""
        assert hasattr(t10, "main")
        assert callable(t10.main)

    def test_pure_functions_exposed(self):
        """zscore_per_country and rank_fusion must be importable pure functions."""
        assert callable(t10.zscore_per_country)
        assert callable(t10.rank_fusion)


# ===========================================================================
# zscore_per_country — sanity checks against drift
# ===========================================================================

class TestZscorePerCountry:

    def test_single_country_mean_zero_std_one(self):
        preds = {(1, "a"): 3.0, (1, "b"): 5.0, (1, "c"): 1.0}
        result = t10.zscore_per_country(preds)
        vals = list(result.values())
        mean = sum(vals) / len(vals)
        std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
        assert abs(mean) < 1e-9
        assert abs(std - 1.0) < 1e-9

    def test_single_category_passthrough(self):
        """Len < 2 branch: return unchanged."""
        assert t10.zscore_per_country({(1, "a"): 7.5}) == {(1, "a"): 7.5}

    def test_empty_input(self):
        assert t10.zscore_per_country({}) == {}


# ===========================================================================
# rank_fusion — sanity checks
# ===========================================================================

class TestRankFusion:

    def test_perfect_overlap(self):
        rp = {(1, "a"): 10.0, (1, "b"): 5.0}
        pp = {(1, "a"): 3.0, (1, "b"): 1.0}
        result = t10.rank_fusion(rp, pp, k=60)
        # (1, "a") at rank 1 in both → 2 * 1/(60+1)
        # (1, "b") at rank 2 in both → 2 * 1/(60+2)
        assert result[(1, "a")] == pytest.approx(2 / 61)
        assert result[(1, "b")] == pytest.approx(2 / 62)

    def test_missing_keys_use_max_rank(self):
        rp = {(1, "a"): 10.0, (1, "b"): 5.0}
        pp = {(1, "a"): 3.0}  # (1, "b") absent
        result = t10.rank_fusion(rp, pp, k=60)
        # 2 total keys → max_rank = 3; (1, "b") persist rank = 3
        expected_b = 1 / (60 + 2) + 1 / (60 + 3)
        assert result[(1, "b")] == pytest.approx(expected_b)

    def test_empty_inputs_return_empty(self):
        assert t10.rank_fusion({}, {}) == {}
