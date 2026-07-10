"""Tests for scripts/validate_verification.py (verification-file CI gate + the
Python parity port of the §3.3 consensus rule).

The consensus vectors live in tests/consensus_vectors.json and are shared with
workflows/events/schemas.test.mjs — the same file locks the JS canonical
implementation and this Python port together.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from migrate_verification_to_v2 import migrate_entry  # noqa: E402
from validate_verification import (  # noqa: E402
    _norm_title, recompute_consensus, validate_directory,
)

VECTORS = json.loads(
    (Path(__file__).resolve().parent / "consensus_vectors.json").read_text(encoding="utf-8"))


# ─── consensus parity ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("case", VECTORS["consensus_vectors"],
                         ids=lambda c: f"{c.get('policy','default')}:{'+'.join(c['passes'])}")
def test_consensus_vectors(case):
    passes = [{"verdict": v} for v in case["passes"]]
    got = recompute_consensus(passes, case.get("policy", "conservative_downgrade"))
    for key, want in case["expected"].items():
        assert got.get(key) == want, f"{key}: got {got.get(key)!r}, want {want!r}"
    assert got["verdict"] == got["consensus_verdict"]  # legacy-reader alias
    if "had_dissent" not in case["expected"]:
        assert "had_dissent" not in got


def test_consensus_rejects_empty_and_invalid():
    with pytest.raises(ValueError):
        recompute_consensus([])
    with pytest.raises(ValueError):
        recompute_consensus([{"verdict": "CONTESTED"}])  # pass verdicts never CONTESTED


@pytest.mark.parametrize("raw,expected", VECTORS["norm_title_vectors"])
def test_norm_title_vectors(raw, expected):
    assert _norm_title(raw) == expected


# ─── directory validation ─────────────────────────────────────────────────────

CURATED_EVENT = {"year": 1969, "title": "Aliyev Becomes First Secretary",
                 "description": "Elected at the plenary on 12 July 1969, consolidating his rise.",
                 "category": "executive_power_consolidation"}
LEGACY_ENTRY = {"year": 1969, "title": "Aliyev Becomes First Secretary",
                "verdict": "TRUE", "reason": "Confirmed by plenary records.",
                "source": "https://en.wikipedia.org/wiki/Heydar_Aliyev"}


def make_dirs(tmp_path, curated=None, verification=None, slug="azerbaijan"):
    cdir, vdir = tmp_path / "curated", tmp_path / "verification"
    cdir.mkdir(parents=True); vdir.mkdir(parents=True)
    if curated is not None:
        (cdir / f"{slug}.json").write_text(json.dumps(curated), encoding="utf-8")
    if verification is not None:
        (vdir / f"{slug}.json").write_text(json.dumps(verification), encoding="utf-8")
    return vdir, cdir


def test_legacy_file_valid(tmp_path):
    vdir, cdir = make_dirs(tmp_path, [CURATED_EVENT], [LEGACY_ENTRY])
    errors, warnings, n_files, n_entries = validate_directory(vdir, cdir)
    assert errors == [] and n_files == 1 and n_entries == 1


def test_migrated_file_valid(tmp_path):
    vdir, cdir = make_dirs(tmp_path, [CURATED_EVENT], [migrate_entry(dict(LEGACY_ENTRY))])
    errors, warnings, *_ = validate_directory(vdir, cdir)
    assert errors == []


def test_legacy_contested_is_error(tmp_path):
    bad = dict(LEGACY_ENTRY, verdict="CONTESTED")
    vdir, cdir = make_dirs(tmp_path, [CURATED_EVENT], [bad])
    errors, *_ = validate_directory(vdir, cdir)
    assert any("CONTESTED requires the v2 shape" in e for e in errors)


def test_verify_count_mismatch_is_error(tmp_path):
    v2 = migrate_entry(dict(LEGACY_ENTRY))
    v2["verify_count"] = 2
    vdir, cdir = make_dirs(tmp_path, [CURATED_EVENT], [v2])
    errors, *_ = validate_directory(vdir, cdir)
    assert any("verify_count" in e for e in errors)


def test_consensus_mismatch_is_error(tmp_path):
    v2 = migrate_entry(dict(LEGACY_ENTRY))
    v2["verifications"].append({"pass_n": 2, "verdict": "FALSE", "reason": "refuted",
                                "source": None,
                                "verifier": {"model": "m", "date": None, "method": "web_search"}})
    v2["verify_count"] = 2
    # top-level verdict left TRUE, but recompute says CONTESTED
    vdir, cdir = make_dirs(tmp_path, [CURATED_EVENT], [v2])
    errors, *_ = validate_directory(vdir, cdir)
    assert any("consensus mismatch" in e for e in errors)


def test_consistent_contested_v2_valid(tmp_path):
    v2 = migrate_entry(dict(LEGACY_ENTRY))
    v2["verifications"].append({"pass_n": 2, "verdict": "FALSE", "reason": "refuted",
                                "source": None,
                                "verifier": {"model": "m", "date": None, "method": "web_search"}})
    v2.update(verify_count=2, verdict="CONTESTED", consensus_verdict="CONTESTED",
              consensus_status="contested_open", needs_tiebreak=True)
    vdir, cdir = make_dirs(tmp_path, [CURATED_EVENT], [v2])
    errors, *_ = validate_directory(vdir, cdir)
    assert errors == []


def _soft_kept_entry():
    v2 = migrate_entry(dict(LEGACY_ENTRY))
    v2["verifications"].append({"pass_n": 2, "verdict": "UNCERTAIN",
                                "reason": "no independent source found", "source": None,
                                "verifier": {"model": "m", "date": None, "method": "web_search"}})
    v2.update(verify_count=2, verdict="TRUE", consensus_verdict="TRUE",
              consensus_status="soft_kept", needs_tiebreak=False)
    return v2


def test_soft_kept_rejected_under_ratified_conservative_policy(tmp_path):
    """B1 ratified 2026-07-02 = conservative_downgrade: a TRUE/soft_kept entry (a
    hand-promotion of a downgraded verdict) must fail CI under the active policy —
    both when passed explicitly and via the default load of the ratified file."""
    vdir, cdir = make_dirs(tmp_path, [CURATED_EVENT], [_soft_kept_entry()])
    errors, *_ = validate_directory(vdir, cdir, active_policy="conservative_downgrade")
    assert any("consensus mismatch" in e for e in errors)
    errors, *_ = validate_directory(vdir, cdir)  # default: loads the ratified policy file
    assert any("consensus mismatch" in e for e in errors)


def test_soft_kept_valid_under_majority_policy_and_fallback(tmp_path):
    """The same entry is legitimate under majority_overturn, and under the
    either-policy fallback used when no policy file exists (pre-ratification)."""
    vdir, cdir = make_dirs(tmp_path, [CURATED_EVENT], [_soft_kept_entry()])
    errors, *_ = validate_directory(vdir, cdir, active_policy="majority_overturn")
    assert errors == []
    errors, *_ = validate_directory(vdir, cdir, active_policy=None)  # no-file fallback
    assert errors == []


def test_load_active_policy_missing_file_returns_none(tmp_path):
    from validate_verification import load_active_policy
    assert load_active_policy(tmp_path / "nope.json") is None
    assert load_active_policy() == "conservative_downgrade"  # the ratified repo file


def test_hidden_dissent_is_error(tmp_path):
    """[TRUE,FALSE,TRUE] stored as clean double_confirmed without had_dissent must
    fail — it would silently skip the founder spot-check queue."""
    v2 = migrate_entry(dict(LEGACY_ENTRY))
    mk = lambda n, v: {"pass_n": n, "verdict": v, "reason": f"r{n}", "source": None,
                       "verifier": {"model": "m", "date": None, "method": "web_search"}}
    v2["verifications"] = [mk(1, "TRUE"), mk(2, "FALSE"), mk(3, "TRUE")]
    v2.update(verify_count=3, verdict="TRUE", consensus_verdict="TRUE",
              consensus_status="double_confirmed", needs_tiebreak=False)
    vdir, cdir = make_dirs(tmp_path, [CURATED_EVENT], [v2])
    errors, *_ = validate_directory(vdir, cdir)
    assert any("consensus mismatch" in e for e in errors)
    # the honest encoding (contested_resolved + had_dissent) passes
    v2.update(consensus_status="contested_resolved", had_dissent=True)
    vdir2, cdir2 = make_dirs(tmp_path / "b", [CURATED_EVENT], [v2])
    errors, *_ = validate_directory(vdir2, cdir2)
    assert errors == []


def test_bogus_contested_status_is_error(tmp_path):
    """TRUE/TRUE stored as contested_open must fail — it would make plan-b
    re-select and waste passes on a settled event."""
    v2 = migrate_entry(dict(LEGACY_ENTRY))
    v2["verifications"].append({"pass_n": 2, "verdict": "TRUE", "reason": "confirmed again",
                                "source": None,
                                "verifier": {"model": "m", "date": None, "method": "web_search"}})
    v2.update(verify_count=2, verdict="TRUE", consensus_verdict="TRUE",
              consensus_status="contested_open", needs_tiebreak=False)
    vdir, cdir = make_dirs(tmp_path, [CURATED_EVENT], [v2])
    errors, *_ = validate_directory(vdir, cdir)
    assert any("consensus mismatch" in e for e in errors)


def test_pass_n_sequence_enforced(tmp_path):
    v2 = migrate_entry(dict(LEGACY_ENTRY))
    v2["verifications"][0]["pass_n"] = 7
    vdir, cdir = make_dirs(tmp_path, [CURATED_EVENT], [v2])
    errors, *_ = validate_directory(vdir, cdir)
    assert any("pass_n" in e for e in errors)


def test_orphan_warns_by_default_errors_when_strict(tmp_path):
    orphan = dict(LEGACY_ENTRY, title="A Title No Curated Event Has")
    vdir, cdir = make_dirs(tmp_path, [CURATED_EVENT], [orphan])
    errors, warnings, *_ = validate_directory(vdir, cdir)
    assert errors == [] and any("orphan verdict" in w for w in warnings)
    errors, warnings, *_ = validate_directory(vdir, cdir, strict_join=True)
    assert any("orphan verdict" in e for e in errors)


def test_verification_without_curated_file_is_error(tmp_path):
    vdir, cdir = make_dirs(tmp_path, curated=None, verification=[LEGACY_ENTRY])
    errors, *_ = validate_directory(vdir, cdir)
    assert any("must shadow a curated country file" in e for e in errors)


def test_bom_is_error(tmp_path):
    vdir, cdir = make_dirs(tmp_path, [CURATED_EVENT], None)
    (vdir / "azerbaijan.json").write_bytes(
        b"\xef\xbb\xbf" + json.dumps([LEGACY_ENTRY]).encode("utf-8"))
    errors, *_ = validate_directory(vdir, cdir)
    assert any("BOM" in e for e in errors)


def test_underscore_files_skipped(tmp_path):
    vdir, cdir = make_dirs(tmp_path, [CURATED_EVENT], [LEGACY_ENTRY])
    (vdir / "_ledgerish.json").write_text("{not json", encoding="utf-8")
    errors, *_ = validate_directory(vdir, cdir)
    assert errors == []


def test_live_repo_passes():
    """The gate must be green on the repo as it stands (pre-migration, legacy
    files, known orphans as warnings) — otherwise it can't be wired to CI.
    Asserts validity only, NOT corpus size (legitimate cleanups shrink it)."""
    errors, warnings, n_files, n_entries = validate_directory()
    assert n_files > 0 and n_entries > 0
    assert errors == [], errors[:10]
