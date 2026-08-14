"""Unit tests for assemble_recipe_floors.build_path_c_floor_rows (FLEET-1b/#960)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import assemble_recipe_floors as asm  # noqa: E402


def test_floor_rows_cohort_is_lock_minus_gap():
    bl = {"r1": {"lock_floor": 0.70, "naive_loco": 0.55, "naive_winner": "NB2",
                 "floor_basis": "absolute_0.70"}}
    rows = asm.build_path_c_floor_rows(bl, cohort_gap=0.06)
    assert rows["r1"]["lock_floor"] == 0.70
    assert rows["r1"]["cohort_loco_floor"] == 0.64
    assert rows["r1"]["path"] == "c" and rows["r1"]["wave"] == "c"
    assert rows["r1"]["basis_loco"] == 0.55


def test_relative_floor_cohort_rounds_to_4dp():
    bl = {"r2": {"lock_floor": 0.7191, "naive_loco": 0.6891, "naive_winner": "NB2",
                 "floor_basis": "relative"}}
    rows = asm.build_path_c_floor_rows(bl)
    assert rows["r2"]["cohort_loco_floor"] == 0.6591  # 0.7191 - 0.06, exact (no 0.66 rounding)


def test_errored_or_floorless_recipe_gets_no_row():
    bl = {
        "ok": {"lock_floor": 0.70, "naive_loco": 0.5, "naive_winner": "NB1", "floor_basis": "absolute_0.70"},
        "boom": {"error": "panel missing"},
        "nofloor": {"naive_loco": 0.5},  # no lock_floor
    }
    rows = asm.build_path_c_floor_rows(bl)
    assert set(rows) == {"ok"}  # the failed/floorless ones are omitted → fleet skips them loudly
