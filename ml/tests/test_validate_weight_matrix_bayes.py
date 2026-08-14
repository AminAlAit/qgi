"""
Unit tests for the Phase 5 v0.2 Path B evaluator.

Scope: the parts of `validate_weight_matrix_bayes.py` that are safely
testable without invoking PyMC's heavy MCMC machinery — module imports,
constants (post-6-seat amendment at docs-specs `0db64f9`), the synthetic-
data generator, the CellsArray dataclass + its provenance hash, the
real-data prep helper (`prep_cells_from_arm_jsons`), and the CLI
argument plumbing.

The smoke test (`run_smoke_test()`) is exercised end-to-end by the
`--smoke` CLI in CI / the PR description, not by pytest — it requires
pymc / numpyro / arviz which live in `requirements-path-b.txt`, not in
the default `requirements.txt`. Per Ji-Hoon #21 §3.1 sign-off, sampling
config + diagnostic verification is the integration-level contract.

Last amended: 2026-05-15 (6-seat Majles convening at qgi-aws-tf#691 ratified
the response-variable shift `auc` → `anomaly_score` plus surgical prior
re-derivations; this test file pins the amended values as canary)
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest


_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "validate_weight_matrix_bayes.py"
_spec = importlib.util.spec_from_file_location("validate_weight_matrix_bayes", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
sys.modules["validate_weight_matrix_bayes"] = mod
_spec.loader.exec_module(mod)


# ===========================================================================
# Constants — amended at docs-specs `0db64f9` per 2026-05-15 6-seat Majles
# (qgi-aws-tf#691). These tests pin the amended values; any future change
# requires a new Majles convening per the §2 line 66 binding clause as
# amended. The test failure is the canary.
# ===========================================================================

def test_priors_locked_at_amended_values():
    """6-seat amendment 2026-05-15:
      §2.1 tau_arm scale 0.05 AUC → 0.30 anomaly_score (k=5.72 signed pooled)
      §2.2 HalfCauchy 0.05 INVARIANT (Ji-Hoon scale-invariance ruling)
      §2.4 mu Normal(0.30, 0.05) AUC-mixture → Normal(0.168, 0.263) empirical-Bayes

    Amending any of these requires a fresh Majles convening with Priya #22,
    Ji-Hoon #21, Kwame #11 plus Roshani #18 / Miriam #14 / Tariq #20 where
    their work is impacted.
    """
    assert mod.TAU_ARM_PRIOR_SCALE == 0.30, "spec §2.1 amended at 0db64f9"
    assert mod.HALF_CAUCHY_SCALE == 0.05, "spec §2.2 INVARIANT"
    assert mod.MU_PRIOR_CENTER == 0.168, "spec §2.4 empirical mu_empirical at 0db64f9"
    assert mod.MU_PRIOR_SCALE == 0.263, "spec §2.4 = 0.5 × sigma_empirical at 0db64f9"


def test_sampling_config_locked_at_ratified_values():
    """§3.1 sampling config geometry block INVARIANT under amendment
    (Ji-Hoon Move 1 round-2 + 2026-05-16 3-seat ratification at qgi-aws-tf#744
    which raised target_accept 0.95 → 0.99 to clear v6 divergence triple-FAIL).

    Amending any of these values requires a new convening:
      - n_chains / n_tune / n_draws / max_treedepth: 3-seat OR 6-seat
        depending on amendment scope (Ji-Hoon §3.1-author call)
      - target_accept: 3-seat (per #744 Ji-Hoon spec-authority ruling that
        target_accept is sampler-hyperparameter, not geometry)
    """
    assert mod.N_CHAINS == 4, "spec §3.1 geometry INVARIANT"
    assert mod.N_TUNE == 1000, "spec §3.1 geometry INVARIANT"
    assert mod.N_DRAWS == 2000, "spec §3.1 geometry INVARIANT"
    assert mod.TARGET_ACCEPT == 0.99, \
        "spec §3.1 amended 2026-05-16 at qgi-aws-tf#744 (was 0.95)"
    assert mod.MAX_TREEDEPTH == 12, "spec §3.1 geometry INVARIANT"


def test_diagnostic_thresholds_locked_at_ratified_values():
    assert mod.R_HAT_THRESHOLD == 1.01, "Ji-Hoon §3.1"
    assert mod.N_EFF_THRESHOLD == 400, "Ji-Hoon §3.1"
    assert mod.DIVERGENCE_THRESHOLD_PCT == 0.001, "Ji-Hoon §3.1 (< 0.1 %)"
    assert mod.E_BFMI_THRESHOLD == 0.3, "Ji-Hoon §3.1"
    assert mod.TREEDEPTH_SATURATION_THRESHOLD == 0.01, \
        "Ji-Hoon J-§3.1: < 1 % treedepth saturation (was non-blocking 2026-05-14; " \
        "MANDATORY 2026-05-15 6-seat); pinned at v0.2-bayes-sweep-config.json"


def test_diagnostic_var_names_covers_all_9_sampled_rvs():
    """F-1 from QA review of PR #60; Kwame round-2 reclassified from
    polish to pre-registration-discipline gap; Ji-Hoon real-data ratification
    MANDATORY: compute_diagnostics's R-hat / n_eff gate must include the
    272-element country_intercept_raw block (the funnel-failure site) plus
    all hyperprior scales — otherwise a chain breakdown there silently
    passes the gate. Any future shrinkage of DIAGNOSTIC_VAR_NAMES requires
    a fresh Majles convening per Kwame round-2 ruling."""
    expected = {
        "mu", "tau_arm", "sigma_sector", "alpha_sector", "sigma_cat",
        "beta_cat_raw", "sigma_country", "country_intercept_raw", "sigma",
    }
    assert set(mod.DIAGNOSTIC_VAR_NAMES) == expected, \
        f"DIAGNOSTIC_VAR_NAMES drift; got {set(mod.DIAGNOSTIC_VAR_NAMES)}, " \
        f"expected {expected}"


def test_chain_seeds_are_at_least_n_chains():
    assert len(mod.CHAIN_SEEDS) >= mod.N_CHAINS, "need one seed per chain"


def test_chain_seeds_pinned_at_ratified_values():
    """Ji-Hoon §3.4: per-chain seeds are the carry-over from Roshani's A3
    baseline set. Closing the F-4 gap from QA review of PR #60: the
    length-only test above doesn't catch a silent value swap. Any future
    change to these specific values must come paired with a Majles
    re-convening, just like the prior constants. See qgi-aws-tf#684."""
    assert mod.CHAIN_SEEDS == (17, 42, 123, 271), \
        "CHAIN_SEEDS drift from ratified Ji-Hoon §3.4 values"


def test_schema_version_starts_at_one():
    """Path B is a distinct output family from Path A (rule v2 verdicts);
    the schema versions are independent and Path B starts at v1."""
    assert mod.PATH_B_SCHEMA_VERSION == 1


def test_arm_json_paths_point_at_v6_sidecars():
    """6-seat amendment: ARM_JSON_PATHS must point at the Path A v6.6
    --emit-per-cell sidecar JSONs (`-v6.json` suffix at qgi-data `14ebded`),
    NOT the v5 originals (T11 falsification substrate; Protocol-5).
    """
    for arm in ("A", "B", "C", "D"):
        path = mod.ARM_JSON_PATHS[arm]
        assert path.name == f"phase4-validation-arm{arm}-v6.json", \
            f"ARM_JSON_PATHS[{arm}] must point at v6 sidecar, not v5 original"


def test_root_resolves_to_monorepo_with_qgi_data_sibling():
    """Module-load assertion ensures ROOT/data-tools exists in the unified monorepo."""
    assert (mod.ROOT / "data-tools").is_dir(), (
        "ROOT/data-tools missing; the module-load assertion at "
        "validate_weight_matrix_bayes.py should have fired before reaching this test"
    )
    assert (mod.ROOT / "ml").is_dir(), "ROOT/ml expected in monorepo"
    assert (mod.ROOT / "docs").is_dir(), "ROOT/docs expected in monorepo"


def test_root_assertion_fires_when_qgi_data_missing(tmp_path, monkeypatch):
    """N-1 (QA review of #70): negative-branch test for the ROOT
    assertion at validate_weight_matrix_bayes.py:106. The positive-pin
    test above is a tautology since module-load fires the assert before
    pytest runs. This test reloads the module under a faked __file__
    that resolves to a tmp_path with NO sibling qgi-data dir, confirming
    the runtime invariant actually fires.

    Companion N-2 fix: assertion replaced with explicit `raise RuntimeError`
    so `python -O` doesn't strip it. This test verifies the RuntimeError
    surfaces correctly.
    """
    import importlib.util as _util

    # Build a fake script path 3 levels under tmp_path so
    # Path(__file__).resolve().parent.parent.parent == tmp_path
    fake_script_dir = tmp_path / "fake-qgi-ml" / "scripts"
    fake_script_dir.mkdir(parents=True)
    fake_script = fake_script_dir / "validate_weight_matrix_bayes.py"

    # Copy the real script's source so module body runs verbatim
    real_script_text = (
        Path(__file__).resolve().parent.parent / "scripts" /
        "validate_weight_matrix_bayes.py"
    ).read_text(encoding="utf-8")
    fake_script.write_text(real_script_text, encoding="utf-8")

    # NO qgi-data sibling created — assertion must fire on load.
    spec = _util.spec_from_file_location("vwmb_negative_branch_test", fake_script)
    fake_mod = _util.module_from_spec(spec)
    with pytest.raises(RuntimeError, match="ROOT resolution failed"):
        spec.loader.exec_module(fake_mod)


# ===========================================================================
# make_synthetic_cells — shape, dtype, NaN structure
# ===========================================================================

def test_synthetic_cells_default_shape():
    cells = mod.make_synthetic_cells()
    assert cells.anomaly_score.shape == (4, 30, 12), \
        "default n_countries=30, n_categories=12, 4 arms"
    assert cells.n_arms == 4
    assert cells.n_countries == 30
    assert cells.n_categories == 12
    assert cells.n_sectors == 4


def test_synthetic_cells_custom_shape():
    cells = mod.make_synthetic_cells(n_countries=10, n_categories=8, n_sectors=2)
    assert cells.anomaly_score.shape == (4, 10, 8)
    assert cells.n_sectors == 2


def test_synthetic_cells_arm_labels_are_abcd():
    cells = mod.make_synthetic_cells()
    assert cells.arm_labels == ["A", "B", "C", "D"]


def test_synthetic_cells_has_nan_at_missing_rate():
    """Default missing_rate=0.30 should drop roughly 30% of cells to NaN.
    Stochastic but with seed=42 fixed; tolerate a wide envelope."""
    cells = mod.make_synthetic_cells(missing_rate=0.30, seed=42)
    n_nan = int(np.sum(np.isnan(cells.anomaly_score)))
    total = cells.anomaly_score.size
    nan_frac = n_nan / total
    assert 0.20 < nan_frac < 0.40, f"expected ~30% NaN; got {nan_frac:.3f}"


def test_synthetic_cells_zero_missing_rate_no_nan():
    cells = mod.make_synthetic_cells(missing_rate=0.0)
    assert not np.any(np.isnan(cells.anomaly_score))


def test_synthetic_cells_sector_idx_in_range():
    cells = mod.make_synthetic_cells(n_categories=12, n_sectors=4)
    assert cells.sector_idx_for_category.shape == (12,)
    assert cells.sector_idx_for_category.min() >= 0
    assert cells.sector_idx_for_category.max() < 4


def test_synthetic_cells_dgp_tau_recoverable_direction():
    """The planted ground truth has tau_arm = (+0.04, +0.02, -0.01, 0.0),
    so the raw cell means should show A > D in expectation."""
    cells = mod.make_synthetic_cells(missing_rate=0.0, seed=42)
    arm_means = np.nanmean(cells.anomaly_score, axis=(1, 2))
    a_minus_d = arm_means[0] - arm_means[3]
    assert a_minus_d > 0.01, f"DGP plants +0.04 A-D swing; got {a_minus_d:.4f}"


def test_synthetic_cells_seed_reproducible():
    c1 = mod.make_synthetic_cells(seed=42)
    c2 = mod.make_synthetic_cells(seed=42)
    np.testing.assert_array_equal(c1.anomaly_score, c2.anomaly_score,
                                  "same seed → identical cells")


def test_synthetic_cells_different_seeds_differ():
    c1 = mod.make_synthetic_cells(seed=42, missing_rate=0.0)
    c2 = mod.make_synthetic_cells(seed=43, missing_rate=0.0)
    assert not np.array_equal(c1.anomaly_score, c2.anomaly_score), \
        "different seeds → different cells"


# ===========================================================================
# CellsArray.sha256_provenance — reproducibility hash (§3.4)
# ===========================================================================

def test_sha256_provenance_deterministic_same_input():
    c1 = mod.make_synthetic_cells(seed=42)
    c2 = mod.make_synthetic_cells(seed=42)
    assert c1.sha256_provenance() == c2.sha256_provenance()


def test_sha256_provenance_differs_on_different_data():
    c1 = mod.make_synthetic_cells(seed=42)
    c2 = mod.make_synthetic_cells(seed=43)
    assert c1.sha256_provenance() != c2.sha256_provenance()


def test_sha256_provenance_sensitive_to_label_order():
    """Swapping arm labels should change the hash (label ordering is
    load-bearing for downstream posterior interpretation)."""
    cells = mod.make_synthetic_cells(seed=42)
    h_original = cells.sha256_provenance()
    cells.arm_labels = ["D", "C", "B", "A"]
    h_swapped = cells.sha256_provenance()
    assert h_original != h_swapped


def test_sha256_provenance_hex_string_length():
    cells = mod.make_synthetic_cells()
    h = cells.sha256_provenance()
    assert len(h) == 64, "SHA-256 hex digest is 64 chars"
    assert all(c in "0123456789abcdef" for c in h)


# ===========================================================================
# prep_cells_from_arm_jsons — real-data extraction (6-seat amendment)
# ===========================================================================

def _write_minimal_v6_arm_json(path: Path, *, arm: str, cells: list[dict]) -> None:
    """Helper to write a minimal v6-shaped arm JSON for testing."""
    payload = {
        "schema_version": 6,
        "ablation_arm": arm,
        "per_cell": {
            "schema_version": 1,
            "n_cells": len(cells),
            "n_indicators_used_min": min((c["n_indicators_used"] for c in cells), default=0),
            "n_indicators_used_max": max((c["n_indicators_used"] for c in cells), default=0),
            "n_indicators_used_median": float(np.median([c["n_indicators_used"] for c in cells]))
                if cells else 0.0,
            "cells": cells,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_prep_helper_raises_when_arm_json_missing(tmp_path):
    """Missing JSONs → FileNotFoundError before any extraction work."""
    fake_paths = {arm: tmp_path / f"phase4-validation-arm{arm}-v6.json"
                  for arm in ("A", "B", "C", "D")}
    with pytest.raises(FileNotFoundError, match="Missing per-arm v6 sidecar JSONs"):
        mod.prep_cells_from_arm_jsons(fake_paths)


def test_prep_helper_raises_keyerror_when_per_cell_block_missing(tmp_path):
    """An arm JSON lacking the per_cell block (e.g., v5 schema, or v6
    without --emit-per-cell) → KeyError pointing at the v6.6 fix."""
    paths = {}
    for arm in ("A", "B", "C", "D"):
        p = tmp_path / f"phase4-validation-arm{arm}-v6.json"
        # v5-shaped payload: no per_cell block
        p.write_text(json.dumps({"schema_version": 5, "ablation_arm": arm}),
                     encoding="utf-8")
        paths[arm] = p
    with pytest.raises(KeyError, match="no 'per_cell' block"):
        mod.prep_cells_from_arm_jsons(paths)


def test_prep_helper_returns_cells_array_with_correct_shape(tmp_path):
    """Happy path: 4 arms, 2 countries, 3 categories → CellsArray with
    anomaly_score shape (4, 2, 3) and full label sets."""
    paths = {}
    countries = [101, 202]
    categories = ["civil_war", "monetary_policy", "famine"]
    for arm in ("A", "B", "C", "D"):
        cells = []
        for country_id in countries:
            for cat in categories:
                cells.append({
                    "country_id": country_id,
                    "event_category": cat,
                    "anomaly_score": 0.1 * country_id + 0.01 * hash(cat) % 7
                                     + (ord(arm) - ord("A")) * 0.5,
                    "n_indicators_used": 5,
                })
        p = tmp_path / f"phase4-validation-arm{arm}-v6.json"
        _write_minimal_v6_arm_json(p, arm=arm, cells=cells)
        paths[arm] = p

    result = mod.prep_cells_from_arm_jsons(paths, l1_mapping={})

    assert result.anomaly_score.shape == (4, 2, 3), \
        f"expected (4, 2, 3), got {result.anomaly_score.shape}"
    assert result.arm_labels == ["A", "B", "C", "D"]
    # country labels are sorted as strings of their ids
    assert sorted(result.country_labels) == ["101", "202"]
    # category labels sorted alphabetically
    assert sorted(result.category_labels) == sorted(categories)
    # without L1 mapping, each category becomes its own sector
    assert result.n_sectors == 3


def test_prep_helper_nan_for_missing_arm_cells(tmp_path):
    """When an arm omits some (country, category) cells, those positions
    in the tensor are NaN — PyMC's auto-imputation absorbs them."""
    paths = {}
    full_cells = [
        {"country_id": 1, "event_category": "civil_war", "anomaly_score": 0.5,
         "n_indicators_used": 3},
        {"country_id": 2, "event_category": "civil_war", "anomaly_score": 0.7,
         "n_indicators_used": 3},
    ]
    sparse_cells = [
        # Only one cell — country 2 missing for this arm
        {"country_id": 1, "event_category": "civil_war", "anomaly_score": 0.3,
         "n_indicators_used": 2},
    ]
    for arm in ("A", "B", "C"):
        p = tmp_path / f"phase4-validation-arm{arm}-v6.json"
        _write_minimal_v6_arm_json(p, arm=arm, cells=full_cells)
        paths[arm] = p
    # Arm D is sparse
    p_d = tmp_path / "phase4-validation-armD-v6.json"
    _write_minimal_v6_arm_json(p_d, arm="D", cells=sparse_cells)
    paths["D"] = p_d

    result = mod.prep_cells_from_arm_jsons(paths, l1_mapping={})

    # Union universe: 2 countries × 1 category = 2 cells per arm
    assert result.anomaly_score.shape == (4, 2, 1)
    # Arm D: country 1 present (0.3), country 2 NaN
    d_idx = result.arm_labels.index("D")
    # Find country 2's index
    c2_idx = result.country_labels.index("2")
    assert np.isnan(result.anomaly_score[d_idx, c2_idx, 0]), \
        "missing cell in arm D should be NaN"
    # Arm A: country 2 present (0.7)
    a_idx = result.arm_labels.index("A")
    assert result.anomaly_score[a_idx, c2_idx, 0] == 0.7


def test_prep_helper_uses_l1_mapping(tmp_path):
    """When an L1 mapping is supplied, multiple categories collapse to
    shared sectors and sector_idx_for_category indexes them correctly."""
    paths = {}
    cells_per_arm = [
        {"country_id": 1, "event_category": "civil_war", "anomaly_score": 0.5,
         "n_indicators_used": 5},
        {"country_id": 1, "event_category": "famine", "anomaly_score": 0.4,
         "n_indicators_used": 5},
        {"country_id": 1, "event_category": "fiscal_policy", "anomaly_score": 0.3,
         "n_indicators_used": 5},
    ]
    for arm in ("A", "B", "C", "D"):
        p = tmp_path / f"phase4-validation-arm{arm}-v6.json"
        _write_minimal_v6_arm_json(p, arm=arm, cells=cells_per_arm)
        paths[arm] = p

    l1 = {
        "civil_war": "conflict",
        "famine": "conflict",
        "fiscal_policy": "economic",
    }
    result = mod.prep_cells_from_arm_jsons(paths, l1_mapping=l1)

    # 2 unique sectors (conflict + economic)
    assert result.n_sectors == 2
    assert sorted(result.sector_labels) == ["conflict", "economic"]
    # civil_war and famine should share a sector index; fiscal_policy a different one
    cat_to_idx = {c: i for i, c in enumerate(result.category_labels)}
    civil_sec = result.sector_idx_for_category[cat_to_idx["civil_war"]]
    famine_sec = result.sector_idx_for_category[cat_to_idx["famine"]]
    fiscal_sec = result.sector_idx_for_category[cat_to_idx["fiscal_policy"]]
    assert civil_sec == famine_sec, "civil_war and famine should share sector"
    assert civil_sec != fiscal_sec, "fiscal_policy should be a different sector"


def test_prep_helper_handles_none_anomaly_score(tmp_path):
    """JSON null for anomaly_score (from `_nan_to_none` in Path A v6.6 when
    the cell was emitted as NaN) round-trips to numpy NaN."""
    paths = {}
    cells = [
        {"country_id": 1, "event_category": "civil_war",
         "anomaly_score": None, "n_indicators_used": 0},  # NaN cell
        {"country_id": 1, "event_category": "famine",
         "anomaly_score": 0.5, "n_indicators_used": 5},
    ]
    for arm in ("A", "B", "C", "D"):
        p = tmp_path / f"phase4-validation-arm{arm}-v6.json"
        _write_minimal_v6_arm_json(p, arm=arm, cells=cells)
        paths[arm] = p

    result = mod.prep_cells_from_arm_jsons(paths, l1_mapping={})

    civil_idx = result.category_labels.index("civil_war")
    famine_idx = result.category_labels.index("famine")
    # All 4 arms should have NaN at civil_war (from None) and 0.5 at famine
    for arm_idx in range(4):
        assert np.isnan(result.anomaly_score[arm_idx, 0, civil_idx]), \
            f"arm {arm_idx}: None in JSON should round-trip to NaN"
        assert result.anomaly_score[arm_idx, 0, famine_idx] == 0.5


def test_prep_helper_deterministic_label_ordering(tmp_path):
    """Label ordering must be deterministic across runs (load-bearing for
    sha256_provenance and downstream posterior interpretation)."""
    paths = {}
    # Insert cells in DIFFERENT order across arms to verify ordering is
    # determined by sort, not insertion order
    base_cells = [
        {"country_id": 3, "event_category": "famine", "anomaly_score": 0.3,
         "n_indicators_used": 5},
        {"country_id": 1, "event_category": "civil_war", "anomaly_score": 0.5,
         "n_indicators_used": 5},
        {"country_id": 2, "event_category": "fiscal_policy", "anomaly_score": 0.4,
         "n_indicators_used": 5},
    ]
    for arm in ("A", "B", "C", "D"):
        p = tmp_path / f"phase4-validation-arm{arm}-v6.json"
        _write_minimal_v6_arm_json(p, arm=arm, cells=base_cells)
        paths[arm] = p

    # Run twice; expect identical label ordering both times
    r1 = mod.prep_cells_from_arm_jsons(paths, l1_mapping={})
    r2 = mod.prep_cells_from_arm_jsons(paths, l1_mapping={})

    assert r1.country_labels == r2.country_labels
    assert r1.category_labels == r2.category_labels
    assert r1.arm_labels == r2.arm_labels
    assert r1.sector_labels == r2.sector_labels  # FU-1 from QA review of PR #65
    # Country labels should be sorted: "1", "2", "3"
    assert r1.country_labels == ["1", "2", "3"]
    # Category labels should be sorted alphabetically
    assert r1.category_labels == ["civil_war", "famine", "fiscal_policy"]


# ===========================================================================
# load_l1_mapping — fallback behavior
# ===========================================================================

def test_load_l1_mapping_returns_empty_when_file_missing(monkeypatch, tmp_path):
    """When the L1 mapping JSON doesn't exist, the helper returns {}
    (not an error) so smoke tests don't depend on it."""
    monkeypatch.setattr(mod, "L1_MAPPING_JSON", tmp_path / "nonexistent.json")
    result = mod.load_l1_mapping()
    assert result == {}


def test_load_l1_mapping_loads_existing_file(monkeypatch, tmp_path):
    p = tmp_path / "l1.json"
    p.write_text('{"mapping": {"cat_01": "sec_0", "cat_02": "sec_1"}}', encoding="utf-8")
    monkeypatch.setattr(mod, "L1_MAPPING_JSON", p)
    result = mod.load_l1_mapping()
    assert result == {"cat_01": "sec_0", "cat_02": "sec_1"}


# ===========================================================================
# CLI — argument parsing without invoking PyMC
# ===========================================================================

def test_cli_requires_one_mode():
    """Argparse should reject calls with neither --smoke nor --prep-only."""
    with pytest.raises(SystemExit):
        mod._main([])


def test_cli_rejects_both_modes():
    with pytest.raises(SystemExit):
        mod._main(["--smoke", "--prep-only"])


# ===========================================================================
# compute_diagnostics — F-1 + J-§3.1 extensions (no NUTS; hand-built idata)
#
# These tests build a minimal arviz InferenceData by hand so we can exercise
# compute_diagnostics() without invoking PyMC sampling. They run in pytest
# (default Python env) because arviz is light enough to be available in the
# default env, but they DO import arviz — guarded with importorskip so CI
# without arviz installed degrades gracefully.
# ===========================================================================

def _build_mock_idata(*, n_chains: int = 2, n_draws: int = 100,
                      tree_depth_values: list[int] | None = None,
                      n_divergences: int = 0):
    """Build a minimal arviz InferenceData carrying just enough structure
    for compute_diagnostics to exercise. PyMC's actual idata has many more
    groups, but compute_diagnostics only reads:
      - posterior (var_names indexed)
      - sample_stats.draw / .chain / .diverging / .tree_depth / .energy

    Note: R-hat and n_eff are derived from the posterior values, not passed
    in — arviz.summary() computes them. Future test authors exercising FAIL
    branches for those diagnostics should construct posterior arrays that
    produce the target r_hat/ess_bulk (e.g., chain-correlated draws).
    """
    az = pytest.importorskip("arviz")
    xr = pytest.importorskip("xarray")

    posterior = {}
    for var in mod.DIAGNOSTIC_VAR_NAMES:
        # Per-var posterior: shape (chain, draw). Drawn from a tight
        # normal so summary stats look healthy by default.
        posterior[var] = xr.DataArray(
            np.random.default_rng(42).normal(0, 1, size=(n_chains, n_draws)),
            dims=["chain", "draw"],
        )
    posterior_ds = xr.Dataset(posterior)

    tree_depth_arr = (
        np.full((n_chains, n_draws), tree_depth_values, dtype=int)
        if isinstance(tree_depth_values, int)
        else np.array(tree_depth_values).reshape(n_chains, n_draws)
        if tree_depth_values is not None
        else np.full((n_chains, n_draws), 8, dtype=int)  # well below max_treedepth=12
    )
    sample_stats = xr.Dataset({
        "diverging": xr.DataArray(
            np.concatenate([
                np.ones(n_divergences, dtype=int),
                np.zeros(n_chains * n_draws - n_divergences, dtype=int),
            ]).reshape(n_chains, n_draws),
            dims=["chain", "draw"],
        ),
        "tree_depth": xr.DataArray(tree_depth_arr, dims=["chain", "draw"]),
        # arviz.bfmi() needs `energy` to compute E-BFMI. Use a mildly-noisy
        # series so the per-chain BFMI is well-defined and > 0.3 by default.
        "energy": xr.DataArray(
            np.random.default_rng(43).normal(100, 1, size=(n_chains, n_draws)),
            dims=["chain", "draw"],
        ),
    })
    return az.InferenceData(posterior=posterior_ds, sample_stats=sample_stats)


def test_compute_diagnostics_emits_treedepth_saturation_fields():
    """J-§3.1: compute_diagnostics must emit max_observed_treedepth,
    n_treedepth_saturated, treedepth_saturation_rate, and a verdict."""
    pytest.importorskip("arviz")
    pytest.importorskip("xarray")
    idata = _build_mock_idata(tree_depth_values=8)  # well below MAX_TREEDEPTH
    diag = mod.compute_diagnostics(idata)
    assert "max_observed_treedepth" in diag
    assert "n_treedepth_saturated" in diag
    assert "treedepth_saturation_rate" in diag
    assert "treedepth_saturation" in diag["verdicts"]
    # Healthy run: depth=8 < max_treedepth=12 → no saturation
    assert diag["max_observed_treedepth"] == 8
    assert diag["n_treedepth_saturated"] == 0
    assert diag["treedepth_saturation_rate"] == 0.0
    assert diag["verdicts"]["treedepth_saturation"] == "PASS"


def test_compute_diagnostics_flags_treedepth_saturation_at_threshold():
    """J-§3.1: > 1 % saturated → FAIL verdict."""
    pytest.importorskip("arviz")
    pytest.importorskip("xarray")
    # 2 chains × 100 draws = 200 total. Saturate 3 of them = 1.5 % > 1 %.
    saturated = [12] * 3 + [8] * 197
    idata = _build_mock_idata(tree_depth_values=saturated)
    diag = mod.compute_diagnostics(idata)
    assert diag["n_treedepth_saturated"] == 3
    assert diag["treedepth_saturation_rate"] == 0.015
    assert diag["verdicts"]["treedepth_saturation"] == "FAIL"


def test_compute_diagnostics_var_names_in_gate_defaults_to_all_9():
    """F-1: by default, compute_diagnostics gates ALL 9 sampled RVs.
    The output dict carries `var_names_in_gate` for audit-trail purposes."""
    pytest.importorskip("arviz")
    pytest.importorskip("xarray")
    idata = _build_mock_idata()
    diag = mod.compute_diagnostics(idata)
    assert set(diag["var_names_in_gate"]) == set(mod.DIAGNOSTIC_VAR_NAMES)
    # And specifically the funnel-failure site:
    assert "country_intercept_raw" in diag["var_names_in_gate"]


def test_compute_diagnostics_var_names_override():
    """F-1: callers can override var_names (e.g., for narrower diagnostic
    sweeps) but the override is recorded in the output for audit traceability."""
    pytest.importorskip("arviz")
    pytest.importorskip("xarray")
    idata = _build_mock_idata()
    # Use a SUBSET of the default vars — arviz will only summarise those.
    custom = ("mu", "tau_arm")
    diag = mod.compute_diagnostics(idata, var_names=custom)
    assert tuple(diag["var_names_in_gate"]) == custom


def test_compute_diagnostics_treedepth_missing_fails_safe():
    """If sample_stats has no tree_depth (older PyMC backend), the
    treedepth verdict is FAIL — better to halt than fly blind."""
    az = pytest.importorskip("arviz")
    xr = pytest.importorskip("xarray")
    # Build idata WITHOUT tree_depth
    posterior = {
        var: xr.DataArray(np.zeros((2, 50)), dims=["chain", "draw"])
        for var in mod.DIAGNOSTIC_VAR_NAMES
    }
    sample_stats = xr.Dataset({
        "diverging": xr.DataArray(np.zeros((2, 50), dtype=int), dims=["chain", "draw"]),
        "energy": xr.DataArray(
            np.random.default_rng(43).normal(100, 1, size=(2, 50)),
            dims=["chain", "draw"],
        ),
    })
    idata = az.InferenceData(
        posterior=xr.Dataset(posterior),
        sample_stats=sample_stats,
    )
    diag = mod.compute_diagnostics(idata)
    assert diag["max_observed_treedepth"] == -1
    assert diag["n_treedepth_saturated"] == -1
    assert np.isnan(diag["treedepth_saturation_rate"])
    assert diag["verdicts"]["treedepth_saturation"] == "FAIL"
