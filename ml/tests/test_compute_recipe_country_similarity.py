"""Unit tests for the #111 nowcast-fill rewrite of compute_recipe_country_similarity.

Pure-function coverage (no IO except a tmp positives.csv for the canonical builder):
  - extract_country_trajectory: default return type is unchanged (back-compat)
  - trailing LOCF fill: carries last observed z forward; flags the tail; band fans
    out as sqrt(horizon); flat series hits the floor; honours the stale-anchor cap
  - FIREWALL (JH-R1): at a historical eval year (frontier already observed) there
    is NO fill — byte-identical to v1 — and the canonical builder never fills
  - compute_country_recipe_similarity_with_fill: point score is byte-identical to
    the base estimator; MC band is ordered + in [0,100] + seed-deterministic;
    zone_stability_pct in [0,100]
  - K-R1: HIGH-depends-on-fill flag fires iff full=HIGH and observed-only!=HIGH,
    and blocks auto_publish_high
  - _drop_predicted: discards is_predicted rows; no-op when the column is absent
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import compute_recipe_country_similarity as crs  # noqa: E402
from compute_recipe_country_similarity import (  # noqa: E402
    CountryTrajectory,
    compute_country_recipe_similarity,
    compute_country_recipe_similarity_with_fill,
    extract_country_trajectory,
    _drop_predicted,
    _observed_only_similarity,
    _zone_of,
    _Z_CRIT,
    _FLAT_SERIES_FLOOR_Z,
    _MAX_FILL_HORIZON_YEARS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _one_country_panel(country: str, year_value: dict[int, float],
                       is_predicted: dict[int, bool] | None = None) -> pd.DataFrame:
    """Build a single-country panel from {year: value}."""
    rows = []
    for yr, val in year_value.items():
        row = {"country": country, "year": yr, "value": val}
        if is_predicted is not None:
            row["is_predicted"] = is_predicted.get(yr, False)
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# _drop_predicted (D1)
# ---------------------------------------------------------------------------


def test_drop_predicted_removes_predicted_rows():
    panel = _one_country_panel(
        "X", {2018: 1.0, 2019: 2.0, 2020: 3.0},
        is_predicted={2018: False, 2019: True, 2020: True},
    )
    out = _drop_predicted(panel)
    assert set(out["year"]) == {2018}
    assert out["value"].tolist() == [1.0]


def test_drop_predicted_noop_without_column():
    panel = _one_country_panel("X", {2018: 1.0, 2019: 2.0})
    out = _drop_predicted(panel)
    assert len(out) == 2  # unchanged when no is_predicted column


# ---------------------------------------------------------------------------
# extract_country_trajectory — back-compat default return
# ---------------------------------------------------------------------------


def test_default_return_is_ndarray_backcompat():
    """Without return_provenance, the function returns a plain (W,) ndarray —
    the contract every existing caller depends on."""
    panel = _one_country_panel("X", {y: float(y - 2000) for y in range(2005, 2021)})
    window = 10
    t = extract_country_trajectory(panel, "X", evaluation_year=2021, window=window)
    assert isinstance(t, np.ndarray)
    assert t.shape == (window,)
    assert np.all(np.isfinite(t))


def test_returns_none_for_unknown_country():
    panel = _one_country_panel("X", {2010: 1.0, 2011: 2.0})
    assert extract_country_trajectory(panel, "Nowhere", 2021, 10) is None


def test_returns_none_when_too_few_observations():
    # Only 2 observed points in the window; threshold is max(3, window//3)=3
    panel = _one_country_panel("X", {2018: 1.0, 2019: 2.0})
    assert extract_country_trajectory(panel, "X", 2021, 9) is None


# ---------------------------------------------------------------------------
# Trailing LOCF fill behaviour
# ---------------------------------------------------------------------------


def test_trailing_locf_carries_last_observed_forward():
    """Window ends after the last observed year → the gap is LOCF-filled with
    the last observed z, flagged, and the observed run is untouched."""
    # Observed 2010-2018; window [2015, 2024]; frontier 2024 → 2019-2024 filled.
    panel = _one_country_panel("X", {y: float(y - 2000) for y in range(2010, 2019)})
    window = 10
    traj = extract_country_trajectory(panel, "X", evaluation_year=2025, window=window,
                                      return_provenance=True)
    assert isinstance(traj, CountryTrajectory)
    years = np.arange(2015, 2025)
    expected_filled = years > 2018
    np.testing.assert_array_equal(traj.filled_mask, expected_filled)
    np.testing.assert_array_equal(traj.observed_mask, ~expected_filled)
    assert traj.n_filled == 6
    assert traj.last_observed_year == 2018
    assert traj.frontier_year == 2024
    # All filled points equal the z at the last observed index.
    last_obs_idx = int(np.flatnonzero(years == 2018)[0])
    anchor = traj.z[last_obs_idx]
    assert np.allclose(traj.z[traj.filled_mask], anchor)


def test_fill_band_fans_out_as_sqrt_horizon():
    panel = _one_country_panel("X", {y: float(y - 2000) for y in range(2010, 2019)})
    traj = extract_country_trajectory(panel, "X", 2025, 10, return_provenance=True)
    band_filled = traj.band_half_z[traj.filled_mask]
    # strictly increasing with horizon
    assert np.all(np.diff(band_filled) > 0)
    # ratio of consecutive half-widths follows sqrt(h+1)/sqrt(h)
    ratio = band_filled[1] / band_filled[0]
    assert abs(ratio - np.sqrt(2.0)) < 1e-9
    # observed points carry zero band
    assert np.allclose(traj.band_half_z[traj.observed_mask], 0.0)


def test_flat_series_hits_floor():
    """A perfectly flat series has sd(Δz)=0 → the band uses the floor, so the
    fill never claims zero uncertainty."""
    panel = _one_country_panel("X", {y: 5.0 for y in range(2010, 2019)})
    traj = extract_country_trajectory(panel, "X", 2025, 10, return_provenance=True)
    first_fill = traj.band_half_z[traj.filled_mask][0]
    # h=1 → half = Z_CRIT * floor * sqrt(1)
    assert abs(first_fill - _Z_CRIT * _FLAT_SERIES_FLOOR_Z) < 1e-9


def test_stale_anchor_when_gap_exceeds_cap():
    panel = _one_country_panel("X", {y: float(y - 2000) for y in range(2010, 2019)})
    # frontier 2024, last obs 2018 → gap 6 > 5 → stale
    traj = extract_country_trajectory(panel, "X", 2025, 15, return_provenance=True)
    assert (2024 - 2018) > _MAX_FILL_HORIZON_YEARS
    assert traj.stale_anchor is True


def test_no_stale_anchor_when_gap_within_cap():
    panel = _one_country_panel("X", {y: float(y - 2000) for y in range(2010, 2021)})
    # frontier 2021, last obs 2020 → gap 1 ≤ 5
    traj = extract_country_trajectory(panel, "X", 2022, 10, return_provenance=True)
    assert traj.stale_anchor is False


# ---------------------------------------------------------------------------
# FIREWALL (JH-R1): no fill at a historical eval year
# ---------------------------------------------------------------------------


def test_no_fill_at_historical_eval_year_is_byte_identical():
    """When the frontier (eval_year-1) is itself observed, there is no trailing
    gap → n_filled=0, every point observed, and the z-vector equals the plain
    (mean-fill-free) formula. This is the property that keeps validation/LOCO
    folds free of any filled row."""
    yv = {y: float((y - 2000) ** 1.1) for y in range(2000, 2017)}
    panel = _one_country_panel("X", yv)
    window = 10
    eval_year = 2017  # frontier 2016 is observed
    traj = extract_country_trajectory(panel, "X", eval_year, window, return_provenance=True)
    assert traj.n_filled == 0
    assert bool(traj.filled_mask.any()) is False
    assert bool(traj.observed_mask.all()) is True
    # default-return path yields the same z-vector
    z_plain = extract_country_trajectory(panel, "X", eval_year, window)
    np.testing.assert_array_equal(traj.z, z_plain)


def test_canonical_builder_ignores_predicted_rows(tmp_path, monkeypatch):
    """build_canonical_profile_from_walk operates on the panels it is given; the
    production path feeds it _drop_predicted panels. Adding future is_predicted
    rows and then dropping them must not change the canonical (firewall)."""
    recipe_id = "firewalltest"
    d = tmp_path / "data" / "shape_inputs_v2" / recipe_id
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([("alpha", 2010), ("beta", 2011)],
                 columns=["country_id", "event_year"]).to_csv(d / "positives.csv", index=False)
    monkeypatch.setattr(crs, "REPO_ROOT", tmp_path)

    recs = []
    for cname in ("Alpha", "Beta"):
        base = 1.0 if cname == "Alpha" else 5.0
        for yr in range(1995, 2013):
            recs.append({"country": cname, "year": yr, "value": base + 0.2 * (yr - 1995),
                         "is_predicted": False})
    observed_panel = pd.DataFrame(recs)
    # A panel that ALSO carries future predicted rows
    future = pd.DataFrame([{"country": "Alpha", "year": yr, "value": 99.0, "is_predicted": True}
                           for yr in range(2013, 2026)])
    with_pred = pd.concat([observed_panel, future], ignore_index=True)

    walk = {"recipe_id": recipe_id}
    window = 5
    canon_observed = crs.build_canonical_profile_from_walk(
        walk, {"IND_X": observed_panel}, window, ["IND_X"])
    canon_dropped = crs.build_canonical_profile_from_walk(
        walk, {"IND_X": _drop_predicted(with_pred)}, window, ["IND_X"])
    np.testing.assert_allclose(canon_observed["IND_X"], canon_dropped["IND_X"], rtol=1e-12)


# ---------------------------------------------------------------------------
# compute_country_recipe_similarity_with_fill
# ---------------------------------------------------------------------------


def _traj(z, observed_mask, filled_mask=None, band_half_z=None, stale=False):
    z = np.asarray(z, dtype=float)
    observed_mask = np.asarray(observed_mask, dtype=bool)
    if filled_mask is None:
        filled_mask = ~observed_mask
    filled_mask = np.asarray(filled_mask, dtype=bool)
    if band_half_z is None:
        band_half_z = np.where(filled_mask, 0.5, 0.0)
    return CountryTrajectory(
        z=z, observed_mask=observed_mask, filled_mask=filled_mask,
        band_half_z=np.asarray(band_half_z, dtype=float),
        n_filled=int(filled_mask.sum()), last_observed_year=2020,
        frontier_year=2024, stale_anchor=stale,
    )


def test_point_score_byte_identical_to_base():
    canonical = {"IND": np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])}
    shap = {"IND": 1.0}
    traj = {"IND": _traj([0, 0, 1, 1, 1, 1], [True, True, True, False, False, False])}
    base = compute_country_recipe_similarity({"IND": traj["IND"].z}, canonical, shap)
    withfill = compute_country_recipe_similarity_with_fill(traj, canonical, shap, mc_draws=200, seed=0)
    assert withfill["risk_score"] == base["risk_score"]
    assert withfill["zone"] == base["zone"]
    assert "fill" in withfill


def test_high_depends_on_fill_flag_fires():
    """Observed run alone aligns with a flat (zero) canonical head → MODERATE;
    the LOCF tail pushes alignment into the crisis run-up → HIGH. K-R1 must flag
    it and block auto-publish."""
    canonical = {"IND": np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])}
    shap = {"IND": 1.0}
    traj = {"IND": _traj([0, 0, 1, 1, 1, 1], [True, True, True, False, False, False])}
    r = compute_country_recipe_similarity_with_fill(traj, canonical, shap, mc_draws=200, seed=0)
    assert r["zone"] == "HIGH"
    assert r["fill"]["observed_only_zone"] != "HIGH"
    assert r["fill"]["high_depends_on_fill"] is True
    assert r["fill"]["auto_publish_high"] is False


def test_high_not_depends_on_fill_allows_auto_publish():
    """Fully observed HIGH (no fill) → observed-only also HIGH → auto-publish allowed."""
    canonical = {"IND": np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])}
    shap = {"IND": 1.0}
    traj = {"IND": _traj([0, 0, 1, 1, 1, 1], [True] * 6, filled_mask=[False] * 6,
                         band_half_z=[0.0] * 6)}
    r = compute_country_recipe_similarity_with_fill(traj, canonical, shap, mc_draws=100, seed=0)
    assert r["zone"] == "HIGH"
    assert r["fill"]["is_predicted"] is False
    assert r["fill"]["high_depends_on_fill"] is False
    assert r["fill"]["auto_publish_high"] is True


def test_fill_band_ordered_and_bounded():
    canonical = {"IND": np.array([0.0, 0.5, 1.0, 1.0, 1.0, 1.0])}
    shap = {"IND": 1.0}
    traj = {"IND": _traj([0.2, 0.4, 0.8, 0.8, 0.8, 0.8],
                         [True, True, True, False, False, False],
                         band_half_z=[0, 0, 0, 0.49, 0.69, 0.85])}
    r = compute_country_recipe_similarity_with_fill(traj, canonical, shap, mc_draws=2000, seed=42)
    b = r["fill"]["fill_band"]
    assert b["ci95_lo"] <= b["ci80_lo"] + 1e-9
    assert b["ci80_lo"] <= b["ci80_hi"] + 1e-9
    assert b["ci80_hi"] <= b["ci95_hi"] + 1e-9
    for k in ("ci80_lo", "ci80_hi", "ci95_lo", "ci95_hi", "mc_mean"):
        assert 0.0 <= b[k] <= 100.0
    assert 0.0 <= b["zone_stability_pct"] <= 100.0
    assert b["mc_draws"] == 2000


def test_fill_band_seed_deterministic():
    canonical = {"IND": np.array([0.0, 0.5, 1.0, 1.0])}
    shap = {"IND": 1.0}
    traj = {"IND": _traj([0.1, 0.5, 0.5, 0.5], [True, True, False, False],
                         band_half_z=[0, 0, 0.49, 0.69])}
    a = compute_country_recipe_similarity_with_fill(traj, canonical, shap, mc_draws=500, seed=7)
    b = compute_country_recipe_similarity_with_fill(traj, canonical, shap, mc_draws=500, seed=7)
    assert a["fill"]["fill_band"] == b["fill"]["fill_band"]


def test_no_fill_gives_collapsed_band_and_full_stability():
    canonical = {"IND": np.array([0.0, 0.5, 1.0, 1.0])}
    shap = {"IND": 1.0}
    traj = {"IND": _traj([0.1, 0.5, 0.9, 1.0], [True] * 4, filled_mask=[False] * 4,
                         band_half_z=[0.0] * 4)}
    r = compute_country_recipe_similarity_with_fill(traj, canonical, shap, mc_draws=1000, seed=0)
    b = r["fill"]["fill_band"]
    assert b["mc_draws"] == 0
    assert b["ci80_lo"] == b["ci95_hi"] == r["risk_score"]
    assert b["zone_stability_pct"] == 100.0


# ---------------------------------------------------------------------------
# _observed_only_similarity + _zone_of
# ---------------------------------------------------------------------------


def test_observed_only_drops_filled_positions():
    canonical = {"IND": np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])}
    shap = {"IND": 1.0}
    traj = {"IND": _traj([0, 0, 1, 1, 1, 1], [True, True, True, False, False, False])}
    obs = _observed_only_similarity(traj, canonical, shap)
    # observed positions [0,1,2] = [0,0,1] vs canonical[0:3]=[0,0,0] → zero canon → cosine 0
    assert abs(obs["cosine_S"] - 0.0) < 1e-12
    assert obs["zone"] == "MODERATE"  # score 50


def test_zone_of_boundaries():
    assert _zone_of(0.0) == "LOW"
    assert _zone_of(39.9) == "LOW"
    assert _zone_of(40.0) == "MODERATE"
    assert _zone_of(64.9) == "MODERATE"
    assert _zone_of(65.0) == "HIGH"
    assert _zone_of(100.0) == "HIGH"


def test_observed_only_returns_moderate_when_too_few_observed():
    """Edge case (review item 6): when no indicator has ≥2 observed points, the
    observed-only diagnostic falls back to S=0 → score 50 → MODERATE. This is a
    'no meaningful counterfactual' state, not 'fill pushed it to HIGH' — the K-R1
    flag still fires correctly (MODERATE != HIGH) but for this reason."""
    canonical = {"IND": np.array([0.0, 0.0, 1.0, 1.0])}
    shap = {"IND": 1.0}
    # only 1 observed point in the window
    traj = {"IND": _traj([0, 1, 1, 1], [False, True, False, False],
                         filled_mask=[False, False, True, True])}
    obs = _observed_only_similarity(traj, canonical, shap)
    assert obs["zone"] == "MODERATE"
    assert abs(obs["risk_score"] - 50.0) < 1e-9


# ---------------------------------------------------------------------------
# Review followups (#111 QA review): firewall assertion, back-compat under
# active fill, multi-indicator divergent coverage, prebake D1 coverage
# ---------------------------------------------------------------------------


def test_forbid_fill_raises_when_trailing_fill_would_activate():
    """JH-R1 firewall mechanism (review item 2): callers in a training/validation
    fold pass forbid_fill=True; a trailing gap then fails loudly."""
    panel = _one_country_panel("X", {y: float(y - 2000) for y in range(2010, 2019)})
    with pytest.raises(RuntimeError, match="JH-R1 firewall"):
        extract_country_trajectory(panel, "X", 2025, 10, return_provenance=True, forbid_fill=True)


def test_forbid_fill_noop_at_historical_year():
    """forbid_fill is inert when the frontier is already observed (no fill)."""
    panel = _one_country_panel("X", {y: float(y - 2000) for y in range(2005, 2017)})
    t = extract_country_trajectory(panel, "X", 2017, 10, return_provenance=True, forbid_fill=True)
    assert isinstance(t, CountryTrajectory)
    assert t.n_filled == 0


def test_default_return_path_under_active_fill_is_plain_ndarray():
    """Back-compat guarantee the 7 callers rely on (review item 7): even when the
    trailing gap activates LOCF, return_provenance=False yields a plain ndarray
    (LOCF applied), NOT a CountryTrajectory."""
    panel = _one_country_panel("X", {y: float(y - 2000) for y in range(2010, 2019)})
    z = extract_country_trajectory(panel, "X", 2025, 10)  # default return
    assert isinstance(z, np.ndarray)
    assert z.shape == (10,)
    # tail carried forward → last 6 points equal the last observed z (2018)
    traj = extract_country_trajectory(panel, "X", 2025, 10, return_provenance=True)
    np.testing.assert_array_equal(z, traj.z)
    assert traj.n_filled == 6  # fill DID activate


def test_multi_indicator_stale_anchor_blocks_auto_publish():
    """Review item 5: a recipe with divergent per-indicator coverage — one fresh,
    one stale — must surface stale_anchor in the aggregate and block auto-publish."""
    canonical = {"A": np.array([0.0, 0.5, 1.0, 1.0]), "B": np.array([0.0, 0.5, 1.0, 1.0])}
    shap = {"A": 0.5, "B": 0.5}
    fresh = _traj([0.0, 0.5, 1.0, 1.0], [True, True, True, True],
                  filled_mask=[False] * 4, band_half_z=[0.0] * 4)        # no fill
    stale = _traj([0.0, 1.0, 1.0, 1.0], [True, True, False, False],
                  filled_mask=[False, False, True, True],
                  band_half_z=[0, 0, 0.5, 0.7], stale=True)              # stale fill
    r = compute_country_recipe_similarity_with_fill({"A": fresh, "B": stale},
                                                    canonical, shap, mc_draws=200, seed=0)
    assert r["fill"]["stale_anchor"] is True
    assert r["fill"]["auto_publish_high"] is False
    assert r["fill"]["per_indicator"]["A"]["stale_anchor"] is False
    assert r["fill"]["per_indicator"]["B"]["stale_anchor"] is True


def test_prebake_drops_predicted_rows(tmp_path):
    """D1 coverage (review items 4/8): prebake_zscore_distribution must compute the
    panel-wide distribution from observed rows only, ignoring is_predicted rows."""
    ind = "IND_P"
    d = tmp_path / ind
    d.mkdir(parents=True, exist_ok=True)
    rows = []
    for ci in range(12):
        rows.append({"country": f"C{ci}", "year": 2020, "value": 1.0, "is_predicted": False})
    # add extreme predicted rows that must NOT affect the distribution
    for ci in range(12):
        rows.append({"country": f"C{ci}", "year": 2020, "value": 999.0, "is_predicted": True})
    pd.DataFrame(rows).to_parquet(d / f"{ind}.parquet")
    dist = crs.prebake_zscore_distribution(tmp_path, [ind], evaluation_year=2021)
    # observed values are all 1.0 → mean 1.0, n_countries 12 (predicted rows excluded)
    assert dist[ind]["n_countries"] == 12
    assert abs(dist[ind]["mean"] - 1.0) < 1e-9
