"""Tests for scripts/split_verification_by_verdict.py (#372).

Covers:
- verdict normalization across 5 adjudication field variants
- reason normalization across 4 reason-field variants
- source URL extraction across 5 source-field variants
- events-list extraction from raw-list vs dict-wrapped (events/results) files
- match-normalization robustness (em-dash, accented chars, replacement chars)
- title healing (exact-post-norm + difflib fuzzy fallback)
- process_file end-to-end on mixed-verdict input
- idempotent re-run produces the same output
"""
import json
import sys
from pathlib import Path

import pytest

# Put scripts/ on sys.path so we can import the target module
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import split_verification_by_verdict as svb  # noqa: E402


# ─── normalize_verdict ────────────────────────────────────────────────

@pytest.mark.parametrize("event,expected", [
    ({"verdict": "TRUE"}, "TRUE"),
    ({"verdict": "true"}, "TRUE"),  # case-insensitive
    ({"verdict": "VERIFIED"}, "TRUE"),  # VERIFIED = TRUE
    ({"status": "VERIFIED"}, "TRUE"),
    ({"verification_status": "VERIFIED"}, "TRUE"),
    ({"verified": "VERIFIED"}, "TRUE"),
    ({"verdict": "FALSE"}, "FALSE"),
    ({"status": "FALSE"}, "FALSE"),
    ({"verdict": "UNVERIFIED"}, None),  # UNVERIFIED → unverdicted
    ({"status": "UNVERIFIED"}, None),
    ({}, None),  # no adjudication field at all
    ({"verdict": None}, None),
    ({"verdict": "", "status": "VERIFIED"}, None),  # verdict wins even if empty
    ({"note": "some note"}, None),  # no adjudication field
])
def test_normalize_verdict(event, expected):
    assert svb.normalize_verdict(event) == expected


def test_normalize_verdict_precedence():
    """When multiple adjudication fields exist, verdict wins (first in tuple)."""
    # verdict is first in ADJUDICATION_FIELDS, so it takes precedence over status
    assert svb.normalize_verdict({"verdict": "TRUE", "status": "FALSE"}) == "TRUE"


# ─── normalize_reason ─────────────────────────────────────────────────

@pytest.mark.parametrize("event,expected", [
    ({"reason": "off by 1 year"}, "off by 1 year"),
    ({"note": "confirmed"}, "confirmed"),
    ({"notes": "confirmed"}, "confirmed"),
    ({"verification_note": "confirmed"}, "confirmed"),
    ({}, None),
    ({"reason": ""}, None),  # empty string treated as missing
    ({"reason": "   "}, None),  # whitespace-only treated as missing
    ({"reason": None, "note": "fallback"}, "fallback"),
    ({"reason": "primary", "note": "secondary"}, "primary"),  # reason wins
])
def test_normalize_reason(event, expected):
    assert svb.normalize_reason(event) == expected


# ─── extract_source ───────────────────────────────────────────────────

@pytest.mark.parametrize("event,expected", [
    ({"source": "https://en.wikipedia.org/x"}, "https://en.wikipedia.org/x"),
    ({"sources": ["https://en.wikipedia.org/x"]}, "https://en.wikipedia.org/x"),
    ({"url": "https://x.com"}, "https://x.com"),
    ({"verification_url": "https://x.com"}, "https://x.com"),
    ({"verification_source": "https://x.com"}, "https://x.com"),
    ({"source": "not a url"}, None),  # non-http skipped
    ({}, None),
    ({"source": None}, None),
    ({"source": "http://example.com"}, "http://example.com"),  # http not just https
])
def test_extract_source(event, expected):
    assert svb.extract_source(event) == expected


# ─── extract_events_list ──────────────────────────────────────────────

def test_extract_events_list_raw_array():
    data = [{"year": 2020, "title": "x", "status": "VERIFIED"}]
    assert svb.extract_events_list(data) == data


def test_extract_events_list_dict_with_events_key():
    data = {"country": "X", "events": [{"year": 2020, "title": "x", "status": "VERIFIED"}]}
    assert svb.extract_events_list(data) == data["events"]


def test_extract_events_list_dict_with_results_key():
    data = {"country": "X", "results": [{"year": 2020, "title": "x", "status": "VERIFIED"}]}
    assert svb.extract_events_list(data) == data["results"]


def test_extract_events_list_prefers_events_over_results():
    data = {"events": [{"title": "a"}], "results": [{"title": "b"}]}
    # events comes first in EVENTS_KEYS
    assert svb.extract_events_list(data)[0]["title"] == "a"


def test_extract_events_list_empty():
    assert svb.extract_events_list({}) == []
    assert svb.extract_events_list({"summary": {"VERIFIED": 10}}) == []
    assert svb.extract_events_list("not a list or dict") == []


def test_extract_events_list_ignores_non_event_lists():
    """A list where items lack 'title' (e.g. a summary list) should not be picked up."""
    data = {"summary_items": [{"count": 5}], "events": [{"year": 2020, "title": "x"}]}
    assert svb.extract_events_list(data)[0]["title"] == "x"


# ─── _match_normalize ─────────────────────────────────────────────────

@pytest.mark.parametrize("inp,expected", [
    ("Hello World", "hello world"),
    ("Hello—World", "hello world"),  # em-dash → space
    ("Hello \ufffd World", "hello world"),  # replacement char → space
    ("Café", "café"),  # accented word chars preserved
    ("  multiple   spaces  ", "multiple spaces"),
    ("punct!@#$%", "punct"),
    ("", ""),
    (None, ""),
    (123, "123"),  # numeric titles coerced
])
def test_match_normalize(inp, expected):
    assert svb._match_normalize(inp) == expected


# ─── heal_title ───────────────────────────────────────────────────────

@pytest.fixture
def curated_dir(tmp_path):
    d = tmp_path / "curated"
    d.mkdir()
    (d / "testland.json").write_text(json.dumps([
        {"year": 2020, "title": "Foo Event — Major Reform"},
        {"year": 2020, "title": "Entirely Different Event"},
        {"year": 2021, "title": "Café Scandal — Ministry Collapse"},
    ]), encoding="utf-8")
    return d


def test_heal_title_exact_match(curated_dir):
    idx, lists = svb.load_curated_titles(curated_dir)
    # verification title with replacement char — should heal to curated em-dash version
    healed = svb.heal_title("testland", 2020, "Foo Event \ufffd Major Reform", idx, lists)
    assert healed == "Foo Event — Major Reform"


def test_heal_title_fuzzy_match(curated_dir):
    idx, lists = svb.load_curated_titles(curated_dir)
    # verification title is missing the accented char (Café → Cafe) — fuzzy match should catch
    healed = svb.heal_title("testland", 2021, "Cafe Scandal \ufffd Ministry Collapse", idx, lists)
    assert healed == "Café Scandal — Ministry Collapse"


def test_heal_title_no_match_returns_input(curated_dir):
    idx, lists = svb.load_curated_titles(curated_dir)
    healed = svb.heal_title("testland", 2020, "Totally Unrelated Event", idx, lists)
    assert healed == "Totally Unrelated Event"


def test_heal_title_unknown_country_returns_input(curated_dir):
    idx, lists = svb.load_curated_titles(curated_dir)
    healed = svb.heal_title("nowhereland", 2020, "Foo Event", idx, lists)
    assert healed == "Foo Event"


def test_heal_title_none_year_returns_input(curated_dir):
    idx, lists = svb.load_curated_titles(curated_dir)
    healed = svb.heal_title("testland", None, "Foo Event", idx, lists)
    assert healed == "Foo Event"


# ─── process_file end-to-end ──────────────────────────────────────────

@pytest.fixture
def verification_file(tmp_path):
    """A verification file with a mix of verdicts + dialect variants."""
    f = tmp_path / "testland.json"
    f.write_text(json.dumps([
        # VERIFIED via status → kept as TRUE
        {"year": 2020, "title": "Foo Event", "status": "VERIFIED", "note": "confirmed"},
        # FALSE via verdict → kept as FALSE
        {"year": 2021, "title": "Bar Event", "verdict": "FALSE", "reason": "off by 1 year"},
        # UNVERIFIED → dropped
        {"year": 2022, "title": "Baz Event", "status": "UNVERIFIED", "note": "pending"},
        # No adjudication at all → dropped
        {"year": 2023, "title": "Qux Event", "note": "just a note"},
        # verified field + URL in verification_source
        {"year": 2024, "title": "Quux Event", "verified": "VERIFIED",
         "verification_source": "https://en.wikipedia.org/Quux"},
    ]), encoding="utf-8")
    return f


def test_process_file_counts(verification_file):
    stats = svb.process_file(verification_file, {}, {})
    assert stats["n_before"] == 5
    assert stats["n_kept"] == 3  # 2 VERIFIED + 1 FALSE
    assert stats["n_true"] == 2
    assert stats["n_false"] == 1
    assert stats["n_dropped"] == 2  # UNVERIFIED + no-adjudication
    assert stats["delete"] is False


def test_process_file_normalized_schema(verification_file):
    stats = svb.process_file(verification_file, {}, {})
    titles = [e["title"] for e in stats["kept_events"]]
    assert "Foo Event" in titles
    assert "Bar Event" in titles
    assert "Quux Event" in titles
    assert "Baz Event" not in titles  # UNVERIFIED dropped
    # Every kept event has normalized fields
    for e in stats["kept_events"]:
        assert "year" in e and "title" in e and "verdict" in e and "reason" in e
        assert e["verdict"] in {"TRUE", "FALSE"}
    # URL carried through
    quux = [e for e in stats["kept_events"] if e["title"] == "Quux Event"][0]
    assert quux["source"] == "https://en.wikipedia.org/Quux"


def test_process_file_all_unverified_flags_delete(tmp_path):
    f = tmp_path / "pending.json"
    f.write_text(json.dumps([
        {"year": 2020, "title": "X", "status": "UNVERIFIED"},
        {"year": 2021, "title": "Y", "status": "UNVERIFIED"},
    ]), encoding="utf-8")
    stats = svb.process_file(f, {}, {})
    assert stats["n_kept"] == 0
    assert stats["delete"] is True


def test_process_file_bad_json(tmp_path):
    f = tmp_path / "broken.json"
    f.write_text("{not valid json", encoding="utf-8")
    stats = svb.process_file(f, {}, {})
    assert "error" in stats


def test_process_file_no_events(tmp_path):
    f = tmp_path / "nolist.json"
    f.write_text(json.dumps({"summary": {"X": 1}}), encoding="utf-8")
    stats = svb.process_file(f, {}, {})
    assert "error" in stats


# ─── healing integration with process_file ───────────────────────────

def test_process_file_heals_corrupted_title(tmp_path, curated_dir):
    """If verification has an encoding-corrupted title, process_file should heal it."""
    vf = tmp_path / "verification" / "testland.json"
    vf.parent.mkdir(parents=True)
    vf.write_text(json.dumps([
        # Corrupted em-dash (replacement char) — should match curated "Foo Event — Major Reform"
        {"year": 2020, "title": "Foo Event \ufffd Major Reform", "status": "FALSE",
         "note": "off by 5 years"},
    ]), encoding="utf-8")
    idx, lists = svb.load_curated_titles(curated_dir)
    stats = svb.process_file(vf, idx, lists)
    assert stats["n_healed"] == 1
    assert stats["kept_events"][0]["title"] == "Foo Event — Major Reform"


# ─── idempotency ──────────────────────────────────────────────────────

def test_split_is_idempotent(tmp_path, curated_dir):
    """Running the split twice on the same input produces identical output."""
    vf = tmp_path / "testland.json"
    vf.write_text(json.dumps([
        {"year": 2020, "title": "Foo Event \ufffd Major Reform", "status": "FALSE", "note": "x"},
        {"year": 2021, "title": "Pending", "status": "UNVERIFIED"},
        {"year": 2022, "title": "Entirely Different Event", "verdict": "TRUE", "reason": "x"},
    ]), encoding="utf-8")
    idx, lists = svb.load_curated_titles(curated_dir)

    # First pass — write normalized output
    stats1 = svb.process_file(vf, idx, lists)
    vf.write_text(json.dumps(stats1["kept_events"], indent=2, ensure_ascii=False), encoding="utf-8")

    # Second pass — should yield identical events
    stats2 = svb.process_file(vf, idx, lists)
    assert stats1["kept_events"] == stats2["kept_events"]
    assert stats2["n_dropped"] == 0  # nothing left to drop
    assert stats2["n_kept"] == stats1["n_kept"]
