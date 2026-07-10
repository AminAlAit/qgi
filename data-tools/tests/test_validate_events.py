"""Tests for scripts/validate_events.py (#373 coverage + #422 Bugs 1/2 refactor).

validate_events returns FileResult / AggregateResult dataclasses instead of
mutating module-level globals — fixture drift risk eliminated. Each test
calls validate_file() and inspects the returned object directly.

Covers:
- valid event passes with no errors
- missing required field (year / title / description / category) → error per field
- year out of range (below 1900, above 2030) → error
- year wrong type (string) → error
- empty title → error
- title that is not a string → error
- unknown (non-string) category → error
- #422 Bug 2: category not in canonical 71-code taxonomy → error
- recency-bias warning: >35% of events post-2020 → warning, no error
- multiple errors in one file are all surfaced (not just first)
- root not a list → error
- invalid JSON → error
- title exceeds MAX_TITLE_LENGTH → warning (not error)
- fewer than MIN_EVENTS_PER_COUNTRY → warning (not error)
- sources field: non-list → error; empty list → warning
- main() integration: valid directory exits 0, invalid exits 1
- #422 Bug 1 regression: re-running in same process doesn't accumulate state
"""
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import validate_events as ve  # noqa: E402


# ─── helpers ──────────────────────────────────────────────────────────────────

def _write_events(path: Path, events: list):
    path.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")


def _valid_event(**overrides):
    base = {
        "year": 2000,
        "title": "A valid event title",
        "description": "A valid description",
        "category": "elections_and_voting",
    }
    base.update(overrides)
    return base


# ─── valid event ──────────────────────────────────────────────────────────────

def test_valid_event_no_errors(tmp_path):
    f = tmp_path / "country.json"
    _write_events(f, [_valid_event() for _ in range(12)])
    result = ve.validate_file(f)
    assert result.errors == []


# ─── missing required fields ──────────────────────────────────────────────────

@pytest.mark.parametrize("missing_field", ["year", "title", "description", "category"])
def test_missing_required_field_raises_error(tmp_path, missing_field):
    event = _valid_event()
    del event[missing_field]
    f = tmp_path / "country.json"
    _write_events(f, [event] * 12)
    result = ve.validate_file(f)
    assert any(missing_field in e for e in result.errors), (
        f"Expected error about missing '{missing_field}' but got: {result.errors}"
    )


# ─── year validation ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad_year", [1899, 2031, 0, -500])
def test_year_out_of_range(tmp_path, bad_year):
    f = tmp_path / "country.json"
    _write_events(f, [_valid_event(year=bad_year)] * 12)
    result = ve.validate_file(f)
    assert any(str(bad_year) in e for e in result.errors)


def test_year_wrong_type_string(tmp_path):
    f = tmp_path / "country.json"
    _write_events(f, [_valid_event(year="2000")] * 12)
    result = ve.validate_file(f)
    assert any("year" in e for e in result.errors)


# ─── title validation ─────────────────────────────────────────────────────────

def test_empty_title_fails(tmp_path):
    f = tmp_path / "country.json"
    _write_events(f, [_valid_event(title="")] * 12)
    result = ve.validate_file(f)
    assert any("title" in e for e in result.errors)


def test_title_not_a_string_fails(tmp_path):
    f = tmp_path / "country.json"
    _write_events(f, [_valid_event(title=42)] * 12)
    result = ve.validate_file(f)
    assert any("title" in e for e in result.errors)


def test_title_over_max_length_is_warning_not_error(tmp_path):
    f = tmp_path / "country.json"
    long_title = "A" * (ve.MAX_TITLE_LENGTH + 1)
    _write_events(f, [_valid_event(title=long_title)] * 12)
    result = ve.validate_file(f)
    assert result.errors == []
    assert any("title" in w or "chars" in w for w in result.warnings)


# ─── mojibake guard (#434) ───────────────────────────────────────────────────


def test_title_mojibake_is_error(tmp_path):
    """A double-encoded UTF-8 title (Ã©, â€" et al.) must fail validation."""
    f = tmp_path / "country.json"
    # 'GuaidÃ³' = U+0047 U+0075 U+0061 U+0069 U+0064 U+00C3 U+00B3 — the
    # mojibake form of 'Guaidó'. Real specimens of this exact pattern
    # were on qgintelligence.com/countries/venezuela before the recovery
    # script ran on 2026-04-25.
    bad_title = "Guaid\u00C3\u00B3 Reaches Out to Caracas"
    _write_events(f, [_valid_event(title=bad_title)] * 12)
    result = ve.validate_file(f)
    assert any("mojibake" in e.lower() for e in result.errors), (
        f"Expected a mojibake error; got errors={result.errors}"
    )


def test_clean_unicode_title_passes(tmp_path):
    """Real accented chars (é, ñ, ó) must NOT be flagged as mojibake."""
    f = tmp_path / "country.json"
    # Same string after recovery — real accented characters.
    clean_title = "Guaid\u00F3 Reaches Out to Caracas"
    _write_events(f, [_valid_event(title=clean_title)] * 12)
    result = ve.validate_file(f)
    assert not any("mojibake" in e.lower() for e in result.errors), (
        f"Clean unicode incorrectly flagged: {result.errors}"
    )


def test_em_dash_mojibake_is_error(tmp_path):
    """The other common mojibake — em-dash via Windows-1252 — must fail."""
    f = tmp_path / "country.json"
    # 'â€"' = the cp1252 mojibake of '—'. Real specimens were on
    # qgintelligence.com/countries/angola before recovery.
    bad_title = "Treaty Signed \u00E2\u20AC\u201D Diplomatic Reset"
    _write_events(f, [_valid_event(title=bad_title)] * 12)
    result = ve.validate_file(f)
    assert any("mojibake" in e.lower() for e in result.errors), (
        f"Expected mojibake error for em-dash; got errors={result.errors}"
    )


# ─── category validation ──────────────────────────────────────────────────────

def test_category_non_string_fails(tmp_path):
    f = tmp_path / "country.json"
    _write_events(f, [_valid_event(category=99)] * 12)
    result = ve.validate_file(f)
    assert any("category" in e for e in result.errors)


def test_category_not_in_taxonomy_fails(tmp_path):
    """#422 Bug 2: category must be in the canonical 71-code set."""
    f = tmp_path / "country.json"
    _write_events(f, [_valid_event(category="totally_made_up_thing")] * 12)
    valid = {"elections_and_voting", "civil_war_and_insurgency"}  # no made-up
    result = ve.validate_file(f, valid_categories=valid)
    assert any(
        "totally_made_up_thing" in e and "taxonomy" in e.lower() for e in result.errors
    ), f"Expected taxonomy-violation error, got: {result.errors}"


def test_category_in_taxonomy_passes(tmp_path):
    """#422 Bug 2: a category in the 71-code set produces no taxonomy error."""
    f = tmp_path / "country.json"
    _write_events(f, [_valid_event(category="elections_and_voting")] * 12)
    valid = {"elections_and_voting", "civil_war_and_insurgency"}
    result = ve.validate_file(f, valid_categories=valid)
    assert result.errors == []


def test_category_enforcement_skipped_when_empty_set(tmp_path):
    """Backwards-compat: empty/None valid_categories disables enforcement
    (so bare `validate_file(path)` calls without taxonomy still work)."""
    f = tmp_path / "country.json"
    _write_events(f, [_valid_event(category="whatever")] * 12)
    # No valid_categories argument
    r1 = ve.validate_file(f)
    # Explicitly empty set
    r2 = ve.validate_file(f, valid_categories=set())
    # Neither should flag the category as taxonomy-violating.
    assert not any("taxonomy" in e.lower() for e in r1.errors)
    assert not any("taxonomy" in e.lower() for e in r2.errors)


# ─── recency bias ─────────────────────────────────────────────────────────────

def test_recency_bias_warning_at_threshold(tmp_path):
    f = tmp_path / "country.json"
    events = [_valid_event(year=2021)] * 36 + [_valid_event(year=1990)] * 64
    _write_events(f, events)
    result = ve.validate_file(f)
    assert result.errors == []
    assert any("2020" in w or "recency" in w.lower() or "%" in w for w in result.warnings)


def test_no_recency_warning_below_threshold(tmp_path):
    f = tmp_path / "country.json"
    events = [_valid_event(year=2021)] * 35 + [_valid_event(year=1990)] * 65
    _write_events(f, events)
    result = ve.validate_file(f)
    recency_warnings = [w for w in result.warnings if "2020" in w or "recency" in w.lower() or "%" in w]
    assert recency_warnings == []


# ─── multiple errors in one file ─────────────────────────────────────────────

def test_multiple_errors_all_surfaced(tmp_path):
    f = tmp_path / "country.json"
    events = [
        _valid_event(year=1800),
        _valid_event(title=""),
        _valid_event(year="not-an-int"),
    ] * 4
    _write_events(f, events)
    result = ve.validate_file(f)
    assert len(result.errors) >= 3


# ─── root structure ───────────────────────────────────────────────────────────

def test_root_not_a_list_is_error(tmp_path):
    f = tmp_path / "country.json"
    f.write_text(json.dumps({"events": []}), encoding="utf-8")
    result = ve.validate_file(f)
    assert any("array" in e or "list" in e for e in result.errors)


def test_invalid_json_is_error(tmp_path):
    f = tmp_path / "country.json"
    f.write_text("{not valid json", encoding="utf-8")
    result = ve.validate_file(f)
    assert any("JSON" in e or "json" in e for e in result.errors)


# ─── count warnings ──────────────────────────────────────────────────────────

def test_fewer_than_min_events_is_warning(tmp_path):
    f = tmp_path / "country.json"
    _write_events(f, [_valid_event()] * (ve.MIN_EVENTS_PER_COUNTRY - 1))
    result = ve.validate_file(f)
    assert result.errors == []
    assert any(str(ve.MIN_EVENTS_PER_COUNTRY) in w or "min" in w.lower() for w in result.warnings)


# ─── sources field validation ─────────────────────────────────────────────────

def test_sources_non_list_is_error(tmp_path):
    f = tmp_path / "country.json"
    event = _valid_event()
    event["sources"] = "https://example.com"
    _write_events(f, [event] * 12)
    result = ve.validate_file(f)
    assert any("sources" in e for e in result.errors)


def test_sources_empty_list_is_warning(tmp_path):
    f = tmp_path / "country.json"
    event = _valid_event()
    event["sources"] = []
    _write_events(f, [event] * 12)
    result = ve.validate_file(f)
    assert result.errors == []
    assert any("sources" in w for w in result.warnings)


# ─── load_valid_categories ───────────────────────────────────────────────────

def test_load_valid_categories_from_real_taxonomy():
    """Real taxonomy file produces 71 codes (Track-2 invariant)."""
    codes = ve.load_valid_categories()
    assert len(codes) == 71
    # Spot-check a known code
    assert "civil_war_and_insurgency" in codes
    assert "elections_and_voting" in codes


def test_load_valid_categories_missing_file_returns_empty(tmp_path):
    """Missing taxonomy → empty set (graceful fallback, not a crash)."""
    result = ve.load_valid_categories(tmp_path / "does_not_exist.json")
    assert result == set()


# ─── validate_directory + main() integration ─────────────────────────────────

def test_validate_directory_returns_aggregate(tmp_path, monkeypatch):
    events_dir = tmp_path / "curated"
    events_dir.mkdir()
    _write_events(events_dir / "country_a.json", [_valid_event()] * 12)
    _write_events(events_dir / "country_b.json", [_valid_event(year=1800)] * 12)

    agg = ve.validate_directory(events_dir, taxonomy_path=tmp_path / "no_taxonomy.json")
    assert agg.total_files == 2
    assert agg.total_events == 24
    assert any("1800" in e for e in agg.errors)


def test_main_exits_0_on_valid_directory(tmp_path, monkeypatch):
    events_dir = tmp_path / "curated"
    events_dir.mkdir()
    _write_events(events_dir / "country.json", [_valid_event() for _ in range(12)])
    monkeypatch.setattr(ve, "EVENTS_DIR", events_dir)
    # Point taxonomy at a file that doesn't exist → enforcement disabled
    monkeypatch.setattr(ve, "TAXONOMY_PATH", tmp_path / "no_taxonomy.json")
    assert ve.main() == 0


def test_main_exits_1_on_invalid_events(tmp_path, monkeypatch):
    events_dir = tmp_path / "curated"
    events_dir.mkdir()
    _write_events(events_dir / "country.json", [_valid_event(year=1800)] * 12)
    monkeypatch.setattr(ve, "EVENTS_DIR", events_dir)
    monkeypatch.setattr(ve, "TAXONOMY_PATH", tmp_path / "no_taxonomy.json")
    assert ve.main() == 1


def test_main_exits_1_when_no_json_files(tmp_path, monkeypatch):
    events_dir = tmp_path / "curated"
    events_dir.mkdir()
    monkeypatch.setattr(ve, "EVENTS_DIR", events_dir)
    monkeypatch.setattr(ve, "TAXONOMY_PATH", tmp_path / "no_taxonomy.json")
    assert ve.main() == 1


# ─── #422 Bug 1 regression: no global state accumulation ─────────────────────

def test_running_twice_in_same_process_does_not_accumulate(tmp_path, monkeypatch):
    """#422 Bug 1: running main() twice previously accumulated errors from
    both runs into module globals. After refactor, each run returns its
    own AggregateResult and nothing persists between calls."""
    # Run 1: invalid directory → exit 1
    events_dir = tmp_path / "curated"
    events_dir.mkdir()
    _write_events(events_dir / "bad.json", [_valid_event(year=1800)] * 12)
    monkeypatch.setattr(ve, "EVENTS_DIR", events_dir)
    monkeypatch.setattr(ve, "TAXONOMY_PATH", tmp_path / "no_taxonomy.json")
    assert ve.main() == 1

    # Run 2: replace with valid files, same directory. Should now exit 0
    # — NOT still carry errors from run 1.
    (events_dir / "bad.json").unlink()
    _write_events(events_dir / "good.json", [_valid_event()] * 12)
    assert ve.main() == 0
