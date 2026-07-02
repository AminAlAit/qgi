"""Unit tests for resolve_frontier_year in the recipe-fleet entrypoint (#111 D2).

The entrypoint lives under batch/recipe-fleet/ (NOT a Python package), so we load
it via importlib. resolve_frontier_year is a pure function (pandas + Path only).
It replaces the hardcoded EVALUATION_YEAR=2021: the scoring frontier is the max
OBSERVED year (is_predicted rows discarded, D1) across the recipe's selected
indicators, plus 1.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

_ENTRYPOINT = Path(__file__).resolve().parents[3] / "batch" / "recipe-fleet" / "recipe_fleet_entrypoint.py"


def _load_entrypoint():
    spec = importlib.util.spec_from_file_location("recipe_fleet_entrypoint", _ENTRYPOINT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["recipe_fleet_entrypoint"] = mod
    spec.loader.exec_module(mod)
    return mod


ep = _load_entrypoint()


def _write_panel(panel_dir: Path, ind: str, rows: list[dict]) -> None:
    d = panel_dir / ind
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(d / f"{ind}.parquet")


def test_frontier_is_max_observed_plus_one(tmp_path):
    _write_panel(tmp_path, "A", [{"country": "X", "year": y, "value": 1.0} for y in range(2010, 2023)])
    _write_panel(tmp_path, "B", [{"country": "X", "year": y, "value": 1.0} for y in range(2010, 2020)])
    # max observed across A(2022) and B(2019) → 2022 → frontier 2023
    assert ep.resolve_frontier_year(["A", "B"], tmp_path) == 2023


def test_frontier_discards_predicted_rows(tmp_path):
    rows = [{"country": "X", "year": y, "value": 1.0, "is_predicted": False} for y in range(2010, 2021)]
    rows += [{"country": "X", "year": y, "value": 9.0, "is_predicted": True} for y in range(2021, 2027)]
    _write_panel(tmp_path, "A", rows)
    # observed stops at 2020 → frontier 2021 (predicted 2021-2026 ignored, D1)
    assert ep.resolve_frontier_year(["A"], tmp_path) == 2021


def test_missing_panel_is_skipped_not_fatal(tmp_path):
    _write_panel(tmp_path, "A", [{"country": "X", "year": y, "value": 1.0} for y in range(2010, 2021)])
    # "B" has no parquet → skipped with a warning, frontier from "A"
    assert ep.resolve_frontier_year(["A", "B_missing"], tmp_path) == 2021


def test_no_observed_rows_raises(tmp_path):
    _write_panel(
        tmp_path, "A", [{"country": "X", "year": y, "value": None, "is_predicted": False} for y in range(2010, 2021)]
    )
    with pytest.raises(RuntimeError, match="Could not resolve scoring frontier"):
        ep.resolve_frontier_year(["A"], tmp_path)
