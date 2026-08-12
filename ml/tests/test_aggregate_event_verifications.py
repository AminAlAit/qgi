"""Unit tests for aggregate_event_verifications.py pure functions.

Covers:
  - is_year_off() — note heuristic classification
  - classify_file() — JSON parsing + CountryStats population (via tmp_path)
  - sum_totals() — cross-country aggregation
  - render_plain_table() — plain-text formatting
  - render_markdown() — markdown output correctness
  - sort key lambdas (false-rate, false-count, total, slug)
  - Empty dir / empty file robustness

Skipped:
  - collect() / count_curated() / main() — depend on real filesystem dirs
    (DEFAULT_VERIFICATION_DIR, DEFAULT_CURATED_DIR) and/or argparse. The
    underlying pure logic is covered through classify_file() + sum_totals().

#373 script test coverage audit.
"""
from __future__ import annotations

import json
import sys
import pathlib

import pytest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import aggregate_event_verifications as aev  # noqa: E402


# ===========================================================================
# is_year_off()
# ===========================================================================

class TestIsYearOff:

    def test_year_is_wrong_phrase(self):
        assert aev.is_year_off("year is wrong") is True

    def test_year_error_phrase(self):
        assert aev.is_year_off("This is a year error.") is True

    def test_off_by_phrase(self):
        assert aev.is_year_off("off by 2 years") is True

    def test_wrong_year_phrase(self):
        assert aev.is_year_off("The wrong year was recorded") is True

    def test_incorrect_year_phrase(self):
        assert aev.is_year_off("incorrect year: should be 1997") is True

    def test_actually_19xx_phrase(self):
        assert aev.is_year_off("actually 1989, not 1990") is True

    def test_actually_20xx_phrase(self):
        assert aev.is_year_off("actually 2003") is True

    def test_not_19xx_phrase(self):
        assert aev.is_year_off("not 1994 but 1995") is True

    def test_not_20xx_phrase(self):
        assert aev.is_year_off("not 2010 actually 2011") is True

    def test_case_insensitive(self):
        assert aev.is_year_off("YEAR ERROR in note") is True
        assert aev.is_year_off("Year Is Wrong") is True

    def test_fact_error_not_year_off(self):
        assert aev.is_year_off("Title is incorrect; event never happened") is False

    def test_empty_string_not_year_off(self):
        assert aev.is_year_off("") is False

    def test_none_coerced_not_year_off(self):
        # Script uses (note or "").lower() so None-equivalent is handled.
        assert aev.is_year_off(None) is False


# ===========================================================================
# classify_file() — via tmp_path
# ===========================================================================

class TestClassifyFile:

    def test_flat_array_format(self, tmp_path):
        """Wire format 1: flat list of event objects."""
        data = [
            {"year": 1990, "title": "Event A", "status": "VERIFIED", "note": ""},
            {"year": 1995, "title": "Event B", "status": "UNVERIFIED", "note": ""},
            {"year": 2000, "title": "Event C", "status": "FALSE", "note": "wrong year"},
        ]
        p = tmp_path / "my_country.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        stats = aev.classify_file(p)
        assert stats.slug == "my_country"
        assert stats.verified == 1
        assert stats.unverified == 1
        assert stats.false == 1
        assert stats.year_off_false == 1

    def test_wrapped_results_format(self, tmp_path):
        """Wire format 2: wrapped object with 'results' array."""
        data = {
            "country": "Test Country",
            "results": [
                {"year": 2001, "title": "E1", "status": "VERIFIED", "note": ""},
                {"year": 2005, "title": "E2", "status": "FALSE", "note": "off by 1 year"},
            ]
        }
        p = tmp_path / "test_country.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        stats = aev.classify_file(p)
        assert stats.verified == 1
        assert stats.false == 1
        assert stats.year_off_false == 1
        assert stats.unverified == 0

    def test_events_key_format(self, tmp_path):
        """Wrapped object with 'events' key instead of 'results'."""
        data = {
            "events": [
                {"year": 2010, "title": "E1", "status": "UNVERIFIED", "note": ""},
            ]
        }
        p = tmp_path / "country_events.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        stats = aev.classify_file(p)
        assert stats.unverified == 1

    def test_status_case_normalization(self, tmp_path):
        """Status matching must be case-insensitive (verified / Verified / VERIFIED)."""
        data = [
            {"year": 1, "title": "a", "status": "verified", "note": ""},
            {"year": 2, "title": "b", "status": "Unverified", "note": ""},
            {"year": 3, "title": "c", "status": "FALSE", "note": ""},
        ]
        p = tmp_path / "cs.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        stats = aev.classify_file(p)
        assert stats.verified == 1
        assert stats.unverified == 1
        assert stats.false == 1

    def test_non_false_year_off_not_counted(self, tmp_path):
        """year_off_false should only increment for FALSE events, not VERIFIED."""
        data = [
            {"year": 1, "title": "a", "status": "VERIFIED", "note": "wrong year"},
        ]
        p = tmp_path / "c.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        stats = aev.classify_file(p)
        assert stats.verified == 1
        assert stats.year_off_false == 0

    def test_unknown_shape_returns_empty_stats(self, tmp_path, capsys):
        """Object with no known list key → warns and returns zeroed stats."""
        data = {"metadata": "only", "description": "no list"}
        p = tmp_path / "odd.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        stats = aev.classify_file(p)
        assert stats.total == 0

    def test_invalid_json_returns_empty_stats(self, tmp_path):
        p = tmp_path / "broken.json"
        p.write_text("NOT VALID JSON {{{{", encoding="utf-8")
        stats = aev.classify_file(p)
        assert stats.total == 0
        assert stats.slug == "broken"

    def test_empty_array_returns_zero_stats(self, tmp_path):
        p = tmp_path / "empty_country.json"
        p.write_text(json.dumps([]), encoding="utf-8")
        stats = aev.classify_file(p)
        assert stats.total == 0

    def test_false_events_list_populated(self, tmp_path):
        data = [
            {"year": 2000, "title": "Bad event", "status": "FALSE",
             "note": "off by 2 years"},
        ]
        p = tmp_path / "ct.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        stats = aev.classify_file(p)
        assert len(stats.false_events) == 1
        fe = stats.false_events[0]
        assert fe["year"] == 2000
        assert fe["title"] == "Bad event"
        assert fe["year_off"] is True


# ===========================================================================
# CountryStats properties
# ===========================================================================

class TestCountryStats:

    def _make(self, verified, unverified, false, year_off_false=0):
        s = aev.CountryStats("test", verified=verified, unverified=unverified,
                             false=false, year_off_false=year_off_false)
        return s

    def test_total(self):
        s = self._make(10, 5, 2)
        assert s.total == 17

    def test_verified_pct(self):
        s = self._make(8, 2, 0)
        assert abs(s.verified_pct - 80.0) < 1e-6

    def test_false_pct(self):
        s = self._make(5, 3, 2)
        assert abs(s.false_pct - 20.0) < 1e-6

    def test_unverified_pct(self):
        s = self._make(6, 3, 1)
        assert abs(s.unverified_pct - 30.0) < 1e-6

    def test_zero_total_returns_zero_pcts(self):
        s = self._make(0, 0, 0)
        assert s.verified_pct == 0.0
        assert s.false_pct == 0.0
        assert s.unverified_pct == 0.0


# ===========================================================================
# sum_totals()
# ===========================================================================

class TestSumTotals:

    def test_two_countries(self):
        a = aev.CountryStats("a", verified=10, unverified=2, false=1, year_off_false=1)
        b = aev.CountryStats("b", verified=5, unverified=3, false=2, year_off_false=0)
        total = aev.sum_totals([a, b])
        assert total.verified == 15
        assert total.unverified == 5
        assert total.false == 3
        assert total.year_off_false == 1

    def test_empty_iterable_returns_zero_totals(self):
        total = aev.sum_totals([])
        assert total.total == 0

    def test_single_country(self):
        a = aev.CountryStats("x", verified=7, unverified=0, false=3)
        total = aev.sum_totals([a])
        assert total.verified == 7
        assert total.false == 3


# ===========================================================================
# Sort key correctness
# ===========================================================================

class TestSortKeys:
    """The sort keys are defined inline in main(), but we can reconstruct them
    and verify the expected ordering on hand-crafted rows."""

    def _rows(self):
        rows = [
            aev.CountryStats("alpha", verified=5, unverified=1, false=4),   # false_pct=40%
            aev.CountryStats("beta", verified=8, unverified=1, false=1),    # false_pct=10%
            aev.CountryStats("gamma", verified=6, unverified=1, false=3),   # false_pct=30%
        ]
        return rows

    def test_sort_by_false_rate_descending(self):
        rows = self._rows()
        rows.sort(key=lambda r: (-r.false_pct, -r.total))
        assert [r.slug for r in rows] == ["alpha", "gamma", "beta"]

    def test_sort_by_false_count_descending(self):
        rows = self._rows()
        rows.sort(key=lambda r: (-r.false, -r.total))
        assert rows[0].slug == "alpha"  # false=4
        assert rows[1].slug == "gamma"  # false=3
        assert rows[2].slug == "beta"   # false=1

    def test_sort_by_total_descending(self):
        rows = [
            aev.CountryStats("a", verified=10, unverified=0, false=0),  # total=10
            aev.CountryStats("b", verified=5, unverified=5, false=5),   # total=15
            aev.CountryStats("c", verified=1, unverified=0, false=0),   # total=1
        ]
        rows.sort(key=lambda r: -r.total)
        assert rows[0].slug == "b"
        assert rows[2].slug == "c"

    def test_sort_by_slug_ascending(self):
        rows = self._rows()
        rows.sort(key=lambda r: r.slug)
        assert [r.slug for r in rows] == ["alpha", "beta", "gamma"]


# ===========================================================================
# render_plain_table()
# ===========================================================================

class TestRenderPlainTable:

    def test_basic_table_contains_header(self):
        rows = [aev.CountryStats("france", verified=10, unverified=2, false=1)]
        out = aev.render_plain_table(rows)
        assert "Country" in out
        assert "False %" in out

    def test_slug_in_output(self):
        rows = [aev.CountryStats("france", verified=10, unverified=2, false=1)]
        out = aev.render_plain_table(rows)
        assert "france" in out

    def test_false_pct_formatted_correctly(self):
        # 2 false out of 10 total = 20.0%
        rows = [aev.CountryStats("x", verified=8, unverified=0, false=2)]
        out = aev.render_plain_table(rows)
        assert "20.0%" in out

    def test_multiple_rows(self):
        rows = [
            aev.CountryStats("a", verified=10, unverified=0, false=0),
            aev.CountryStats("b", verified=8, unverified=1, false=1),
        ]
        out = aev.render_plain_table(rows)
        assert "a" in out
        assert "b" in out

    def test_empty_rows_returns_separators_only(self):
        out = aev.render_plain_table([])
        # Should still have separators without crashing
        assert isinstance(out, str)


# ===========================================================================
# render_markdown()
# ===========================================================================

class TestRenderMarkdown:

    def _make_rows_and_totals(self):
        rows = [
            aev.CountryStats("france", verified=10, unverified=2, false=1,
                             year_off_false=1),
            aev.CountryStats("germany", verified=8, unverified=1, false=0),
        ]
        totals = aev.sum_totals(rows)
        return rows, totals

    def test_contains_h1_title(self):
        rows, totals = self._make_rows_and_totals()
        md = aev.render_markdown(rows, totals, (2, 10))
        assert "# QGI Event Verification" in md

    def test_coverage_line_present(self):
        rows, totals = self._make_rows_and_totals()
        md = aev.render_markdown(rows, totals, (2, 10))
        assert "2 of 10" in md

    def test_table_header_present(self):
        rows, totals = self._make_rows_and_totals()
        md = aev.render_markdown(rows, totals, (2, 10))
        assert "| Country |" in md

    def test_slugs_in_table(self):
        rows, totals = self._make_rows_and_totals()
        md = aev.render_markdown(rows, totals, (2, 10))
        assert "france" in md
        assert "germany" in md

    def test_false_events_section_rendered(self):
        rows, totals = self._make_rows_and_totals()
        md = aev.render_markdown(rows, totals, (2, 10))
        # france has 1 FALSE event -> section should exist
        assert "## FALSE events" in md
        assert "france" in md

    def test_year_off_marker_present(self):
        """FALSE events with year_off=True should carry [year-off] marker."""
        rows = [
            aev.CountryStats("iraq", verified=5, unverified=0, false=1,
                             year_off_false=1,
                             false_events=[{
                                 "year": 2003, "title": "Invasion",
                                 "note": "year error", "year_off": True
                             }])
        ]
        totals = aev.sum_totals(rows)
        md = aev.render_markdown(rows, totals, (1, 5))
        assert "[year-off]" in md

    def test_fact_error_marker_present(self):
        """FALSE events without year_off should carry [fact-error] marker."""
        rows = [
            aev.CountryStats("iran", verified=3, unverified=0, false=1,
                             year_off_false=0,
                             false_events=[{
                                 "year": 1979, "title": "Revolution",
                                 "note": "wrong details", "year_off": False
                             }])
        ]
        totals = aev.sum_totals(rows)
        md = aev.render_markdown(rows, totals, (1, 5))
        assert "[fact-error]" in md
