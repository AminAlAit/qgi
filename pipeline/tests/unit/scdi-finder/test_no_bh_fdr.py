"""
Regression-prevention tests for #502 — BH-FDR removal from scdi_finder.

The Phase B SCDI finder previously applied Benjamini-Hochberg
multiple-testing correction to the survivors of the |r| pre-filter
(`#139` / pre-#502 code). That step was removed per founder hard veto
(`feedback_no_fdr_correction.md`); QGI is screening candidates for
downstream investigation, not making point claims that need bounded
false-discovery rates.

These tests fail loudly if a future refactor re-adds BH-FDR. They sit
next to the SCDI finder so a contributor running pytest locally before
committing will see the failure immediately.

Replaces `test_hac_pvalues.py` (deleted in the same commit), which
exercised `effective_df_for_source_type()` and
`pearson_pvalues_vectorized()` — both helpers existed solely to feed
BH-FDR p-values and were removed alongside the application block.

The source-text checks (read the file as bytes and grep) run
unconditionally so reintroduction is caught even on a developer
machine without scipy/psutil installed. The module-level checks load
scdi_finder via importlib and require the runtime deps; they skip when
those deps are missing.
"""

import importlib.util
import inspect
from pathlib import Path

import pytest

_SCDI_PATH = Path(__file__).resolve().parent.parent.parent.parent / "batch" / "scdi-finder" / "src" / "scdi_finder.py"


@pytest.fixture(scope="module")
def scdi_finder_module():
    """Load scdi_finder.py once per test module. Skips the test if
    scipy or psutil are missing — both are imported at module load
    time, so this fixture stand-in cannot proceed without them."""
    pytest.importorskip("scipy", reason="scdi_finder imports scipy.signal")
    pytest.importorskip("psutil", reason="scdi_finder imports psutil")

    spec = importlib.util.spec_from_file_location("scdi_finder", str(_SCDI_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------- #
# Source-text checks — run unconditionally (no runtime deps)              #
# ---------------------------------------------------------------------- #


def test_source_text_does_not_import_scipy_stats():
    """`from scipy import stats` was used for `stats.t.sf` inside the
    p-value helper. Removing the import alone catches a class of
    reintroductions that would otherwise silently land if a future
    contributor copied a snippet from git history."""
    text = _SCDI_PATH.read_text(encoding="utf-8")
    assert "from scipy import stats" not in text, (
        "scdi_finder must not import scipy.stats — only used by removed BH-FDR p-value helper. See #502."
    )
    assert "scipy.stats" not in text, "scdi_finder must not reference scipy.stats — see #502."


def test_source_text_does_not_call_bh_fdr_or_pvalue_helpers():
    """A contributor restoring BH-FDR would necessarily call
    `bh_fdr_mask(...)` and `pearson_pvalues_vectorized(...)`. Defensive
    grep — paired with the function-absent tests below to lock both
    the definition and the call site."""
    text = _SCDI_PATH.read_text(encoding="utf-8")
    assert "bh_fdr_mask(" not in text, "scdi_finder must not call bh_fdr_mask() — see #502."
    assert "pearson_pvalues_vectorized(" not in text, (
        "scdi_finder must not call pearson_pvalues_vectorized() — see #502."
    )
    assert "effective_df_for_source_type(" not in text, (
        "scdi_finder must not call effective_df_for_source_type() — see #502."
    )


def test_source_text_does_not_define_bh_fdr_env_vars():
    """`BH_FDR_ENABLED` / `BH_FDR_ALPHA` were the runtime kill-switches
    for the BH-FDR step. With BH-FDR gone, defining them at module
    level would suggest the kill-switch is still meaningful — it isn't."""
    text = _SCDI_PATH.read_text(encoding="utf-8")
    # `BH_FDR_ENABLED = ...` assignment must not exist.
    assert "BH_FDR_ENABLED =" not in text, "scdi_finder must not define BH_FDR_ENABLED — see #502."
    assert "BH_FDR_ALPHA =" not in text, "scdi_finder must not define BH_FDR_ALPHA — see #502."


# ---------------------------------------------------------------------- #
# Module-level checks — require scipy + psutil (run in CI, skip on dev)  #
# ---------------------------------------------------------------------- #


def test_bh_fdr_mask_function_is_absent(scdi_finder_module):
    """The BH-FDR mask function existed pre-#502. Its absence removes
    the only mechanism that could re-enable per-p-value pruning."""
    assert not hasattr(scdi_finder_module, "bh_fdr_mask"), (
        "bh_fdr_mask() must not exist in scdi_finder — see #502 / feedback_no_fdr_correction.md."
    )


def test_pearson_pvalues_vectorized_function_is_absent(scdi_finder_module):
    """The vectorized p-value helper fed BH-FDR exclusively. Without
    BH-FDR there is no consumer; re-introducing it signals BH-FDR is
    coming back."""
    assert not hasattr(scdi_finder_module, "pearson_pvalues_vectorized"), (
        "pearson_pvalues_vectorized() must not exist in scdi_finder — see #502."
    )


def test_effective_df_for_source_type_function_is_absent(scdi_finder_module):
    """The HAC degrees-of-freedom adjustment (#364) only mattered if
    p-values were computed; without BH-FDR it has no consumer."""
    assert not hasattr(scdi_finder_module, "effective_df_for_source_type"), (
        "effective_df_for_source_type() must not exist in scdi_finder — see #502."
    )


def test_bh_fdr_env_var_constants_are_absent(scdi_finder_module):
    """Module-level absence of the env-var constants. Belt-and-braces
    against the source-text test catching only the assignment form."""
    assert not hasattr(scdi_finder_module, "BH_FDR_ENABLED"), (
        "BH_FDR_ENABLED must not be a module-level constant — see #502."
    )
    assert not hasattr(scdi_finder_module, "BH_FDR_ALPHA"), (
        "BH_FDR_ALPHA must not be a module-level constant — see #502."
    )


def test_tier_threshold_is_the_sole_correlation_gate(scdi_finder_module):
    """Sanity check that the |r|-based tier function still exists and
    returns the documented thresholds. With BH-FDR gone, this is the
    only correlation-test-layer filter."""
    mod = scdi_finder_module
    assert hasattr(mod, "tier_threshold"), (
        "tier_threshold() must remain — it is the sole correlation-test gate post-#502."
    )
    # S tier (3-8 yr) -> 0.88
    assert mod.tier_threshold(5) == pytest.approx(0.88)
    assert mod.tier_threshold(8) == pytest.approx(0.88)
    # M tier (9-20 yr) -> 0.85
    assert mod.tier_threshold(9) == pytest.approx(0.85)
    assert mod.tier_threshold(20) == pytest.approx(0.85)
    # L tier (21-40 yr) -> 0.82
    assert mod.tier_threshold(21) == pytest.approx(0.82)
    assert mod.tier_threshold(40) == pytest.approx(0.82)
    # XL tier (41+ yr) -> 0.82
    assert mod.tier_threshold(41) == pytest.approx(0.82)
    assert mod.tier_threshold(100) == pytest.approx(0.82)


def test_find_and_save_signature_no_source_type_param(scdi_finder_module):
    """`source_type` was a BH-FDR-only parameter (passed only to
    pearson_pvalues_vectorized). Its presence in the signature would
    indicate partial reversion."""
    sig = inspect.signature(scdi_finder_module.find_and_save_sdcis_parallel)
    assert "source_type" not in sig.parameters, (
        "find_and_save_sdcis_parallel must not accept source_type — "
        "this parameter only existed to feed BH-FDR p-values. See #502."
    )
