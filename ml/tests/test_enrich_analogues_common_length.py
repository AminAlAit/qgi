"""Unit tests for enrich_analogues_common_length.py pure functions.

Covers:
  - best_common_length() — picks L maximizing event-end-aligned coverage
  - pick_analogue_window() — selects the best window for a given target L

Skipped:
  - enrich() — reads/writes JSON files on disk (pair-windows/ dir +
    analogues-enriched.json). File I/O gated; skip per #373 scope.

#373 script test coverage audit.
"""
from __future__ import annotations

import sys
import pathlib
from unittest.mock import patch

import pytest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import enrich_analogues_common_length as eacl  # noqa: E402

# Pin CURRENT_YEAR to a stable value so future-date guards don't flap.
FIXED_YEAR = 2026


# ===========================================================================
# Helpers
# ===========================================================================

def _win(l, sb, sa=1980, pps=0.5, ac=0.8):
    """Compact window dict matching the compact schema from generate_pair_windows.py."""
    return {"l": l, "sb": sb, "sa": sa, "pps": pps, "ac": ac, "ic": 10}


def _analogue(country_b_id, event_year_b):
    return {"country_b_id": country_b_id, "event_year_b": event_year_b}


# ===========================================================================
# best_common_length()
# ===========================================================================

class TestBestCommonLength:

    def test_single_analogue_single_window_returns_that_length(self):
        """One analogue with one valid window -> that window's length is returned."""
        pair_windows = {
            "1": {"top": [_win(20, 1990)]}
        }
        analogues = [_analogue(1, 2010)]  # sb+l = 1990+20 = 2010, exact end
        with patch.object(eacl, "CURRENT_YEAR", FIXED_YEAR):
            result = eacl.best_common_length(pair_windows, analogues)
        assert result == 20

    def test_two_analogues_same_length_wins(self):
        """Two analogues both with length 15 aligned -> 15 wins over 20."""
        pair_windows = {
            "1": {"top": [_win(15, 1995), _win(20, 1990)]},
            "2": {"top": [_win(15, 2000), _win(25, 1985)]},
        }
        analogues = [
            _analogue(1, 2010),   # L=15: sb+l=1995+15=2010 (exact)
            _analogue(2, 2015),   # L=15: sb+l=2000+15=2015 (exact)
        ]
        with patch.object(eacl, "CURRENT_YEAR", FIXED_YEAR):
            result = eacl.best_common_length(pair_windows, analogues)
        assert result == 15

    def test_empty_analogues_list_returns_none(self):
        result = eacl.best_common_length({}, [])
        assert result is None

    def test_no_pair_windows_data_returns_none(self):
        analogues = [_analogue(1, 2010)]
        result = eacl.best_common_length({}, analogues)
        assert result is None

    def test_analogue_without_country_b_id_skipped(self):
        """Analogues without country_b_id contribute no candidate lengths."""
        analogues = [{"event_year_b": 2010}]  # no country_b_id key
        result = eacl.best_common_length({}, analogues)
        assert result is None

    def test_coverage_tiebreak_by_pps(self):
        """When two lengths cover the same analogue count, pick higher-PPS one.

        To avoid cross-contamination from the ±2 length_tolerance (which would
        allow L=30's window to score for L=28's score_length call), we use
        lengths far enough apart (>2*tolerance) so each length's score_length
        only sees its own window.
        """
        # L=25 and L=30 are 5 apart (> 2*tol=4), so each window is only
        # eligible for its own candidate length when tolerance=2.
        pair_windows = {
            "1": {"top": [
                _win(25, 1985, pps=0.9),   # L=25: 1985+25=2010 exact, high PPS
                _win(30, 1980, pps=0.3),   # L=30: 1980+30=2010 exact, low PPS
            ]},
        }
        analogues = [_analogue(1, 2010)]
        with patch.object(eacl, "CURRENT_YEAR", FIXED_YEAR):
            result = eacl.best_common_length(pair_windows, analogues)
        # score_length(25) = (1, 0, 0.9), score_length(30) = (1, 0, 0.3)
        # -> L=25 wins on PPS tiebreak
        assert result == 25

    def test_future_dated_windows_excluded(self):
        """Windows whose sb+l > CURRENT_YEAR must not contribute."""
        pair_windows = {
            "1": {"top": [
                _win(20, FIXED_YEAR),   # sb+l = 2026+20 = 2046 — FUTURE, excluded
                _win(10, 2010),          # sb+l = 2010+10 = 2020 — OK
            ]}
        }
        analogues = [_analogue(1, 2020)]
        with patch.object(eacl, "CURRENT_YEAR", FIXED_YEAR):
            result = eacl.best_common_length(pair_windows, analogues)
        assert result == 10

    def test_tolerance_window_included(self):
        """L=20 with tolerance=2: a window of length 18 should still be considered."""
        pair_windows = {
            "1": {"top": [_win(18, 1992)]},  # |18-20|=2 <= tolerance=2
        }
        analogues = [_analogue(1, 2010)]  # sb+l = 1992+18 = 2010 exact
        with patch.object(eacl, "CURRENT_YEAR", FIXED_YEAR):
            result = eacl.best_common_length(pair_windows, analogues, length_tolerance=2)
        # Candidate lengths = {18}. L=18 aligns exactly to 2010. Returns 18.
        assert result == 18

    def test_zero_coverage_returns_none(self):
        """If the chosen L scores zero coverage on all tiers, return None."""
        # Window is future-dated, so eligible is empty after future guard.
        pair_windows = {
            "1": {"top": [_win(20, FIXED_YEAR + 10)]}
        }
        analogues = [_analogue(1, FIXED_YEAR + 30)]
        with patch.object(eacl, "CURRENT_YEAR", FIXED_YEAR):
            result = eacl.best_common_length(pair_windows, analogues)
        assert result is None

    def test_fallback_any_coverage_when_no_event_year(self):
        """When event_year_b is None, Tier-2 any_coverage path still picks an L."""
        pair_windows = {
            "1": {"top": [_win(25, 1985)]}
        }
        # event_year_b=None -> no end-alignment possible, any_cov path used
        analogues = [{"country_b_id": 1, "event_year_b": None}]
        with patch.object(eacl, "CURRENT_YEAR", FIXED_YEAR):
            result = eacl.best_common_length(pair_windows, analogues)
        # any_cov = 1 -> result is non-None
        assert result is not None


# ===========================================================================
# pick_analogue_window()
# ===========================================================================

class TestPickAnalogueWindow:

    def test_none_event_year_returns_none(self):
        windows = [_win(20, 1990)]
        with patch.object(eacl, "CURRENT_YEAR", FIXED_YEAR):
            result = eacl.pick_analogue_window(windows, 20, None)
        assert result is None

    def test_exact_end_alignment_selected(self):
        """sb + l == event_year_b → Tier 1 exact match."""
        # 1990 + 20 = 2010
        windows = [_win(20, 1990, pps=0.8)]
        with patch.object(eacl, "CURRENT_YEAR", FIXED_YEAR):
            result = eacl.pick_analogue_window(windows, 20, 2010)
        assert result is not None
        assert result["l"] == 20
        assert result["sb"] == 1990

    def test_near_end_alignment_within_tolerance(self):
        """sb + l within ±2 of event_year_b → Tier 2 near match."""
        # 1991 + 20 = 2011, event_year_b = 2010, diff = 1 <= 2
        windows = [_win(20, 1991, pps=0.6)]
        with patch.object(eacl, "CURRENT_YEAR", FIXED_YEAR):
            result = eacl.pick_analogue_window(windows, 20, 2010)
        assert result is not None
        assert result["sb"] == 1991

    def test_exact_beats_near(self):
        """Tier 1 (exact) wins over Tier 2 (near) even if near has higher PPS."""
        exact_win = _win(20, 1990, pps=0.5)  # 1990+20=2010 exact
        near_win = _win(20, 1991, pps=0.9)   # 1991+20=2011, near
        windows = [near_win, exact_win]
        with patch.object(eacl, "CURRENT_YEAR", FIXED_YEAR):
            result = eacl.pick_analogue_window(windows, 20, 2010)
        assert result["sb"] == 1990  # exact wins

    def test_future_dated_window_excluded(self):
        """Windows where sb + l > CURRENT_YEAR are skipped."""
        future_win = _win(20, FIXED_YEAR)  # 2026+20=2046 > 2026
        windows = [future_win]
        with patch.object(eacl, "CURRENT_YEAR", FIXED_YEAR):
            result = eacl.pick_analogue_window(windows, 20, FIXED_YEAR + 20)
        assert result is None

    def test_length_tolerance_respected(self):
        """Window with |l - target_L| > tolerance is excluded."""
        # target_L=20, tolerance=2: l=23 has diff=3 -> excluded
        windows = [_win(23, 1987, pps=0.9)]
        with patch.object(eacl, "CURRENT_YEAR", FIXED_YEAR):
            result = eacl.pick_analogue_window(windows, 20, 2010, length_tolerance=2)
        assert result is None

    def test_length_at_tolerance_boundary_included(self):
        """l=18, target_L=20, tolerance=2: |18-20|=2 exactly -> included."""
        windows = [_win(18, 1992, pps=0.7)]  # 1992+18=2010 exact
        with patch.object(eacl, "CURRENT_YEAR", FIXED_YEAR):
            result = eacl.pick_analogue_window(windows, 20, 2010, length_tolerance=2)
        assert result is not None
        assert result["l"] == 18

    def test_empty_windows_returns_none(self):
        with patch.object(eacl, "CURRENT_YEAR", FIXED_YEAR):
            result = eacl.pick_analogue_window([], 20, 2010)
        assert result is None

    def test_tier3_fallback_used_when_no_alignment_possible(self):
        """When no window end-aligns (pre-coverage event), best-PPS fallback used."""
        # event_year_b=1980, but all windows end at 2000+; no alignment possible
        windows = [
            _win(20, 1980, pps=0.3),  # 1980+20=2000
            _win(20, 1985, pps=0.7),  # 1985+20=2005
        ]
        with patch.object(eacl, "CURRENT_YEAR", FIXED_YEAR):
            result = eacl.pick_analogue_window(windows, 20, 1970)
        # Tier 3 fallback: best PPS among eligible = the pps=0.7 one
        assert result is not None
        assert result["sb"] == 1985

    def test_near_prefers_end_before_event(self):
        """When two near windows tie on distance, prefer end <= event_year_b."""
        before_win = _win(20, 1989, pps=0.5)  # 1989+20=2009, before 2010
        after_win = _win(20, 1991, pps=0.5)   # 1991+20=2011, after 2010
        windows = [after_win, before_win]
        with patch.object(eacl, "CURRENT_YEAR", FIXED_YEAR):
            result = eacl.pick_analogue_window(windows, 20, 2010)
        # before (ends 2009) vs after (ends 2011): before preferred
        assert result["sb"] == 1989

    def test_highest_pps_among_exact_matches_selected(self):
        """Multiple exact-aligned windows: highest PPS wins."""
        w1 = _win(20, 1990, pps=0.4)  # 1990+20=2010 exact
        w2 = _win(20, 1990, pps=0.9)  # same position, higher PPS
        windows = [w1, w2]
        with patch.object(eacl, "CURRENT_YEAR", FIXED_YEAR):
            result = eacl.pick_analogue_window(windows, 20, 2010)
        assert result["pps"] == pytest.approx(0.9)

    def test_window_missing_l_field_skipped(self):
        """Window dicts without an integer 'l' field are treated as ineligible."""
        windows = [{"sb": 1990, "pps": 0.8, "sa": 1985}]  # no 'l'
        with patch.object(eacl, "CURRENT_YEAR", FIXED_YEAR):
            result = eacl.pick_analogue_window(windows, 20, 2010)
        assert result is None

    def test_window_missing_sb_field_skipped(self):
        """Windows without 'sb' field are ineligible."""
        windows = [{"l": 20, "pps": 0.8, "sa": 1985}]  # no 'sb'
        with patch.object(eacl, "CURRENT_YEAR", FIXED_YEAR):
            result = eacl.pick_analogue_window(windows, 20, 2010)
        assert result is None


# ===========================================================================
# enrich() — regression tests for #559 + #561 fixes
#
# These tests cover the V2.0 enrich() flow end-to-end against tmp_path
# fixtures. They are the only tests that exercise the lines that #559's
# UnboundLocalError on `L` and dead `canonical_lengths.values()` reference
# previously poisoned. Without these, the live enrich() path is entirely
# uncovered.
# ===========================================================================

import json  # noqa: E402


def _write_enriched(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_pair_windows(dir_path, subject_id, windows_by_analogue):
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / f"{subject_id}.json").write_text(
        json.dumps(windows_by_analogue), encoding="utf-8"
    )


def test_enrich_does_not_raise_unbound_local_l(tmp_path):
    """#559 regression: the legacy `chosen = pick_analogue_window(windows,
    L, ...)` call referenced an undefined `L` (set by the now-removed V1
    `best_common_length()` block) and raised UnboundLocalError whenever
    an analogue had pair-window data. The V2.0 per-year loop below
    recomputed everything anyway, making the call both broken and dead.
    Fix: delete the call. This test confirms enrich() runs end-to-end on
    a fixture with pair-window data without hitting the NameError."""
    pw_dir = tmp_path / "pair-windows"
    enriched_path = tmp_path / "analogues-enriched.json"

    _write_pair_windows(pw_dir, "101", {
        "201": {"top": [
            # event year 2010, end-aligned window: sb=1990, l=20 -> end 2010
            {"l": 20, "sb": 1990, "sa": 1985, "pps": 0.8, "ac": 0.7, "ic": 12},
        ]},
    })
    _write_enriched(enriched_path, {
        "countries": {
            "101": {
                "civil_war": {
                    "analogues": [
                        {"country_b_id": 201, "event_year_b": 2010},
                    ]
                }
            }
        }
    })

    rc = eacl.enrich(pw_dir, enriched_path, length_tolerance=2)
    assert rc == 0

    out = json.loads(enriched_path.read_text(encoding="utf-8"))
    analogue = out["countries"]["101"]["civil_war"]["analogues"][0]
    # The V2.0 per-year loop should have populated pair_* fields
    assert analogue["pair_length"] == 20
    assert analogue["pair_start_b"] == 1990
    assert analogue["pair_pps"] == pytest.approx(0.8)
    assert analogue["event_in_window"] is True


def test_enrich_does_not_reference_canonical_lengths(tmp_path):
    """#559 regression: the trailing stats block iterated
    `canonical_lengths.values()` — a dict the V1 code populated alongside
    `block["canonical_length"] = L`. Both were removed in V2.0 (no force-
    fit), so the loop iterated an undefined name. Fix: delete the block.
    This test runs enrich() on a fixture where the V1 flow would have set
    canonical_lengths; the V2.0 code must complete without NameError."""
    pw_dir = tmp_path / "pair-windows"
    enriched_path = tmp_path / "analogues-enriched.json"

    # Two subjects x two categories with multiple analogues — the kind of
    # fixture that would have populated several canonical_lengths entries
    # under the V1 algorithm.
    _write_pair_windows(pw_dir, "101", {
        "201": {"top": [{"l": 20, "sb": 1990, "sa": 1985, "pps": 0.8, "ac": 0.7, "ic": 12}]},
        "202": {"top": [{"l": 22, "sb": 1988, "sa": 1983, "pps": 0.6, "ac": 0.6, "ic": 10}]},
    })
    _write_pair_windows(pw_dir, "102", {
        "201": {"top": [{"l": 18, "sb": 1992, "sa": 1987, "pps": 0.7, "ac": 0.7, "ic": 11}]},
    })
    _write_enriched(enriched_path, {
        "countries": {
            "101": {
                "civil_war": {
                    "analogues": [
                        {"country_b_id": 201, "event_year_b": 2010},
                        {"country_b_id": 202, "event_year_b": 2010},
                    ]
                }
            },
            "102": {
                "protest": {
                    "analogues": [
                        {"country_b_id": 201, "event_year_b": 2010},
                    ]
                }
            }
        }
    })

    # If the dead `canonical_lengths.values()` reference came back, this
    # would raise NameError. Asserting rc == 0 is the regression check.
    rc = eacl.enrich(pw_dir, enriched_path, length_tolerance=2)
    assert rc == 0


def test_enrich_respects_length_tolerance_flag(tmp_path):
    """#561 regression: the inner `_aligned_for` helper hardcoded ±2 for
    the terminus-alignment band. Wiring the helper to length_tolerance
    means a tightened CLI flag (--tolerance 0) excludes windows that
    a looser tolerance (--tolerance 5) would have kept. This test pins
    that wire-through so the flag's effect is testable, not just
    cosmetic."""
    pw_dir = tmp_path / "pair-windows"
    enriched_path_strict = tmp_path / "strict.json"
    enriched_path_loose = tmp_path / "loose.json"

    # Window ends at sb+l = 1990+20 = 2010. Event year is 2014.
    # Terminus offset = |2010 - 2014| = 4.
    #   Under tolerance=2: NOT aligned -> no pair_* fields.
    #   Under tolerance=5: aligned     -> pair_length=20 etc.
    payload = {
        "countries": {
            "101": {
                "civil_war": {
                    "analogues": [
                        {"country_b_id": 201, "event_year_b": 2014},
                    ]
                }
            }
        }
    }
    _write_pair_windows(pw_dir, "101", {
        "201": {"top": [
            {"l": 20, "sb": 1990, "sa": 1985, "pps": 0.8, "ac": 0.7, "ic": 12},
        ]},
    })
    _write_enriched(enriched_path_strict, payload)
    _write_enriched(enriched_path_loose, dict(payload))

    eacl.enrich(pw_dir, enriched_path_strict, length_tolerance=2)
    eacl.enrich(pw_dir, enriched_path_loose, length_tolerance=5)

    strict = json.loads(enriched_path_strict.read_text(encoding="utf-8"))
    loose = json.loads(enriched_path_loose.read_text(encoding="utf-8"))

    strict_analogue = strict["countries"]["101"]["civil_war"]["analogues"][0]
    loose_analogue = loose["countries"]["101"]["civil_war"]["analogues"][0]

    # Strict run: no aligned window -> no pair_length set
    assert strict_analogue.get("pair_length") is None
    # Loose run: window aligned -> pair_length populated
    assert loose_analogue.get("pair_length") == 20
