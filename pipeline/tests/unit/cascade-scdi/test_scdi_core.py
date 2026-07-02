"""Unit tests for the cascade SCDI bake core (§H): the founder's balanced ranking
(NOT PPS), greedy size-fill, slug construction, and the z-score/downsample/pearson
transforms. Pure functions — no S3, no Athena.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "batch" / "cascade-scdi"))
import scdi_core as sc  # noqa: E402


# ---- balanced_scores: must de-bias length (the whole point vs PPS) ----------


def test_balanced_score_beats_pps_length_bias():
    # A: strong corr, SHORT, many indicators. B: weak corr, LONG, few indicators.
    A = {"corr": 0.9, "length": 10, "n_ind": 5}
    B = {"corr": 0.5, "length": 60, "n_ind": 2}
    # PPS would rank B (0.5*60*2=60) ABOVE A (0.9*10*5=45) — pure length bias.
    s = sc.balanced_scores([A, B])
    assert s[0] > s[1]  # balanced ranks the strong/short/rich pattern FIRST
    # exact: A -> 0.34*1 + 0.36*1 + 0.30*0 = 0.70 ; B -> 0.30
    assert s == [0.70, 0.30]


def test_balanced_score_tilts_to_indicators_over_length():
    # equal corr; one pattern maxes #indicators, the other maxes length.
    hi_nind = {"corr": 1.0, "length": 1, "n_ind": 10}
    hi_len = {"corr": 1.0, "length": 10, "n_ind": 1}
    s = sc.balanced_scores([hi_nind, hi_len])
    assert s[0] > s[1]  # #indicators (0.36) beats length (0.30)
    assert s == [0.36, 0.30]


def test_balanced_scores_empty():
    assert sc.balanced_scores([]) == []


# ---- rank_and_fill: greedy to the size cap ----------------------------------


def test_rank_and_fill_greedy_to_cap_in_score_order():
    ws = [{"corr": c, "length": 5, "n_ind": 3, "id": c} for c in (0.1, 0.9, 0.5)]
    sel, total = sc.rank_and_fill(ws, size_cap_bytes=250, per_pattern_bytes=lambda w: 100)
    assert [w["id"] for w in sel] == [0.9, 0.5]  # top-2 by score; 3rd would overflow
    assert total == 200


def test_rank_and_fill_skips_overflow_keeps_smaller_later():
    ws = [{"corr": 0.9, "length": 5, "n_ind": 3, "sz": 300}, {"corr": 0.5, "length": 5, "n_ind": 3, "sz": 50}]
    sel, total = sc.rank_and_fill(ws, size_cap_bytes=100, per_pattern_bytes=lambda w: w["sz"])
    assert [w["sz"] for w in sel] == [50]  # big one skipped, small fits
    assert total == 50


# ---- build_slug -------------------------------------------------------------


def test_build_slug_aligned_4_segment():
    assert sc.build_slug("PT", "ES", 1975, 1975, 50) == "pt-es-1975-2024"


def test_build_slug_offset_5_segment():
    assert sc.build_slug("KE", "PS", 1998, 2004, 19) == "ke-ps-1998-2004-19"


# ---- zscore_downsample ------------------------------------------------------


def test_zscore_no_downsample_when_lengths_match():
    out = sc.zscore_downsample([10, 20, 30, 40, 50], n_epochs=5)
    assert out == [-1.4142, -0.7071, 0.0, 0.7071, 1.4142]


def test_zscore_downsample_to_12_preserves_endpoints():
    out = sc.zscore_downsample(list(range(25)), n_epochs=12)
    assert len(out) == 12
    assert out[0] < 0 and out[-1] > 0  # z of first < mean, last > mean
    assert out[0] == round((0 - 12) / (sum((i - 12) ** 2 for i in range(25)) / 25) ** 0.5, 4)


def test_zscore_empty():
    assert sc.zscore_downsample([]) == []


def test_zscore_single_epoch_returns_first_zscore():
    # n_epochs=1 -> z-score of the first window point (documented single-epoch contract)
    assert sc.zscore_downsample([10, 20, 30, 40, 50], n_epochs=1) == [-1.4142]


# ---- pearson_r + direction --------------------------------------------------


def test_pearson_perfect_and_anti():
    assert sc.pearson_r([1, 2, 3], [2, 4, 6]) == 1.0
    assert sc.pearson_r([1, 2, 3], [3, 2, 1]) == -1.0


def test_pearson_undefined_cases():
    assert sc.pearson_r([1, 1, 1], [1, 2, 3]) is None  # constant series
    assert sc.pearson_r([1, 2], [1, 2, 3]) is None  # length mismatch
    assert sc.pearson_r([1], [1]) is None  # n < 2


def test_direction():
    assert sc.direction(0.5) == "same"
    assert sc.direction(-0.01) == "opposite"
    assert sc.direction(0.0) == "same"
    assert sc.direction(None) is None
