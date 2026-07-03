"""
Unit tests for A3 cascade M1+M2+M3 (Ihsa I1 lock 2026-05-02).

The methodology fixes are pure SQL changes inside `write_recipes_aggregated_table()`.
This test suite verifies the SQL CONTAINS the right patterns rather than executing
against Athena. Integration verification happens at trigger time (Greenlight 5)
under founder approval per `feedback_no_pipeline_runs_without_approval.md`.

Coverage:
- M1: weighted approx_percentile (3-arg form) on length × |avg_correlation|
- M2: hard-cut WHERE clause `abs(rd.avg_correlation) >= {threshold}` in temp_table CTAS
- M3: dual TF-IDF aggregations — unweighted (for Wilson CI) + weighted (for ranking)
- Constants: SCDI_M2_THRESHOLD default 0.75, env-overridable
- Module-level constants exist
- temp_table CTAS projects avg_correlation column
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# Load the Lambda module directly. Sibling import of `country_risks` requires
# adding the Lambda dir to sys.path before executing the spec.
_LAMBDA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "lambdas" / "pipeline-recipe-engine-finalize"
sys.path.insert(0, str(_LAMBDA_DIR))
_MODULE_PATH = _LAMBDA_DIR / "lambda_function.py"
_spec = importlib.util.spec_from_file_location("recipe_engine_finalize_a3", _MODULE_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


# ===========================================================================
# Module-level constants
# ===========================================================================


def test_scdi_m2_threshold_constant_exists():
    """SCDI_M2_THRESHOLD must be a module-level constant accessible to consumers."""
    assert hasattr(mod, "SCDI_M2_THRESHOLD"), "Module must expose SCDI_M2_THRESHOLD"
    assert isinstance(mod.SCDI_M2_THRESHOLD, float)


def test_scdi_m2_threshold_default_matches_ihsa_i1_lock():
    """Per Ihsa I1 vote 2026-05-02 (founder picked 0.75 over 0.90 alternative).

    A change to this default is a methodology change and requires a council
    convening. Test asserts the lock; it should fail loud if someone bumps the
    default unilaterally.
    """
    # Re-import module without the test environment's potential override
    import importlib.util as _iu

    spec = _iu.spec_from_file_location("recipe_engine_finalize_freshimport", _MODULE_PATH)
    fresh_mod = _iu.module_from_spec(spec)
    # Save and clear env to test the hardcoded default
    saved = os.environ.pop("SCDI_M2_THRESHOLD", None)
    try:
        spec.loader.exec_module(fresh_mod)
        assert fresh_mod.SCDI_M2_THRESHOLD == 0.75, (
            f"SCDI_M2_THRESHOLD default must be 0.75 per Ihsa I1 lock, got {fresh_mod.SCDI_M2_THRESHOLD}"
        )
    finally:
        if saved is not None:
            os.environ["SCDI_M2_THRESHOLD"] = saved


def test_scdi_m2_threshold_env_overridable():
    """Threshold must be env-overridable for backtest sweeps. Founder approves
    backtests; methodology changes still require a council vote."""
    import importlib.util as _iu

    spec = _iu.spec_from_file_location("recipe_engine_finalize_envtest", _MODULE_PATH)
    fresh_mod = _iu.module_from_spec(spec)
    saved = os.environ.get("SCDI_M2_THRESHOLD")
    os.environ["SCDI_M2_THRESHOLD"] = "0.85"
    try:
        spec.loader.exec_module(fresh_mod)
        assert fresh_mod.SCDI_M2_THRESHOLD == 0.85
    finally:
        if saved is None:
            os.environ.pop("SCDI_M2_THRESHOLD", None)
        else:
            os.environ["SCDI_M2_THRESHOLD"] = saved


def test_no_dead_ablation_flag():
    """Per strict review 2026-05-03 + Ihsa I1 lock: M3 is unconditionally
    weighted in v1. There must NOT be a dangling `M3_USE_WEIGHTED_TFIDF`
    env flag that's read but never branched on (silent dead code that
    misleads operators into thinking they can disable weighting).
    """
    # The flag MUST not be present in the module
    assert not hasattr(mod, "M3_USE_WEIGHTED_TFIDF"), (
        "M3_USE_WEIGHTED_TFIDF was a dead flag (read from env but never "
        "consumed in SQL). It was removed per strict review 2026-05-03. "
        "If a future ablation is needed, add a SQL conditional then — don't "
        "pre-bake a dead env flag."
    )


def test_scdi_m2_threshold_malformed_env_raises_runtime_error():
    """Strict-review minor #2: malformed SCDI_M2_THRESHOLD env var must
    produce a clear RuntimeError, not a cryptic ValueError at module load.
    """
    import importlib.util as _iu

    spec = _iu.spec_from_file_location("recipe_engine_finalize_badenv", _MODULE_PATH)
    fresh_mod = _iu.module_from_spec(spec)
    saved = os.environ.get("SCDI_M2_THRESHOLD")
    os.environ["SCDI_M2_THRESHOLD"] = "not-a-float"
    try:
        with pytest.raises(RuntimeError, match="SCDI_M2_THRESHOLD"):
            spec.loader.exec_module(fresh_mod)
    finally:
        if saved is None:
            os.environ.pop("SCDI_M2_THRESHOLD", None)
        else:
            os.environ["SCDI_M2_THRESHOLD"] = saved


# ===========================================================================
# SQL pattern verification — M1+M2+M3 must produce the right SQL strings
# ===========================================================================
#
# We invoke `write_recipes_aggregated_table()` with mocked Athena so the SQL
# string is sent to `run_query` and we can inspect what it contains.

# ===========================================================================
# SQL pattern verification (source-text inspection — no mocking needed)
# ===========================================================================
#
# These tests inspect the lambda_function.py source as a string and verify
# the M1+M2+M3 SQL fragments are present. This avoids the brittleness of
# trying to mock S3+Athena+the idempotency guard end-to-end, and keeps the
# tests focused on what they actually verify: the SQL templates are correct.
#
# Integration verification (does the SQL actually compute the right result
# on real Athena?) happens at trigger time under founder Greenlight 5
# per `feedback_no_pipeline_runs_without_approval.md`.

_LAMBDA_SOURCE = _MODULE_PATH.read_text(encoding="utf-8")


def test_temp_table_ctas_projects_avg_correlation():
    """The temp_table CTAS must SELECT rd.avg_correlation (needed for M1+M3)."""
    # Locate the temp_table CTAS block
    ctas_match = re.search(
        r"ctas_sql\s*=\s*f?\"\"\"(.*?)\"\"\"",
        _LAMBDA_SOURCE,
        re.DOTALL,
    )
    assert ctas_match, "Could not locate ctas_sql block in lambda_function.py"
    ctas_block = ctas_match.group(1)
    assert "rd.avg_correlation" in ctas_block, "temp_table CTAS must project rd.avg_correlation for M1+M3 weighting"


def test_m2_filter_present_in_temp_table_ctas():
    """M2: WHERE abs(rd.avg_correlation) >= {SCDI_M2_THRESHOLD} must appear in CTAS."""
    ctas_match = re.search(
        r"ctas_sql\s*=\s*f?\"\"\"(.*?)\"\"\"",
        _LAMBDA_SOURCE,
        re.DOTALL,
    )
    assert ctas_match
    ctas_block = ctas_match.group(1)
    # Match `abs(rd.avg_correlation) >= {SCDI_M2_THRESHOLD}` (f-string interp)
    assert re.search(
        r"WHERE\s+abs\(\s*rd\.avg_correlation\s*\)\s*>=\s*\{SCDI_M2_THRESHOLD\}",
        ctas_block,
    ), (
        "M2 hard-cut filter not found in CTAS. "
        "Expected `WHERE abs(rd.avg_correlation) >= {SCDI_M2_THRESHOLD}` "
        "(f-string substitution against module-level constant)"
    )


def test_m1_weighted_approx_percentile_present():
    """M1: canonical_length must use 3-arg approx_percentile(value, weight, 0.5)
    with the weight scaled by 100.0.

    THIS TEST IS ALSO THE REGRESSION GUARD for the *100.0 scaling. Removing
    the `* 100.0` from the source causes the pattern below not to match,
    and this test fails. There is no separate negative-form guard — QA
    review 2026-05-03 caught that a [^)]*? guard would silently no-op
    against the multi-line SQL, so the positive form does the work.

    Why *100.0 is required:

      Trino's approx_percentile requires weight >= 1 (treats weight as a
      per-item count and raises INVALID_FUNCTION_ARGUMENT at runtime if
      any weight is below 1). After the M2 filter abs(avg_correlation) >=
      0.75, every row's weight is in [0.75, 1.0] — every row would crash.
      The *100.0 lifts weights into [75, 100]. Scaling all weights by the
      same constant is a mathematical no-op for weighted percentile
      (uses ratios), but is required to satisfy the runtime constraint.

    Caught by smoke test 2026-05-03 (qid 0d1be98a) — the SQL would have
    crashed Greenlight 5 without the *100.0. The unit tests in this file
    cannot catch a Trino *runtime* constraint by source-text inspection
    alone; the staging smoke is the only path that finds it. This test
    pins the source to the *post-fix* form so a future maintainer can't
    remove the *100.0 without breaking CI.
    """
    pattern = (
        r"approx_percentile\s*\(\s*\n?\s*"
        r"cast\s*\(\s*length\s+as\s+double\s*\)\s*,\s*\n?\s*"
        r"abs\s*\(\s*cast\s*\(\s*avg_correlation\s+as\s+double\s*\)\s*\)\s*\*\s*100\.0\s*,\s*\n?\s*"
        r"0\.5\s*\n?\s*\)"
    )
    assert re.search(pattern, _LAMBDA_SOURCE, re.IGNORECASE), (
        "M1 weighted approx_percentile (with *100.0 scaling) not found. Expected:\n"
        "  approx_percentile(\n"
        "      cast(length as double),\n"
        "      abs(cast(avg_correlation as double)) * 100.0,\n"
        "      0.5\n"
        "  )\n"
        "The *100.0 satisfies Trino's weight>=1 runtime constraint. Removing\n"
        "it will cause the lambda to crash at runtime once the SQL hits Athena."
    )


def test_m1_no_unweighted_canonical_length_fallback():
    """No unweighted approx_percentile(length, 0.5) hidden in the canonical_length path."""
    # We accept other unweighted approx_percentile usages elsewhere; this guard
    # is specifically about `cast(length as double), 0.5` (no weight in between).
    unweighted_pattern = (
        r"approx_percentile\s*\(\s*"
        r"cast\s*\(\s*length\s+as\s+double\s*\)\s*,\s*"
        r"0\.5\s*\)"
    )
    assert not re.search(unweighted_pattern, _LAMBDA_SOURCE), (
        "M1 regression: unweighted approx_percentile(cast(length as double), 0.5) "
        "found in source — should be the 3-arg weighted form."
    )


def test_m3_dual_aggregations_present():
    """M3: indicator_counts must have BOTH unweighted and weighted aggregations."""
    # Unweighted count (preserved for Wilson CI semantic)
    assert "count(distinct recipe_id) AS recipes_with_indicator" in _LAMBDA_SOURCE, (
        "M3: unweighted recipes_with_indicator count missing (needed for Wilson CI)"
    )
    # Weighted aggregation in indicator_counts
    assert "recipes_with_indicator_weighted" in _LAMBDA_SOURCE, (
        "M3: weighted recipes_with_indicator_weighted aggregation missing (needed for TF-IDF)"
    )
    assert "n_recipes_weighted" in _LAMBDA_SOURCE, "M3: n_recipes_weighted missing"
    assert "n_total_weighted" in _LAMBDA_SOURCE, "M3: n_total_weighted missing"


def test_m3_tfidf_uses_weighted_aggregations():
    """M3: the tfidf expression must use the weighted aggregations, not unweighted."""
    # Match the weighted TF-IDF expression — allow newlines + whitespace
    pattern = (
        r"\(\s*ic\.recipes_with_indicator_weighted\s*/\s*rpc\.n_recipes_weighted\s*\)"
        r"\s*\n?\s*"
        r"\*\s*ln\s*\(\s*tr\.n_total_weighted\s*/\s*ic\.recipes_with_indicator_weighted\s*\)"
        r"\s*AS\s+tfidf"
    )
    assert re.search(pattern, _LAMBDA_SOURCE, re.IGNORECASE | re.DOTALL), (
        "M3: TF-IDF expression doesn't use weighted aggregations.\n"
        "Expected: `(ic.recipes_with_indicator_weighted / rpc.n_recipes_weighted) "
        "* ln(tr.n_total_weighted / ic.recipes_with_indicator_weighted) AS tfidf`"
    )


def test_m3_no_unweighted_tfidf_regression():
    """The pre-A3 unweighted TF-IDF expression must NOT remain in the source."""
    # Pre-A3 form was:
    #   cast(ic.recipes_with_indicator as double) / cast(rpc.n_recipes as double)
    #     * ln(cast(tr.n_total as double) / cast(ic.recipes_with_indicator as double))
    # This shouldn't be present anymore — the weighted form replaced it.
    pre_a3_tfidf = (
        r"cast\(ic\.recipes_with_indicator\s+as\s+double\)\s*/\s*"
        r"cast\(rpc\.n_recipes\s+as\s+double\)\s*\n?\s*"
        r"\*\s*ln\s*\("
    )
    assert not re.search(pre_a3_tfidf, _LAMBDA_SOURCE, re.IGNORECASE | re.DOTALL), (
        "M3 regression: pre-A3 unweighted TF-IDF expression found in source. "
        "The TF-IDF must use weighted aggregations (recipes_with_indicator_weighted)."
    )


def test_wilson_ci_keeps_unweighted_p():
    """M3 design lock: Wilson CI keeps unweighted p (binomial-CI semantic stays valid)."""
    pattern = (
        r"cast\(\s*ic\.recipes_with_indicator\s+as\s+double\s*\)\s*/\s*"
        r"cast\(\s*rpc\.n_recipes\s+as\s+double\s*\)\s+AS\s+p"
    )
    assert re.search(pattern, _LAMBDA_SOURCE, re.IGNORECASE), (
        "M3 design: Wilson CI input `p` must be unweighted "
        "(cast(ic.recipes_with_indicator as double) / cast(rpc.n_recipes as double))."
    )


def test_indicator_unnest_carries_weight():
    """M3: the indicator_unnest CTE must project `abs(cast(avg_correlation as double)) AS w`."""
    pattern = r"abs\s*\(\s*cast\s*\(\s*avg_correlation\s+as\s+double\s*\)\s*\)\s+AS\s+w"
    assert re.search(pattern, _LAMBDA_SOURCE, re.IGNORECASE), (
        "M3: indicator_unnest must project `abs(cast(avg_correlation as double)) AS w` "
        "for use as the per-row weight in downstream sum() aggregations."
    )
