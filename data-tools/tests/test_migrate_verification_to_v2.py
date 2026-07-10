"""Tests for scripts/migrate_verification_to_v2.py (v2 double-verify migration).

Covers the §3.4 acceptance cases: single→wrapped, idempotent re-run, no-source
entry, malformed-verdict left alone, PARTIAL/UNCERTAIN preserved, dry-run is a
no-op, `_`-prefixed files skipped.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from migrate_verification_to_v2 import main, migrate_entry  # noqa: E402

LEGACY = [
    {"year": 1969, "title": "Aliyev Becomes First Secretary",
     "verdict": "TRUE", "reason": "Confirmed by plenary records.",
     "source": "https://en.wikipedia.org/wiki/Heydar_Aliyev"},
    {"year": 1976, "title": "Politburo Full Membership",
     "verdict": "FALSE", "reason": "Candidate member only in 1976."},
    {"year": 1980, "title": "Some Partial Event",
     "verdict": "PARTIAL", "reason": "Happened, but scope differs.",
     "source": "  https://example.org/x  "},
    {"year": 1990, "title": "Some Uncertain Event",
     "verdict": "UNCERTAIN", "reason": "No independent source found."},
    {"year": 1995, "title": "Malformed Entry",
     "verdict": "VERIFIED", "reason": "old label the migration must not touch"},
]


def write_fixture(d: Path, name: str = "azerbaijan.json", data=None):
    p = d / name
    p.write_text(json.dumps(data if data is not None else LEGACY, indent=2,
                            ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def test_migrate_entry_wraps_single_verdict():
    out = migrate_entry(dict(LEGACY[0]))
    assert out["verify_count"] == 1
    assert out["consensus_verdict"] == "TRUE"
    assert out["consensus_status"] == "single"
    assert out["needs_tiebreak"] is False
    assert out["source_independence"] == "n/a"
    assert out["verdict"] == "TRUE" and out["reason"] == LEGACY[0]["reason"]
    assert out["source"] == LEGACY[0]["source"]
    p1 = out["verifications"][0]
    assert p1["pass_n"] == 1 and p1["verdict"] == "TRUE"
    assert p1["source"] == LEGACY[0]["source"]
    assert p1["verifier"] == {"model": "qgi-agent-verified-pre-migration",
                              "date": None, "method": "web_search"}
    # join keys never mutated
    assert out["year"] == LEGACY[0]["year"] and out["title"] == LEGACY[0]["title"]


def test_migrate_entry_no_source_omits_top_level_source():
    out = migrate_entry(dict(LEGACY[1]))
    assert "source" not in out
    assert out["verifications"][0]["source"] is None
    assert out["consensus_verdict"] == "FALSE"


def test_migrate_entry_strips_whitespace_source():
    out = migrate_entry(dict(LEGACY[2]))
    assert out["source"] == "https://example.org/x"
    assert out["verifications"][0]["source"] == "https://example.org/x"
    assert out["consensus_verdict"] == "PARTIAL"


def test_migrate_entry_preserves_partial_and_uncertain():
    for src, expected in ((LEGACY[2], "PARTIAL"), (LEGACY[3], "UNCERTAIN")):
        out = migrate_entry(dict(src))
        assert out["verdict"] == expected
        assert out["consensus_verdict"] == expected


def test_migrate_entry_leaves_malformed_verdict_alone():
    e = dict(LEGACY[4])
    out = migrate_entry(e)
    assert out is e  # identity: untouched, no wrapping
    assert "verifications" not in out


def test_migrate_entry_idempotent_on_v2():
    once = migrate_entry(dict(LEGACY[0]))
    twice = migrate_entry(once)
    assert twice is once


def test_dry_run_writes_nothing(tmp_path):
    p = write_fixture(tmp_path)
    before = p.read_bytes()
    assert main(["--dir", str(tmp_path)]) == 0
    assert p.read_bytes() == before


def test_apply_then_rerun_is_noop(tmp_path):
    p = write_fixture(tmp_path)
    assert main(["--dir", str(tmp_path), "--apply"]) == 0
    first = p.read_bytes()
    assert not first.startswith(b"\xef\xbb\xbf")  # UTF-8 without BOM
    data = json.loads(first.decode("utf-8"))
    assert sum(1 for e in data if "verifications" in e) == 4  # malformed 5th untouched
    assert data[4] == LEGACY[4]
    # idempotent second apply: byte-identical
    assert main(["--dir", str(tmp_path), "--apply"]) == 0
    assert p.read_bytes() == first


def test_underscore_files_skipped(tmp_path):
    write_fixture(tmp_path)
    ledgerish = write_fixture(tmp_path, "_scratch.json")
    before = ledgerish.read_bytes()
    assert main(["--dir", str(tmp_path), "--apply"]) == 0
    assert ledgerish.read_bytes() == before


def test_split_script_refuses_v2_files(tmp_path):
    """split_verification_by_verdict.py predates v2 and would strip verifications[]
    and drop PARTIAL/UNCERTAIN — its guard must refuse migrated files loudly."""
    import pytest
    from migrate_verification_to_v2 import migrate_entry
    from split_verification_by_verdict import process_file
    p = tmp_path / "azerbaijan.json"
    p.write_text(json.dumps([migrate_entry(dict(LEGACY[0]))]), encoding="utf-8")
    with pytest.raises(SystemExit, match="REFUSING"):
        process_file(p, {}, {})


def test_top_level_verdict_unchanged_for_all_legacy_shapes(tmp_path):
    """The linchpin (§3.0): migration must not move any top-level verdict —
    build_verified_positives.py / ingest_events.py read exactly that field."""
    p = write_fixture(tmp_path)
    assert main(["--dir", str(tmp_path), "--apply"]) == 0
    after = json.loads(p.read_text(encoding="utf-8"))
    for old, new in zip(LEGACY, after):
        assert str(new["verdict"]).upper() == str(old["verdict"]).upper()
        assert new["year"] == old["year"] and new["title"] == old["title"]
