"""
Tests for the XLSX-driven V-Dem indicator loader in `scripts/ingest_vdem.py`
(#494 step 2). Covers `load_vdem_indicators_from_xlsx` + `resolve_xlsx_path`.

Why this matters:
- Step 2 replaces the hardcoded `VDEM_INDICATORS` list with a runtime
  read of `indicators/control-surface.xlsx` (sheet `vdem_indicators`).
  If the loader silently returns the wrong indicators, every subsequent
  V-Dem ingest writes wrong partitions to the data lake.
- The schema test (test_control_surface_schema.py) enforces the XLSX
  shape; this file enforces that the loader USES that shape correctly.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import openpyxl
import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "ingest_vdem.py"
LIVE_XLSX = REPO_ROOT / "indicators" / "control-surface.xlsx"


def _import_ingest_vdem():
    """Import the script as a module without invoking main()."""
    spec = importlib.util.spec_from_file_location("ingest_vdem_under_test", str(SCRIPT_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ingest_vdem():
    return _import_ingest_vdem()


# ---------------------------------------------------------------------------
# Loader tests against the live XLSX (integration-style, no fixture)
# ---------------------------------------------------------------------------


def test_loader_returns_39_active_indicators(ingest_vdem):
    """The shipped XLSX has 39 V-Dem rows, all status=process. Loader
    must return all 39."""
    indicators = ingest_vdem.load_vdem_indicators_from_xlsx(LIVE_XLSX)
    assert len(indicators) == 39, (
        f"Expected 39 active V-Dem indicators in {LIVE_XLSX}, got {len(indicators)}"
    )


def test_loader_returns_id_strings_in_sheet_order(ingest_vdem):
    """Sheet order is meaningful — preserves the VD-XX catalog ordering.
    First entry must be `v2x_polyarchy` (VD-01), last `v2psprlnks` (VD-39)."""
    indicators = ingest_vdem.load_vdem_indicators_from_xlsx(LIVE_XLSX)
    assert indicators[0] == "v2x_polyarchy"
    assert indicators[-1] == "v2psprlnks"


def test_loader_returns_only_v2_prefixed_strings(ingest_vdem):
    """All V-Dem variable names start with `v2`. Anything else means a
    non-V-Dem indicator landed in the V-Dem sheet."""
    indicators = ingest_vdem.load_vdem_indicators_from_xlsx(LIVE_XLSX)
    bad = [i for i in indicators if not i.startswith("v2")]
    assert not bad, f"V-Dem loader returned non-v2 strings: {bad}"


# ---------------------------------------------------------------------------
# Loader tests with synthetic fixture XLSX (filter / error paths)
# ---------------------------------------------------------------------------


def _build_fixture_xlsx(
    tmp_path: Path,
    rows: list[tuple[str, int, str, str, str, str]],
    sheet_name: str = "vdem_indicators",
) -> Path:
    """Build a one-sheet XLSX matching the canonical 6-column header."""
    path = tmp_path / "fixture.xlsx"
    wb = openpyxl.Workbook()
    # openpyxl creates a default 'Sheet'; rename if needed
    ws = wb.active
    ws.title = sheet_name
    ws.append(["id_string", "numeric_id", "name", "status", "category", "description"])
    for row in rows:
        ws.append(list(row))
    wb.save(path)
    return path


def test_loader_skips_hold_rows(ingest_vdem, tmp_path):
    """Rows with status='hold' must NOT appear in the active list."""
    fixture = _build_fixture_xlsx(
        tmp_path,
        [
            ("v2x_polyarchy", 276, "Electoral Democracy Index",
             "process", "Governance", "active"),
            ("v2x_libdem",    277, "Liberal Democracy Index",
             "hold",    "Governance", "held"),  # hold — should be skipped
            ("v2x_jucon",     278, "Judicial Constraints",
             "process", "Governance", "active"),
        ],
    )
    indicators = ingest_vdem.load_vdem_indicators_from_xlsx(fixture)
    assert indicators == ["v2x_polyarchy", "v2x_jucon"], (
        f"hold filtering failed; got {indicators}"
    )


def test_loader_raises_on_missing_xlsx(ingest_vdem, tmp_path):
    """Missing XLSX path = FileNotFoundError with a helpful message."""
    missing = tmp_path / "does-not-exist.xlsx"
    with pytest.raises(FileNotFoundError) as excinfo:
        ingest_vdem.load_vdem_indicators_from_xlsx(missing)
    assert "indicator catalog XLSX not found" in str(excinfo.value)
    # Helpful: mentions the env var override
    assert "INDICATOR_CATALOG_XLSX_PATH" in str(excinfo.value)


def test_loader_raises_on_missing_sheet(ingest_vdem, tmp_path):
    """XLSX exists but doesn't have `vdem_indicators` sheet → ValueError
    with a message that explains the schema requirement (per the PR #3
    review nit — must NOT instruct the operator to "Run add_vdem_sheet.py"
    since that script is THROWAWAY and not safely re-runnable)."""
    fixture = _build_fixture_xlsx(
        tmp_path,
        [("v2x_polyarchy", 276, "x", "process", "Governance", "x")],
        sheet_name="other_sheet",  # wrong sheet name
    )
    with pytest.raises(ValueError) as excinfo:
        ingest_vdem.load_vdem_indicators_from_xlsx(fixture)
    msg = str(excinfo.value)
    assert "vdem_indicators" in msg
    assert "missing" in msg
    # Helpful: points at the schema reference, not a re-run instruction
    assert "expected schema" in msg
    # Defensive: must NOT say "Run scripts/add_vdem_sheet.py to populate"
    # which would mislead an operator into double-populating a live XLSX
    assert "Run scripts/add_vdem_sheet.py to populate" not in msg


def test_loader_raises_when_no_active_rows(ingest_vdem, tmp_path):
    """All rows held → ValueError. The schema-drift signal."""
    fixture = _build_fixture_xlsx(
        tmp_path,
        [
            ("v2x_polyarchy", 276, "x", "hold", "Governance", "x"),
            ("v2x_libdem",    277, "x", "hold", "Governance", "x"),
        ],
    )
    with pytest.raises(ValueError) as excinfo:
        ingest_vdem.load_vdem_indicators_from_xlsx(fixture)
    assert "no V-Dem indicators with status='process'" in str(excinfo.value)


def test_loader_skips_blank_trailing_rows(ingest_vdem, tmp_path):
    """openpyxl may yield trailing rows that are entirely None. The
    loader must skip them gracefully — defensive against XLSX edits
    that leave blank rows at the bottom."""
    fixture = _build_fixture_xlsx(
        tmp_path,
        [
            ("v2x_polyarchy", 276, "x", "process", "Governance", "x"),
        ],
    )
    # Append a blank-ish row by directly mutating the workbook
    wb = openpyxl.load_workbook(fixture)
    ws = wb["vdem_indicators"]
    ws.append([None, None, None, None, None, None])
    wb.save(fixture)
    indicators = ingest_vdem.load_vdem_indicators_from_xlsx(fixture)
    assert indicators == ["v2x_polyarchy"]


# ---------------------------------------------------------------------------
# resolve_xlsx_path precedence
# ---------------------------------------------------------------------------


def test_resolve_xlsx_path_cli_wins(ingest_vdem, tmp_path, monkeypatch):
    """CLI override beats env var beats default."""
    cli = tmp_path / "cli.xlsx"
    monkeypatch.setenv("INDICATOR_CATALOG_XLSX_PATH", str(tmp_path / "env.xlsx"))
    assert ingest_vdem.resolve_xlsx_path(cli) == cli


def test_resolve_xlsx_path_env_wins_over_default(ingest_vdem, tmp_path, monkeypatch):
    """When --xlsx-path is None, env var beats the default repo path."""
    env_path = tmp_path / "env.xlsx"
    monkeypatch.setenv("INDICATOR_CATALOG_XLSX_PATH", str(env_path))
    assert ingest_vdem.resolve_xlsx_path(None) == env_path


def test_resolve_xlsx_path_default(ingest_vdem, monkeypatch):
    """No CLI, no env → default (repo-root path)."""
    monkeypatch.delenv("INDICATOR_CATALOG_XLSX_PATH", raising=False)
    resolved = ingest_vdem.resolve_xlsx_path(None)
    assert resolved == ingest_vdem.DEFAULT_XLSX_PATH


def test_default_xlsx_path_points_to_repo_indicators_dir(ingest_vdem):
    """Sanity: the default path points to the right folder, not somewhere
    surprising. Catches a refactor that accidentally moved DEFAULT_XLSX_PATH."""
    assert ingest_vdem.DEFAULT_XLSX_PATH.parent.name == "indicators"
    assert ingest_vdem.DEFAULT_XLSX_PATH.name == "control-surface.xlsx"
