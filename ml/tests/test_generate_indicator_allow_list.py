"""Unit tests for generate_indicator_allow_list.py.

Covers parse_catalog (regex breadth) and build_allow_list (two-path
lookup logic). Does NOT touch S3 — fetch_indicator_map is mocked or
exercised indirectly via build_allow_list with a fake id_to_num.
"""
from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parent.parent / "scripts" / "generate_indicator_allow_list.py"
)
_spec = importlib.util.spec_from_file_location("gen_allow_list", _SCRIPT)
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


# ---------------------------------------------------------------------------
# parse_catalog
# ---------------------------------------------------------------------------

def _write_catalog(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "catalog.md"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def test_parse_catalog_extracts_wb_with_api_code(tmp_path: Path):
    catalog = _write_catalog(tmp_path, """
        # header noise
        | WB-01 | VC.BTL.DETH | Battle deaths | civil_war | 180 |
    """)
    rows = gen.parse_catalog(catalog)
    assert rows == [("WB-01", "VC.BTL.DETH")]


def test_parse_catalog_extracts_vd_with_api_code(tmp_path: Path):
    catalog = _write_catalog(tmp_path, """
        | VD-01 | v2x_polyarchy | Electoral Democracy Index | civil_war | 200 |
    """)
    rows = gen.parse_catalog(catalog)
    assert rows == [("VD-01", "v2x_polyarchy")]


def test_parse_catalog_extracts_fa_with_descriptive_column2(tmp_path: Path):
    """FA-XX rows have descriptive names in column 2 (not API codes).
    The fix: capture the row anyway with api_code=None, so build_allow_list
    can fall back to catalog-code lookup."""
    catalog = _write_catalog(tmp_path, """
        | FA-01 | Prevalence of undernourishment (%) | What % of people don't get enough calories | humanitarian_crisis | 170 |
    """)
    rows = gen.parse_catalog(catalog)
    assert rows == [("FA-01", None)]


def test_parse_catalog_extracts_uc_with_descriptive_column2(tmp_path: Path):
    catalog = _write_catalog(tmp_path, """
        | UC-01 | Battle-related deaths (best estimate, annual) | The definitive count | civil_war | 185 |
    """)
    rows = gen.parse_catalog(catalog)
    assert rows == [("UC-01", None)]


def test_parse_catalog_sorted_by_catalog_code(tmp_path: Path):
    catalog = _write_catalog(tmp_path, """
        | WB-02 | SP.POP.TOTL | Population | foo | 100 |
        | FA-01 | desc with spaces | foo | bar | 100 |
        | VD-01 | v2x_polyarchy | foo | bar | 200 |
        | WB-01 | VC.BTL.DETH | Battle | foo | 180 |
    """)
    rows = gen.parse_catalog(catalog)
    codes = [r[0] for r in rows]
    assert codes == sorted(codes)


def test_parse_catalog_ignores_non_matching_lines(tmp_path: Path):
    """Header rows, separator rows, prose lines should not match."""
    catalog = _write_catalog(tmp_path, """
        # Section header
        Some prose line.
        | # | Code | Name | Categories | Coverage |
        |---|------|------|------------|----------|
        | WB-01 | VC.BTL.DETH | Battle | civil_war | 180 |
    """)
    rows = gen.parse_catalog(catalog)
    # Only the data row matches; header/separator/prose are skipped
    assert rows == [("WB-01", "VC.BTL.DETH")]


# ---------------------------------------------------------------------------
# build_allow_list — two-path lookup
# ---------------------------------------------------------------------------

def test_build_allow_list_path1_api_code_lookup():
    """Standard path: column 2 is an API code that's in indicator_map."""
    catalog = [("WB-01", "VC.BTL.DETH")]
    id_to_num = {"VC.BTL.DETH": 100}
    nums, resolved, unresolved = gen.build_allow_list(catalog, id_to_num)
    assert nums == [100]
    assert resolved == [("WB-01", "VC.BTL.DETH")]
    assert unresolved == []


def test_build_allow_list_path2_catalog_code_lookup():
    """FA-XX path: column 2 is descriptive (None), but catalog code itself
    is in indicator_map (ingester uses catalog code as id_string)."""
    catalog = [("FA-01", None)]
    id_to_num = {"FA-01": 1001}
    nums, resolved, unresolved = gen.build_allow_list(catalog, id_to_num)
    assert nums == [1001]
    assert resolved == [("FA-01", "FA-01")]
    assert unresolved == []


def test_build_allow_list_path1_takes_precedence_over_path2():
    """If both column-2 API code AND catalog code are in indicator_map,
    Path 1 (API code) wins. Should never happen in practice but defines
    deterministic behavior."""
    catalog = [("WB-01", "VC.BTL.DETH")]
    id_to_num = {"VC.BTL.DETH": 100, "WB-01": 999}
    nums, resolved, unresolved = gen.build_allow_list(catalog, id_to_num)
    assert nums == [100]
    assert resolved == [("WB-01", "VC.BTL.DETH")]


def test_build_allow_list_unresolved_when_neither_path_matches():
    """Catalog entry whose API code AND catalog code are both absent from
    indicator_map → goes to unresolved (provider not yet ingested)."""
    catalog = [
        ("WB-01", "VC.BTL.DETH"),  # API code missing from map
        ("UC-01", None),            # catalog code missing from map
    ]
    id_to_num = {}  # empty map
    nums, resolved, unresolved = gen.build_allow_list(catalog, id_to_num)
    assert nums == []
    assert resolved == []
    assert sorted(unresolved) == [("UC-01", None), ("WB-01", "VC.BTL.DETH")]


def test_build_allow_list_dedupes_and_sorts_numeric_ids():
    """If the same numeric_id is reachable via two different catalog rows
    (shouldn't happen, but defensive), it appears once in the output."""
    catalog = [
        ("WB-01", "VC.BTL.DETH"),
        ("FA-01", None),
        ("WB-02", "SP.POP.TOTL"),
    ]
    id_to_num = {
        "VC.BTL.DETH": 100,
        "FA-01": 50,
        "SP.POP.TOTL": 100,  # collision with WB-01 — same numeric_id
    }
    nums, resolved, _ = gen.build_allow_list(catalog, id_to_num)
    assert nums == [50, 100]  # deduped, sorted
    # Both WB-01 and WB-02 still appear in resolved (they're separate
    # catalog entries even if they map to the same numeric_id).
    assert len(resolved) == 3


def test_build_allow_list_mixed_real_world_shape():
    """Simulates the real Phase 5 v0.0b shape: WB+VD via Path 1,
    FA via Path 2, UC via unresolved (not yet ingested)."""
    catalog = [
        ("FA-01", None),
        ("FA-02", None),
        ("UC-01", None),  # not yet ingested
        ("VD-01", "v2x_polyarchy"),
        ("WB-01", "VC.BTL.DETH"),
    ]
    id_to_num = {
        "FA-01": 1001,
        "FA-02": 1002,
        "v2x_polyarchy": 276,
        "VC.BTL.DETH": 1,
    }
    nums, resolved, unresolved = gen.build_allow_list(catalog, id_to_num)
    assert nums == [1, 276, 1001, 1002]
    assert len(resolved) == 4
    assert unresolved == [("UC-01", None)]


# ---------------------------------------------------------------------------
# API_CODE_RE classification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("col2,is_api_code", [
    ("VC.BTL.DETH", True),                    # WB
    ("v2x_polyarchy", True),                   # V-Dem
    ("v2xeg_eqprotec", True),                  # V-Dem
    ("GFDD.DI.01", True),                      # WB
    ("Prevalence of undernourishment (%)", False),  # FA descriptive
    ("Battle-related deaths (best estimate, annual)", False),  # UC descriptive
    ("Average news tone per year", False),     # GD descriptive
])
def test_api_code_re_classification(col2: str, is_api_code: bool):
    assert bool(gen.API_CODE_RE.match(col2)) == is_api_code


# ---------------------------------------------------------------------------
# build_json_payload — single-pass resolution (#600 Finding 4)
# ---------------------------------------------------------------------------

def test_build_json_payload_resolves_numeric_ids_inline():
    """Regression for the two-pass seam: build_json_payload must
    populate resolved[].numeric_id at construction time, not leave it
    None for a separate pass to fill. Reason: a future caller that
    forgets the second call would silently emit numeric_id=null in the
    metadata for every resolved row."""
    resolved = [("WB-01", "VC.BTL.DETH"), ("VD-02", "v2x_polyarchy")]
    unresolved = [("UC-01", "ucdp_battle_deaths_pending")]
    id_to_num = {
        "VC.BTL.DETH": 1001,
        "v2x_polyarchy": 1002,
    }

    payload = gen.build_json_payload(
        bucket="test-bucket",
        catalog_rows_total=142,
        resolved=resolved,
        unresolved=unresolved,
        numeric_ids=[1001, 1002],
        catalog_sha256="abc123",
        id_to_num=id_to_num,
    )

    # Every resolved entry has its numeric_id filled in
    for entry in payload["resolved"]:
        assert entry["numeric_id"] is not None, (
            f"build_json_payload left numeric_id=None on resolved entry "
            f"{entry['catalog_code']!r}; the two-pass seam is back"
        )
    # Verify the actual values
    by_catalog = {e["catalog_code"]: e["numeric_id"] for e in payload["resolved"]}
    assert by_catalog == {"WB-01": 1001, "VD-02": 1002}
    # Unresolved entries don't get a numeric_id (pending ingestion)
    assert all("numeric_id" not in u
               for u in payload["unresolved_pending_ingestion"])


def test_build_json_payload_raises_on_missing_id_mapping():
    """If id_to_num is missing an api_code that's in `resolved`, the
    function must raise KeyError loudly — silent None-fill would be
    the pre-fix behavior we're trying to eliminate."""
    resolved = [("WB-01", "VC.BTL.DETH"), ("VD-02", "v2x_polyarchy")]
    id_to_num = {"VC.BTL.DETH": 1001}  # v2x_polyarchy intentionally missing

    with pytest.raises(KeyError, match="v2x_polyarchy"):
        gen.build_json_payload(
            bucket="test-bucket",
            catalog_rows_total=142,
            resolved=resolved,
            unresolved=[],
            numeric_ids=[1001],
            catalog_sha256="abc123",
            id_to_num=id_to_num,
        )


def test_fill_resolved_numeric_ids_helper_removed():
    """The standalone fill_resolved_numeric_ids() helper was removed in
    #600 Finding 4 to collapse the two-pass seam. If a future change
    re-introduces it (e.g. by re-splitting the function), this test
    fails and forces the reviewer to revisit whether the seam is
    justified."""
    assert not hasattr(gen, "fill_resolved_numeric_ids"), (
        "fill_resolved_numeric_ids() was deliberately removed in #600 "
        "Finding 4. If re-introducing it, either delete this test with "
        "justification OR re-think the single-pass design."
    )
