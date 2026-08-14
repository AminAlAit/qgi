"""Bit-identity tests for the #129 (FLEET-PERF) per-(indicator,country,year,window) feature
memo in build_X_y.

The §2.5 contract: caching changes ONLY speed, never the walk's selected indicators / windows /
AUCs. The cache is sound iff a cached feature vector is byte-equal to a freshly-computed one —
which holds because extract_features_for_indicator is a pure deterministic function of exactly
(indicator, country, year, window), independent of the selected set. These tests prove that on
the REAL build_X_y + extract_features_for_indicator (no monkeypatch): cache-on == cache-off,
warm-cache == cold-cache, and a cache shared across growing selected sets stays correct. The
end-to-end §2.5 confirmation is the canary re-run; this is the unit-level proof.

No IO, no panels-on-disk, no AWS.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_f_ml_1_poc as drv  # noqa: E402


def _make_panel(seed: int, n_countries: int = 14, year0: int = 1995, n_years: int = 28):
    """A deterministic indicator panel (columns country/year/value). Distinct per `seed`
    so different indicators carry different signals; enough countries (≥10) to exercise the
    cross-country z-score path and enough years to fill the longest window."""
    rng = np.random.default_rng(seed)
    rows = []
    for ci in range(n_countries):
        base = rng.normal(seed + ci, 1.0)
        for yi in range(n_years):
            year = year0 + yi
            val = base + 0.1 * yi + rng.normal(0.0, 0.5)
            rows.append({"country": f"C{ci:02d}", "year": year, "value": float(val)})
    import pandas as pd
    return pd.DataFrame(rows)


def _make_samples():
    import pandas as pd
    # a spread of (country, year, label); years late enough that all windows have history
    recs = [("C00", 2018, 1), ("C01", 2019, 0), ("C02", 2017, 1), ("C03", 2020, 0),
            ("C04", 2018, 1), ("C05", 2019, 0), ("C06", 2021, 1), ("C07", 2016, 0),
            ("C08", 2018, 0), ("C09", 2019, 1), ("C10", 2020, 0), ("C11", 2017, 1)]
    return pd.DataFrame(recs, columns=["country", "year", "label"])


def _panels(inds):
    return {ind: _make_panel(seed=i + 1) for i, ind in enumerate(inds)}


def _assert_quad_equal(a, b):
    """Exact equality of (X, y, countries, years), treating NaN as equal (assert_array_equal)."""
    for left, right in zip(a, b):
        np.testing.assert_array_equal(np.asarray(left), np.asarray(right))


def test_cache_off_equals_cache_on():
    """THE core guarantee: build_X_y with a cache == build_X_y without one, byte-for-byte."""
    inds = ["i1", "i2", "i3"]
    panels = _panels(inds)
    samples = _make_samples()
    for win in (5, 10, 15, 20):
        no_cache = drv.build_X_y(samples, inds, win, panels)
        cache = {}
        with_cache = drv.build_X_y(samples, inds, win, panels, feat_cache=cache)
        _assert_quad_equal(no_cache, with_cache)
        assert len(cache) > 0  # the cache actually populated


def test_warm_cache_equals_cold_cache():
    """Second call against an already-warm cache (all hits) is identical to the first (all misses)."""
    inds = ["i1", "i2"]
    panels = _panels(inds)
    samples = _make_samples()
    cache = {}
    cold = drv.build_X_y(samples, inds, 12, panels, feat_cache=cache)
    n_after_cold = len(cache)
    warm = drv.build_X_y(samples, inds, 12, panels, feat_cache=cache)  # all hits now
    _assert_quad_equal(cold, warm)
    assert len(cache) == n_after_cold  # no new entries on the warm pass → every lookup hit


def test_cache_shared_across_growing_selected_sets():
    """Greedy reuses ONE cache as the selected set grows (+ candidates). A set that reuses
    cached single-indicator columns must equal a fresh from-scratch build of the same set."""
    inds = ["i1", "i2", "i3"]
    panels = _panels(inds)
    samples = _make_samples()
    cache = {}
    drv.build_X_y(samples, ["i1"], 10, panels, feat_cache=cache)            # warm i1@10
    drv.build_X_y(samples, ["i1", "i2"], 10, panels, feat_cache=cache)      # warm i1,i2@10
    shared = drv.build_X_y(samples, ["i1", "i2", "i3"], 10, panels, feat_cache=cache)
    fresh = drv.build_X_y(samples, ["i1", "i2", "i3"], 10, panels)          # no cache
    _assert_quad_equal(shared, fresh)


def test_cache_keys_are_indicator_country_year_window():
    """The memo key contract: (indicator, country, year, window). A different window for the
    same (indicator,country,year) is a DISTINCT entry (no cross-window contamination)."""
    inds = ["i1"]
    panels = _panels(inds)
    samples = _make_samples()
    cache = {}
    drv.build_X_y(samples, inds, 5, panels, feat_cache=cache)
    keys_w5 = set(cache)
    assert all(k[0] == "i1" and k[3] == 5 for k in keys_w5)
    drv.build_X_y(samples, inds, 10, panels, feat_cache=cache)
    keys_w10 = set(cache) - keys_w5
    assert keys_w10 and all(k[3] == 10 for k in keys_w10)  # window-5 entries untouched, new w10 added


def test_cached_none_is_honored_not_recomputed_into_other_branch():
    """FU-1 (QA PR review #121): exercise the `feat_cache[key] is None` branch — a stored
    `None` (insufficient data) must drop the row identically with a cold and a pre-warmed cache.
    Build a panel where ONE country has only 2 years of data before the sample year (less than
    the window-5 minimum of max(3, 5//3)=3 → extract returns None → row is skipped). Same skip
    behaviour with or without the cache, AND with the None already cached."""
    import pandas as pd
    # i1: rich panel for all countries. i2: only 2 years for "C00" (forces None at win=5).
    inds = ["i1", "i2"]
    panels = {
        "i1": _make_panel(seed=1, n_countries=12, year0=2000, n_years=20),
        "i2": pd.concat([
            pd.DataFrame([{"country": "C00", "year": y, "value": 0.5} for y in (2014, 2015)]),
            pd.DataFrame([{"country": f"C{ci:02d}", "year": 2000 + yi, "value": 0.1 * yi}
                          for ci in range(1, 12) for yi in range(20)]),
        ], ignore_index=True),
    }
    samples = pd.DataFrame([("C00", 2018, 1), ("C01", 2018, 0), ("C02", 2018, 1),
                            ("C03", 2018, 0), ("C04", 2018, 1), ("C05", 2018, 0)],
                           columns=["country", "year", "label"])
    # The None precondition: i2 at (C00, 2018, win=5) MUST be None.
    assert drv.extract_features_for_indicator(panels["i2"], "C00", 2018, 5) is None

    no_cache = drv.build_X_y(samples, inds, 5, panels)
    cache = {}
    cold = drv.build_X_y(samples, inds, 5, panels, feat_cache=cache)
    _assert_quad_equal(no_cache, cold)
    # The None was stored and is honored on a warm pass (this is the dead-branch coverage).
    assert cache[("i2", "C00", 2018, 5)] is None
    warm = drv.build_X_y(samples, inds, 5, panels, feat_cache=cache)
    _assert_quad_equal(cold, warm)
    # And C00 was dropped from the output (the None routes through `if f is None: skip=True`).
    assert "C00" not in no_cache[2].tolist() and "C00" not in cold[2].tolist()


def test_cache_value_matches_direct_extraction():
    """A cached vector equals a direct extract_features_for_indicator call for the same key —
    the purity claim the whole optimization rests on."""
    inds = ["i1", "i2"]
    panels = _panels(inds)
    samples = _make_samples()
    cache = {}
    drv.build_X_y(samples, inds, 8, panels, feat_cache=cache)
    for (ind, country, year, win), cached in cache.items():
        direct = drv.extract_features_for_indicator(panels[ind], country, year, win)
        if cached is None:
            assert direct is None
        else:
            np.testing.assert_array_equal(cached, direct)
