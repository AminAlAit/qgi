"""
Tests for the MIN_YEAR_CUTOFF filter (#509) in scdi_finder.py.

V-Dem v16 brought 1789-2025 coverage to qgi_data.indicators (#494
close-out). The cutoff caps SCDI search at year >= 1960 to:
  1. Avoid analytically-uninformative pre-1960 V-Dem segments
  2. Cap the SCDI search-space explosion (~10x more compute without
     the cutoff)

Filter applies in `run_pipeline()` AFTER load_data() and BEFORE
preprocess_data() — so the streak-finder operates only on
cutoff-eligible years.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

import pytest


_SCDI_PATH = Path(__file__).resolve().parent.parent.parent.parent / "batch" / "scdi-finder" / "src" / "scdi_finder.py"


@pytest.fixture(scope="module")
def scdi_finder_module():
    """Load scdi_finder once per module. Skips if scipy/psutil missing
    (consistent with test_no_bh_fdr.py pattern)."""
    pytest.importorskip("scipy", reason="scdi_finder imports scipy.signal")
    pytest.importorskip("psutil", reason="scdi_finder imports psutil")
    spec = importlib.util.spec_from_file_location("scdi_finder", str(_SCDI_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------- #
# Source-text checks (run unconditionally, no scipy/psutil needed)       #
# ---------------------------------------------------------------------- #


def test_min_year_cutoff_constant_present_in_source():
    """Defense against accidental removal during a future refactor."""
    text = _SCDI_PATH.read_text(encoding="utf-8")
    assert (
        'MIN_YEAR_CUTOFF = int(os.environ.get("MIN_YEAR_CUTOFF"' in text
        or "MIN_YEAR_CUTOFF = int(os.environ.get('MIN_YEAR_CUTOFF'" in text
    ), "MIN_YEAR_CUTOFF env-var-overridable constant must exist."


def test_apply_year_cutoff_function_present_in_source():
    """The filter function and its call-site must both exist."""
    text = _SCDI_PATH.read_text(encoding="utf-8")
    assert "def apply_year_cutoff(" in text
    assert "indicator_df = apply_year_cutoff(indicator_df, MIN_YEAR_CUTOFF)" in text


def test_filter_applied_before_preprocess_data():
    """The order matters: filter must run BEFORE preprocess_data so the
    streak-finder operates on cutoff-eligible years only. A regression
    that moves the filter AFTER preprocess_data would silently break
    the contract — preprocess_data would build streaks from full data,
    THEN the cutoff would chop into them."""
    text = _SCDI_PATH.read_text(encoding="utf-8")
    cutoff_pos = text.find("indicator_df = apply_year_cutoff(")
    preprocess_pos = text.find("preprocess_data(indicator_df, countries, MIN_LENGTH)")
    assert cutoff_pos > 0, "apply_year_cutoff call missing"
    assert preprocess_pos > 0, "preprocess_data call missing"
    assert cutoff_pos < preprocess_pos, "apply_year_cutoff must be called BEFORE preprocess_data"


# ---------------------------------------------------------------------- #
# Module-level filter behaviour                                          #
# ---------------------------------------------------------------------- #


def test_apply_year_cutoff_drops_pre_1960_rows(scdi_finder_module):
    """Synthetic indicator_df with rows from 1850-2020. Cutoff at 1960
    must keep only 1960+ rows."""
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame(
        {
            "country": ["USA"] * 10,
            "year": [1850, 1900, 1955, 1960, 1965, 1970, 1980, 2000, 2010, 2020],
            "value": list(range(10)),
        }
    )
    out = scdi_finder_module.apply_year_cutoff(df, 1960)
    # 4 pre-1960 rows dropped (1850, 1900, 1955; 1960 is kept since `>=`)
    assert len(out) == 7
    assert out["year"].min() == 1960
    assert out["year"].max() == 2020


def test_apply_year_cutoff_inclusive_boundary(scdi_finder_module):
    """The cutoff is `>=` not `>`, so the boundary year IS included."""
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame({"country": ["X"] * 3, "year": [1959, 1960, 1961], "value": [1, 2, 3]})
    out = scdi_finder_module.apply_year_cutoff(df, 1960)
    assert sorted(out["year"].tolist()) == [1960, 1961]


def test_apply_year_cutoff_no_op_on_already_filtered_data(scdi_finder_module):
    """WB / FAO indicators with all rows >= 1960 are unchanged. This is
    the dominant case in production — only V-Dem ingests pre-1960
    rows."""
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame(
        {
            "country": ["USA", "USA", "GBR"],
            "year": [1971, 2000, 2020],
            "value": [1.0, 2.0, 3.0],
        }
    )
    out = scdi_finder_module.apply_year_cutoff(df, 1960)
    # No-op: same row count
    assert len(out) == len(df)
    # Same data
    assert out["year"].tolist() == df["year"].tolist()


def test_apply_year_cutoff_all_pre_cutoff_returns_empty(scdi_finder_module):
    """Edge case: indicator_df has only pre-1960 rows (e.g., a future
    archival indicator). Filter returns empty DataFrame; downstream
    preprocess_data sees `len(country_data) < min_len` and skips that
    country, so no SCDIs are computed but the script doesn't crash."""
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame(
        {
            "country": ["USA"] * 3,
            "year": [1850, 1900, 1955],
            "value": [1, 2, 3],
        }
    )
    out = scdi_finder_module.apply_year_cutoff(df, 1960)
    assert len(out) == 0
    # Schema preserved (DataFrame columns intact even when empty)
    assert list(out.columns) == ["country", "year", "value"]


def test_apply_year_cutoff_logs_drop_count(scdi_finder_module, caplog):
    """The filter logs how many rows it dropped — operator-visible
    signal that the filter took effect."""
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame({"country": ["X"] * 4, "year": [1900, 1960, 1980, 2000], "value": [1, 2, 3, 4]})
    with caplog.at_level(logging.INFO):
        scdi_finder_module.apply_year_cutoff(df, 1960)
    assert any("year_cutoff" in rec.message for rec in caplog.records), "expected a [year_cutoff] log entry"
    # The log mentions the drop count when rows are dropped
    drop_log = next(
        (rec.message for rec in caplog.records if "year_cutoff" in rec.message and "dropped" in rec.message), ""
    )
    assert "dropped 1" in drop_log or "dropped 1," in drop_log, f"expected 'dropped 1' in log, got: {drop_log}"


def test_apply_year_cutoff_logs_no_op_when_unchanged(scdi_finder_module, caplog):
    """When all rows survive, the log says 'no-op' so the operator
    knows the indicator is WB/FAO-style (already 1960+) vs V-Dem-style."""
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame({"country": ["X"] * 2, "year": [1980, 2000], "value": [1, 2]})
    with caplog.at_level(logging.INFO):
        scdi_finder_module.apply_year_cutoff(df, 1960)
    no_op_log = next(
        (rec.message for rec in caplog.records if "year_cutoff" in rec.message and "no-op" in rec.message),
        "",
    )
    assert no_op_log, "expected a 'no-op' log when no rows are dropped"


def test_apply_year_cutoff_missing_year_column_logs_warning(scdi_finder_module, caplog):
    """Defensive: future schema drift might rename the year column.
    Filter must NOT crash; just log and return the input unchanged."""
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame({"country": ["X"], "no_year_here": [42], "value": [1.0]})
    with caplog.at_level(logging.WARNING):
        out = scdi_finder_module.apply_year_cutoff(df, 1960)
    # Returned the input unchanged
    assert len(out) == len(df)
    # Logged a warning so the operator notices
    assert any(
        "year_cutoff" in rec.message and "year" in rec.message.lower() and rec.levelname == "WARNING"
        for rec in caplog.records
    )


def test_min_year_cutoff_default_is_1960(scdi_finder_module):
    """Pin the default. A future researcher who tweaks this must do so
    deliberately (and update this test) — silent drift on the cutoff
    would change every pipeline run's SCDI output."""
    assert scdi_finder_module.MIN_YEAR_CUTOFF == 1960


def test_min_year_cutoff_env_var_override(scdi_finder_module, monkeypatch):
    """Ablation researchers can override via env. Reload the module
    with MIN_YEAR_CUTOFF=1980 and check the constant picks up the
    override.

    Module-level constants are bound at import time. `spec_from_file_location`
    bypasses sys.modules so the override is picked up cleanly on
    re-execution (no caching gotcha). PR #10 review nit: dropped a
    redundant `pytest.importorskip("importlib")` that was a no-op
    against the module-level `import importlib.util` already at the
    top of the file.
    """
    monkeypatch.setenv("MIN_YEAR_CUTOFF", "1980")
    spec = importlib.util.spec_from_file_location("scdi_finder_override", str(_SCDI_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.MIN_YEAR_CUTOFF == 1980


def test_apply_year_cutoff_preserves_column_dtypes(scdi_finder_module):
    """Filter must not alter column dtypes — preprocess_data downstream
    relies on `year` being int and `value` being float."""
    pd = pytest.importorskip("pandas")
    import numpy as np

    df = pd.DataFrame(
        {
            "country": pd.Series(["X", "Y"], dtype=object),
            "year": pd.Series([1900, 2000], dtype=np.int64),
            "value": pd.Series([1.5, 2.5], dtype=np.float64),
        }
    )
    out = scdi_finder_module.apply_year_cutoff(df, 1960)
    assert out["year"].dtype == np.int64
    assert out["value"].dtype == np.float64
