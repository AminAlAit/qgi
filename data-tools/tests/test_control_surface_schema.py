"""
test_control_surface_schema.py — schema-and-content tests for the indicator
control surface XLSX (`indicators/control-surface.xlsx`), gating regressions
on both the existing WB sheet (`phase_2_indicators`) and the V-Dem sheet
added in #494 step 1 (commit 9edbb12).

Filed as #494 step 3, brought forward per the QA review of step 1
("schema test would fail loudly before the runtime does"). Step 2 (the
ingest_vdem.py refactor that reads from this sheet at runtime) lands
afterward; this test catches schema regressions at CI time so a typo or
column-rename doesn't first surface as a runtime exception during the
annual V-Dem ingest.

Coverage:
- Both sheets carry the canonical 6-column header in identical order
- `numeric_id` is unique across both sheets (no collisions when joined)
- `numeric_id` ranges match the documented allocation
  (WB 1..260, V-Dem 276..314, gap 261..275 reserved for #487)
- Every `vdem_indicators.id_string` matches `^v2[a-z0-9_]+$`
  (V-Dem's variable-naming convention)
- All 39 expected V-Dem id_strings are present
- `status` values are from a known vocabulary
- `category` values are from the canonical taxonomy
"""
from __future__ import annotations

import re
from pathlib import Path

import openpyxl
import pytest


XLSX_PATH = Path(__file__).resolve().parent.parent / "indicators" / "control-surface.xlsx"

CANONICAL_HEADER: tuple[str, ...] = (
    "id_string",
    "numeric_id",
    "name",
    "status",
    "category",
    "description",
)

# Allocation per indicator-catalog-detailed.md §V-Dem and #487 (WB hold/new):
#   - WB existing: 1..260 (260 rows)
#   - WB hold/new (#487): 261..275 reserved (no rows yet — placeholder gap)
#   - V-Dem (#492): 276..314 (39 rows)
EXPECTED_WB_ID_RANGE = (1, 260)
EXPECTED_VDEM_ID_RANGE = (276, 314)
EXPECTED_VDEM_ROW_COUNT = 39

# Status vocabulary — keep extensible. WB rows use `process` and `hold`
# today; V-Dem rows all start at `process`. New values added here as the
# vocabulary expands (each addition is a deliberate decision worth a PR
# diff in this list).
ALLOWED_STATUS_VALUES: frozenset[str] = frozenset({"process", "hold"})

# Canonical category taxonomy (mirrors lib/design.ts SECTOR_COLORS in
# qgi-frontend). New categories must be added in BOTH places — flagging
# here prevents silent drift.
ALLOWED_CATEGORIES: frozenset[str] = frozenset({
    "Economic",
    "Trade",
    "Finance",
    "Energy",
    "Military",
    "Governance",
    "Government",
    "Health",
    "Demographic",
    "Social",
    "Education",
    "Infrastructure",
    "Environment",
    "Other",
})

# V-Dem id_strings follow the V-Dem variable-naming convention:
# `v2x_*` for indices, `v2*` for individual variables. All start with
# `v2` and use lowercase letters / digits / underscores only.
VDEM_ID_REGEX = re.compile(r"^v2[a-z0-9_]+$")

# Expected V-Dem id_strings (matches the order in scripts/ingest_vdem.py
# VDEM_INDICATORS list). If a row is added/removed there, update both
# places; this list pins the contract.
EXPECTED_VDEM_IDS: tuple[str, ...] = (
    "v2x_polyarchy",       # VD-01
    "v2x_libdem",          # VD-02
    "v2x_jucon",           # VD-03
    "v2xlg_legcon",        # VD-04
    "v2csreprss",          # VD-05
    "v2cacamps",           # VD-06
    "v2excrptps",          # VD-07
    "v2x_freexp_altinf",   # VD-08
    "v2x_partip",          # VD-09
    "v2x_regime",          # VD-10
    "v2stfisccap",         # VD-11
    "v2x_clphy",           # VD-12
    "v2clkill",            # VD-13
    "v2cltort",            # VD-14
    "v2x_clpol",           # VD-15
    "v2x_clpriv",          # VD-16
    "v2mecenefm",          # VD-17
    "v2x_corr",            # VD-18
    "v2jureform",          # VD-19
    "v2lgbicam",           # VD-20
    "v2exl_legitlead",     # VD-21
    "v2exremhog",          # VD-22
    "v2xeg_eqprotec",      # VD-23
    "v2cseeorgs",          # VD-24
    "v2csprtcpt",          # VD-25
    "v2x_gender",          # VD-26
    "v2pepwrgen",          # VD-27
    "v2pepwrsoc",          # VD-28
    "v2pepwrort",          # VD-29
    "v2pepwrses",          # VD-30
    "v2x_neopat",          # VD-31
    "v2xel_frefair",       # VD-32
    "v2elintmon",          # VD-33
    "v2ex_hosw",           # VD-34
    "v2exaphogp",          # VD-35
    "v2svdomaut",          # VD-36
    "v2x_rule",            # VD-37
    "v2lgqstexp",          # VD-38
    "v2psprlnks",          # VD-39
)


# ---------------------------------------------------------------------------
# Module-scoped fixtures — open the workbook once per test session
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def workbook():
    if not XLSX_PATH.exists():
        pytest.fail(f"control-surface.xlsx not found at {XLSX_PATH}")
    return openpyxl.load_workbook(XLSX_PATH, read_only=True)


def _iter_data_rows(ws):
    """Yield data rows (skip the header) as tuples."""
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue  # header
        # Skip fully-blank rows (some XLSX files have trailing emptiness).
        if row is None or all(v is None for v in row):
            continue
        yield row


# ---------------------------------------------------------------------------
# Sheet presence and headers
# ---------------------------------------------------------------------------


def test_workbook_has_both_sheets(workbook):
    """Both sheets must exist; new sheets show up here as a deliberate add."""
    assert "phase_2_indicators" in workbook.sheetnames, (
        "WB sheet missing — expected `phase_2_indicators`."
    )
    assert "vdem_indicators" in workbook.sheetnames, (
        "V-Dem sheet missing — expected `vdem_indicators` (added in #494 step 1)."
    )


def test_phase2_header_matches_canonical(workbook):
    ws = workbook["phase_2_indicators"]
    header = list(ws.iter_rows(min_row=1, max_row=1, values_only=True))[0]
    assert tuple(header) == CANONICAL_HEADER, (
        f"phase_2_indicators header drift: {header!r} != {CANONICAL_HEADER!r}"
    )


def test_vdem_header_matches_canonical(workbook):
    ws = workbook["vdem_indicators"]
    header = list(ws.iter_rows(min_row=1, max_row=1, values_only=True))[0]
    assert tuple(header) == CANONICAL_HEADER, (
        f"vdem_indicators header drift: {header!r} != {CANONICAL_HEADER!r}"
    )


def test_both_sheets_share_identical_header(workbook):
    """Defense in depth — even if the canonical tuple changes, the two
    sheets must stay in lockstep."""
    h_wb = list(workbook["phase_2_indicators"].iter_rows(min_row=1, max_row=1, values_only=True))[0]
    h_vd = list(workbook["vdem_indicators"].iter_rows(min_row=1, max_row=1, values_only=True))[0]
    assert tuple(h_wb) == tuple(h_vd)


# ---------------------------------------------------------------------------
# Numeric ID — uniqueness + range allocation
# ---------------------------------------------------------------------------


def _all_numeric_ids(workbook) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for sheet in ("phase_2_indicators", "vdem_indicators"):
        out[sheet] = [int(row[1]) for row in _iter_data_rows(workbook[sheet]) if row[1] is not None]
    return out


def test_numeric_ids_unique_across_sheets(workbook):
    """A numeric_id collision would silently corrupt the
    indicator_map.csv that scdi_finder reads — must never overlap."""
    ids = _all_numeric_ids(workbook)
    wb_ids = set(ids["phase_2_indicators"])
    vd_ids = set(ids["vdem_indicators"])
    overlap = wb_ids & vd_ids
    assert not overlap, f"numeric_id overlap between WB and V-Dem: {sorted(overlap)}"


def test_numeric_ids_unique_within_each_sheet(workbook):
    """No duplicates within a single sheet either."""
    for sheet, id_list in _all_numeric_ids(workbook).items():
        seen = set()
        dupes = []
        for nid in id_list:
            if nid in seen:
                dupes.append(nid)
            seen.add(nid)
        assert not dupes, f"{sheet}: duplicate numeric_id values {dupes}"


def test_phase2_numeric_id_range(workbook):
    ids = _all_numeric_ids(workbook)["phase_2_indicators"]
    assert min(ids) >= EXPECTED_WB_ID_RANGE[0]
    assert max(ids) <= EXPECTED_WB_ID_RANGE[1]
    # A gap exists at numeric_id=165 (originally the duplicate
    # SP.DYN.TFRT.IN row; removed by `scripts/remove_tfrt_duplicate.py`
    # after this very test surfaced the duplicate during #494 step 3).
    # We don't enforce strict contiguity on the WB range — gaps are an
    # acceptable artifact of corrections, and the unique-id and unique-
    # id-string tests above are the contracts that actually matter for
    # downstream consumers.
    KNOWN_WB_GAPS = {165}
    full_range = set(range(EXPECTED_WB_ID_RANGE[0], max(ids) + 1))
    actual_set = set(ids)
    unexpected_gaps = (full_range - actual_set) - KNOWN_WB_GAPS
    assert not unexpected_gaps, (
        f"WB numeric_id range has unexpected gaps: {sorted(unexpected_gaps)}"
    )


def test_vdem_numeric_id_range(workbook):
    ids = _all_numeric_ids(workbook)["vdem_indicators"]
    assert min(ids) == EXPECTED_VDEM_ID_RANGE[0], (
        f"V-Dem first numeric_id should be {EXPECTED_VDEM_ID_RANGE[0]} — got {min(ids)}"
    )
    assert max(ids) == EXPECTED_VDEM_ID_RANGE[1], (
        f"V-Dem last numeric_id should be {EXPECTED_VDEM_ID_RANGE[1]} — got {max(ids)}"
    )
    # Contiguous within V-Dem range
    assert sorted(ids) == list(range(EXPECTED_VDEM_ID_RANGE[0], EXPECTED_VDEM_ID_RANGE[1] + 1))


def test_vdem_row_count(workbook):
    """V-Dem ships with 39 rows (VD-01..VD-39). #492 closed at 39; any
    later addition / removal will break this until updated here."""
    rows = list(_iter_data_rows(workbook["vdem_indicators"]))
    assert len(rows) == EXPECTED_VDEM_ROW_COUNT, (
        f"V-Dem row count drift: expected {EXPECTED_VDEM_ROW_COUNT}, got {len(rows)}"
    )


# ---------------------------------------------------------------------------
# id_string conventions
# ---------------------------------------------------------------------------


def test_vdem_id_strings_match_v2_regex(workbook):
    """V-Dem variable names follow `v2*` — anything else suggests a typo
    or a non-V-Dem indicator landed in the wrong sheet."""
    ws = workbook["vdem_indicators"]
    bad = []
    for row in _iter_data_rows(ws):
        if not VDEM_ID_REGEX.match(row[0] or ""):
            bad.append(row[0])
    assert not bad, f"V-Dem id_strings not matching ^v2[a-z0-9_]+$: {bad}"


def test_vdem_id_strings_match_expected_set(workbook):
    """All 39 expected ids are present, in the expected order. Pins the
    contract that `scripts/ingest_vdem.py` VDEM_INDICATORS and the XLSX
    sheet stay in lockstep."""
    ws = workbook["vdem_indicators"]
    actual = tuple(row[0] for row in _iter_data_rows(ws))
    assert actual == EXPECTED_VDEM_IDS, (
        f"V-Dem id_string drift: actual order/set != expected.\n"
        f"  actual:   {actual}\n"
        f"  expected: {EXPECTED_VDEM_IDS}"
    )


def test_phase2_id_strings_unique(workbook):
    """No duplicate WB id_strings either."""
    ws = workbook["phase_2_indicators"]
    ids = [row[0] for row in _iter_data_rows(ws)]
    seen = set()
    dupes = []
    for s in ids:
        if s in seen:
            dupes.append(s)
        seen.add(s)
    assert not dupes, f"phase_2_indicators duplicate id_strings: {dupes}"


# ---------------------------------------------------------------------------
# Status + category vocabularies
# ---------------------------------------------------------------------------


def test_all_status_values_in_vocabulary(workbook):
    """Catches typos like `actve` / `proces`. Add new values to
    ALLOWED_STATUS_VALUES via PR — that diff is the audit trail for the
    expanded vocabulary."""
    bad = {"phase_2_indicators": [], "vdem_indicators": []}
    for sheet in bad:
        for row in _iter_data_rows(workbook[sheet]):
            if row[3] not in ALLOWED_STATUS_VALUES:
                bad[sheet].append((row[0], row[3]))
    assert all(not v for v in bad.values()), (
        f"Unknown status values: {bad}. "
        f"Allowed: {sorted(ALLOWED_STATUS_VALUES)}"
    )


def test_all_categories_in_taxonomy(workbook):
    """Categories must match the lib/design.ts SECTOR_COLORS taxonomy.
    Adding a new category requires both this file's ALLOWED_CATEGORIES
    AND the qgi-frontend SECTOR_COLORS map to be updated — flagging
    keeps the two in lockstep."""
    bad = {"phase_2_indicators": [], "vdem_indicators": []}
    for sheet in bad:
        for row in _iter_data_rows(workbook[sheet]):
            if row[4] not in ALLOWED_CATEGORIES:
                bad[sheet].append((row[0], row[4]))
    assert all(not v for v in bad.values()), (
        f"Unknown categories: {bad}. "
        f"Allowed: {sorted(ALLOWED_CATEGORIES)}"
    )


# ---------------------------------------------------------------------------
# Description + name presence
# ---------------------------------------------------------------------------


def test_no_blank_descriptions(workbook):
    """Empty descriptions are an exposure — every indicator that ends
    up on the public methodology page or RCI badge tooltip needs at
    least a one-sentence definition."""
    bad = {"phase_2_indicators": [], "vdem_indicators": []}
    for sheet in bad:
        for row in _iter_data_rows(workbook[sheet]):
            if not row[5] or not str(row[5]).strip():
                bad[sheet].append(row[0])
    assert all(not v for v in bad.values()), f"Blank descriptions: {bad}"


def test_no_blank_names(workbook):
    """Indicator name is the human-readable label users see."""
    bad = {"phase_2_indicators": [], "vdem_indicators": []}
    for sheet in bad:
        for row in _iter_data_rows(workbook[sheet]):
            if not row[2] or not str(row[2]).strip():
                bad[sheet].append(row[0])
    assert all(not v for v in bad.values()), f"Blank names: {bad}"
