"""Unit tests for generate_country_events_json.py pure functions.

Covers:
  - normalize_category()
  - build_country_events() (file-based, tested with tmp_path)

No AWS calls. Deterministic, offline-only.

#373 script test coverage audit.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import generate_country_events_json as gcej  # noqa: E402


# ===========================================================================
# normalize_category()
# ===========================================================================

class TestNormalizeCategory:

    MAPPING = {
        "Civil War": "civil_war_and_insurgency",
        " elections ": "elections_and_voting",
        "mass protest": "mass_protest",
    }

    def test_exact_match(self):
        """Exact key in mapping returns canonical value."""
        assert gcej.normalize_category("Civil War", self.MAPPING) == "civil_war_and_insurgency"

    def test_stripped_match(self):
        """Key matches after stripping whitespace."""
        assert gcej.normalize_category(" elections ", self.MAPPING) == "elections_and_voting"

    def test_unmapped_returns_snake_case(self):
        """Unmapped category is lowercased and spaces → underscores (NOT 'other')."""
        result = gcej.normalize_category("Economic Reform", self.MAPPING)
        assert result == "economic_reform"

    def test_unmapped_already_snake_case(self):
        """Already-snake category with no mapping passes through unchanged."""
        result = gcej.normalize_category("some_unknown_slug", self.MAPPING)
        assert result == "some_unknown_slug"

    def test_empty_string_returns_uncategorized(self):
        assert gcej.normalize_category("", self.MAPPING) == "uncategorized"

    def test_none_returns_uncategorized(self):
        assert gcej.normalize_category(None, self.MAPPING) == "uncategorized"

    def test_non_string_returns_uncategorized(self):
        assert gcej.normalize_category(42, self.MAPPING) == "uncategorized"

    def test_empty_mapping_returns_snake_case(self):
        """With an empty mapping, any input falls through to snake_case transform."""
        result = gcej.normalize_category("Mass Protest", {})
        assert result == "mass_protest"

    def test_multi_word_spaces_become_underscores(self):
        """Spaces in unmapped category become underscores."""
        result = gcej.normalize_category("government formation", {})
        assert result == "government_formation"


# ===========================================================================
# build_country_events()
# ===========================================================================

class TestBuildCountryEvents:

    MAPPING = {
        "civil_war_and_insurgency": "civil_war_and_insurgency",
        "elections_and_voting": "elections_and_voting",
    }
    CANONICAL_SET = set(MAPPING.values())

    def _write(self, tmp_path, filename, events):
        p = tmp_path / filename
        p.write_text(json.dumps(events), encoding="utf-8")
        return p

    def test_basic_single_country(self, tmp_path):
        """Single country file is read and returned keyed by stem."""
        self._write(tmp_path, "turkey.json", [
            {"year": 2016, "title": "Coup attempt", "category": "civil_war_and_insurgency"},
        ])
        out, counts = gcej.build_country_events(tmp_path, self.MAPPING)
        assert "turkey" in out
        assert len(out["turkey"]) == 1
        assert out["turkey"][0]["year"] == 2016

    def test_slug_is_filename_stem(self, tmp_path):
        """Slug must equal the filename stem (T20 #313 fix)."""
        self._write(tmp_path, "central_african_republic.json", [
            {"year": 2013, "title": "Civil war", "category": "civil_war_and_insurgency"},
        ])
        out, _ = gcej.build_country_events(tmp_path, self.MAPPING)
        assert "central_african_republic" in out
        # Must NOT be present under any name-derived transformation
        assert "african_republic" not in out

    def test_events_sorted_by_year_ascending(self, tmp_path):
        """Events must be sorted by year ascending so frontend doesn't need to re-sort."""
        self._write(tmp_path, "france.json", [
            {"year": 2019, "title": "Yellow vests", "category": "elections_and_voting"},
            {"year": 1968, "title": "May 68", "category": "elections_and_voting"},
            {"year": 2005, "title": "Riots", "category": "elections_and_voting"},
        ])
        out, _ = gcej.build_country_events(tmp_path, self.MAPPING)
        years = [e["year"] for e in out["france"]]
        assert years == sorted(years)

    def test_missing_year_events_dropped(self, tmp_path):
        """Events with missing or non-int year must be silently dropped."""
        self._write(tmp_path, "germany.json", [
            {"year": None, "title": "Missing year", "category": "elections_and_voting"},
            {"year": "not_int", "title": "Bad year", "category": "elections_and_voting"},
            {"year": 2021, "title": "Valid", "category": "elections_and_voting"},
        ])
        out, _ = gcej.build_country_events(tmp_path, self.MAPPING)
        assert len(out["germany"]) == 1
        assert out["germany"][0]["year"] == 2021

    def test_non_dict_events_dropped(self, tmp_path):
        """Non-dict items in the event array are silently dropped."""
        self._write(tmp_path, "spain.json", [
            "not a dict",
            {"year": 2017, "title": "Catalonia", "category": "elections_and_voting"},
        ])
        out, _ = gcej.build_country_events(tmp_path, self.MAPPING)
        assert len(out["spain"]) == 1

    def test_non_list_file_skipped(self, tmp_path):
        """A file that is not a JSON array must be skipped entirely."""
        p = tmp_path / "bad_country.json"
        p.write_text(json.dumps({"year": 2020}), encoding="utf-8")
        out, _ = gcej.build_country_events(tmp_path, self.MAPPING)
        assert "bad_country" not in out

    def test_invalid_json_file_skipped(self, tmp_path):
        """A file with invalid JSON must be skipped without crashing."""
        p = tmp_path / "corrupt.json"
        p.write_text("{invalid json{{", encoding="utf-8")
        out, _ = gcej.build_country_events(tmp_path, self.MAPPING)
        assert "corrupt" not in out

    def test_files_starting_with_underscore_skipped(self, tmp_path):
        """Files like _backup_turkey.json must be skipped (backup/synthetic files)."""
        self._write(tmp_path, "_backup_turkey.json", [
            {"year": 2016, "title": "Coup", "category": "civil_war_and_insurgency"},
        ])
        out, _ = gcej.build_country_events(tmp_path, self.MAPPING)
        assert "_backup_turkey" not in out
        assert not any(k.startswith("_") for k in out)

    def test_canonical_count_incremented(self, tmp_path):
        """canonical_counts['canonical'] tracks events that matched the mapping."""
        self._write(tmp_path, "iraq.json", [
            {"year": 2003, "title": "Invasion", "category": "civil_war_and_insurgency"},
            {"year": 2010, "title": "Elections", "category": "elections_and_voting"},
            {"year": 2020, "title": "Unknown", "category": "unknown_category_xyz"},
        ])
        out, counts = gcej.build_country_events(tmp_path, self.MAPPING)
        assert counts["canonical"] == 2
        assert counts["fallback"] == 1

    def test_multiple_countries(self, tmp_path):
        """Multiple files produce multiple keys in output dict."""
        for slug, year in [("brazil", 2016), ("chile", 1973), ("peru", 2021)]:
            self._write(tmp_path, f"{slug}.json", [
                {"year": year, "title": "Event", "category": "elections_and_voting"},
            ])
        out, _ = gcej.build_country_events(tmp_path, self.MAPPING)
        assert set(out.keys()) == {"brazil", "chile", "peru"}

    def test_empty_directory(self, tmp_path):
        """An empty directory returns empty dict with zero counts."""
        out, counts = gcej.build_country_events(tmp_path, self.MAPPING)
        assert out == {}
        assert counts["canonical"] == 0
        assert counts["fallback"] == 0

    def test_category_normalized_in_output(self, tmp_path):
        """Output event category must be the normalized form, not the raw input."""
        # Raw category has spaces — should be snake_case-ified
        self._write(tmp_path, "india.json", [
            {"year": 2024, "title": "Vote", "category": "elections_and_voting"},
        ])
        out, _ = gcej.build_country_events(tmp_path, self.MAPPING)
        assert out["india"][0]["category"] == "elections_and_voting"

    def test_output_event_fields_are_year_title_category_only(self, tmp_path):
        """Extra fields in the source event must not appear in the output."""
        self._write(tmp_path, "mexico.json", [
            {
                "year": 2018,
                "title": "AMLO elected",
                "category": "elections_and_voting",
                "source": "wikipedia",
                "verified": True,
            }
        ])
        out, _ = gcej.build_country_events(tmp_path, self.MAPPING)
        event = out["mexico"][0]
        assert set(event.keys()) == {"year", "title", "category"}
