"""Tests for the verdict-filter in scripts/ingest_events.py (#372 + #374).

#374 invariant (Amin 2026-04-21): the pipeline ingests ONLY verified-TRUE
events. FALSE and unverified are both dropped. This is THE rule, not a mode.

Covers:
- _normalize_title robust to encoding corruption
- load_verdict_index reads all 5 adjudication field variants
- load_verdict_index handles raw-list + dict-wrapped (events/results)
- load_verdict_index skips UNVERIFIED / missing / unknown
- parse_verified_events keeps ONLY verdict=TRUE events (#374)
- parse_verified_events drops unverified (no fallback)
- stale_partition_country_ids returns the set to delete from S3
"""
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import ingest_events  # noqa: E402


# ─── _normalize_title ─────────────────────────────────────────────────

@pytest.mark.parametrize("inp,expected", [
    ("Hello World", "hello world"),
    ("Hello—World", "hello world"),
    ("Hello \ufffd World", "hello world"),
    ("Café", "café"),
    ("  Mixed   Spaces  ", "mixed spaces"),
    ("Punct!@#", "punct"),
    ("", ""),
    (None, ""),
])
def test_normalize_title(inp, expected):
    assert ingest_events._normalize_title(inp) == expected


def test_normalize_title_matches_across_encoding_variants():
    """Same event title corrupted in different ways must produce the same key."""
    clean = "PLUA Founded — First Underground Independence Party"
    corrupt = "PLUA Founded \ufffd First Underground Independence Party"
    assert ingest_events._normalize_title(clean) == ingest_events._normalize_title(corrupt)


# ─── load_verdict_index ───────────────────────────────────────────────

def _write_verification(tmp_path, filename, data):
    d = tmp_path / "verification"
    d.mkdir(exist_ok=True)
    (d / filename).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return d


def test_load_verdict_index_raw_list(tmp_path):
    vdir = _write_verification(tmp_path, "testland.json", [
        {"year": 2020, "title": "Event A", "verdict": "TRUE"},
        {"year": 2021, "title": "Event B", "verdict": "FALSE"},
        {"year": 2022, "title": "Event C", "verdict": "UNVERIFIED"},
    ])
    idx = ingest_events.load_verdict_index(vdir)
    assert idx == {
        ("testland", 2020, "event a"): "TRUE",
        ("testland", 2021, "event b"): "FALSE",
        # UNVERIFIED skipped
    }


def test_load_verdict_index_dict_events_key(tmp_path):
    vdir = _write_verification(tmp_path, "testland.json", {
        "country": "Testland",
        "events": [{"year": 2020, "title": "X", "status": "VERIFIED"}],
    })
    idx = ingest_events.load_verdict_index(vdir)
    assert idx == {("testland", 2020, "x"): "TRUE"}


def test_load_verdict_index_dict_results_key(tmp_path):
    vdir = _write_verification(tmp_path, "testland.json", {
        "country": "Testland",
        "results": [{"year": 2020, "title": "X", "status": "FALSE"}],
    })
    idx = ingest_events.load_verdict_index(vdir)
    assert idx == {("testland", 2020, "x"): "FALSE"}


def test_load_verdict_index_all_adjudication_fields(tmp_path):
    """Each of the 5 adjudication field variants must map correctly."""
    vdir = _write_verification(tmp_path, "testland.json", [
        {"year": 2020, "title": "A", "verdict": "VERIFIED"},
        {"year": 2021, "title": "B", "status": "VERIFIED"},
        {"year": 2022, "title": "C", "verification_status": "VERIFIED"},
        {"year": 2023, "title": "D", "verification_verdict": "VERIFIED"},
        {"year": 2024, "title": "E", "verified": "VERIFIED"},
    ])
    idx = ingest_events.load_verdict_index(vdir)
    assert len(idx) == 5
    assert all(v == "TRUE" for v in idx.values())


def test_load_verdict_index_missing_dir(tmp_path):
    """Missing verification dir → empty index, no crash."""
    idx = ingest_events.load_verdict_index(tmp_path / "does_not_exist")
    assert idx == {}


def test_load_verdict_index_encoding_corruption_healed(tmp_path):
    """Keys must be consistent across em-dash / replacement char variants."""
    vdir = _write_verification(tmp_path, "testland.json", [
        {"year": 2020, "title": "Foo \ufffd Bar", "verdict": "FALSE"},
    ])
    idx = ingest_events.load_verdict_index(vdir)
    # The key is normalized — clients using ingest_events._normalize_title
    # on the CURATED title ("Foo — Bar") must get the same key
    expected_key = ("testland", 2020, ingest_events._normalize_title("Foo — Bar"))
    assert expected_key in idx
    assert idx[expected_key] == "FALSE"


def test_load_verdict_index_skips_bad_json(tmp_path, capsys):
    vdir = tmp_path / "verification"
    vdir.mkdir()
    (vdir / "bad.json").write_text("{not valid}", encoding="utf-8")
    (vdir / "good.json").write_text(json.dumps([
        {"year": 2020, "title": "X", "verdict": "TRUE"}
    ]), encoding="utf-8")
    idx = ingest_events.load_verdict_index(vdir)
    assert ("good", 2020, "x") in idx
    # Bad file logged a warning but did not crash
    captured = capsys.readouterr()
    assert "bad.json" in captured.out or "bad.json" in captured.err


# ─── parse_verified_events with verdict filter ──────────────────────────

@pytest.fixture
def curated_dir(tmp_path):
    d = tmp_path / "curated"
    d.mkdir()
    (d / "testland.json").write_text(json.dumps([
        {"year": 2020, "title": "Real Event", "description": "x", "category": "elections_and_voting"},
        {"year": 2021, "title": "Fake Event", "description": "x", "category": "elections_and_voting"},
        {"year": 2022, "title": "Unverified Event", "description": "x", "category": "elections_and_voting"},
    ]), encoding="utf-8")
    return d


def test_parse_verified_events_no_verdict_index_drops_everything(tmp_path, curated_dir):
    """#374: With no verdict_index, NO events are kept (strict-only invariant)."""
    batches_dir = tmp_path / "batches"
    events = ingest_events.parse_verified_events(batches_dir, curated_dir, verdict_index=None)
    assert events == []


def test_parse_verified_events_empty_verdict_index_drops_everything(tmp_path, curated_dir):
    """#374: Empty verdict_index ≡ no verification → zero events ingested."""
    batches_dir = tmp_path / "batches"
    events = ingest_events.parse_verified_events(batches_dir, curated_dir, verdict_index={})
    assert events == []


def test_parse_verified_events_keeps_only_true(tmp_path, curated_dir):
    """#374: TRUE kept, FALSE dropped, unverified dropped (no fallback)."""
    batches_dir = tmp_path / "batches"
    verdict_index = {
        ("testland", 2020, "real event"): "TRUE",
        ("testland", 2021, "fake event"): "FALSE",
        # 2022 "unverified event" NOT in index → dropped under #374 invariant
    }
    events = ingest_events.parse_verified_events(batches_dir, curated_dir, verdict_index=verdict_index)
    titles = {e["title"] for e in events}
    assert titles == {"Real Event"}
    assert "Fake Event" not in titles
    assert "Unverified Event" not in titles


def test_parse_verified_events_heals_encoding_corruption_in_curated(tmp_path):
    """If verdict index title matches curated title after robust normalization, filter triggers."""
    curated = tmp_path / "curated"
    curated.mkdir()
    (curated / "testland.json").write_text(json.dumps([
        {"year": 2020, "title": "PLUA Founded — First Underground",
         "description": "x", "category": "x"}
    ]), encoding="utf-8")
    # Verdict index uses the corrupted variant (replacement char) + FALSE
    verdict_index = {
        ("testland", 2020, ingest_events._normalize_title(
            "PLUA Founded \ufffd First Underground")): "FALSE",
    }
    events = ingest_events.parse_verified_events(tmp_path / "batches", curated, verdict_index)
    assert events == []  # FALSE filtered


def test_parse_verified_events_true_verdict_with_encoding_corruption_still_kept(tmp_path):
    """TRUE verdict with encoding-corrupted title should still match healed curated."""
    curated = tmp_path / "curated"
    curated.mkdir()
    (curated / "testland.json").write_text(json.dumps([
        {"year": 2020, "title": "PLUA Founded — First Underground",
         "description": "x", "category": "x"}
    ]), encoding="utf-8")
    verdict_index = {
        ("testland", 2020, ingest_events._normalize_title(
            "PLUA Founded \ufffd First Underground")): "TRUE",
    }
    events = ingest_events.parse_verified_events(tmp_path / "batches", curated, verdict_index)
    assert len(events) == 1
    assert events[0]["title"] == "PLUA Founded — First Underground"


# ─── stale_partition_country_ids (#374) ──────────────────────────────

def test_stale_partition_country_ids_basic():
    """Countries on S3 but not in current DataFrame are stale → returned for deletion."""
    existing = {1, 2, 3, 4, 5}
    current = {1, 3}
    stale = ingest_events.stale_partition_country_ids(existing, current)
    assert stale == {2, 4, 5}


def test_stale_partition_country_ids_no_stale():
    """Current is a superset → nothing stale."""
    stale = ingest_events.stale_partition_country_ids({1, 2}, {1, 2, 3})
    assert stale == set()


def test_stale_partition_country_ids_empty_current_deletes_all():
    """No current events (all unverified) → every existing partition is stale."""
    stale = ingest_events.stale_partition_country_ids({1, 2, 3}, set())
    assert stale == {1, 2, 3}


def test_stale_partition_country_ids_empty_existing():
    """No existing partitions → nothing to delete."""
    stale = ingest_events.stale_partition_country_ids(set(), {1, 2, 3})
    assert stale == set()
