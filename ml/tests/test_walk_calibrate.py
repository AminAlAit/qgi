"""Tests for `qgi_ml.src.walk.calibrate`."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from walk.calibrate import IsotonicCalibrator, stratified_train_cal_split  # noqa: E402


# -- IsotonicCalibrator ------------------------------------------------------


class TestIsotonicCalibrator:
    def test_fit_then_predict_returns_array(self) -> None:
        rng = np.random.default_rng(0)
        n = 200
        raw = rng.random(n)
        labels = (raw + rng.normal(0, 0.1, n) > 0.5).astype(int)
        cal = IsotonicCalibrator()
        cal.fit(raw, labels)
        out = cal.predict(raw)
        assert out.shape == (n,)
        assert (out >= 0).all() and (out <= 1).all()

    def test_monotonic_output(self) -> None:
        rng = np.random.default_rng(0)
        n = 200
        raw = rng.random(n)
        labels = (raw > 0.5).astype(int)
        cal = IsotonicCalibrator().fit(raw, labels)
        # Apply to sorted inputs; output must be non-decreasing.
        sorted_raw = np.sort(np.linspace(0, 1, 50))
        sorted_pred = cal.predict(sorted_raw)
        assert np.all(np.diff(sorted_pred) >= -1e-9)

    def test_unfitted_predict_raises(self) -> None:
        cal = IsotonicCalibrator()
        with pytest.raises(RuntimeError, match="not fitted"):
            cal.predict(np.array([0.5]))

    def test_unfitted_serialize_raises(self) -> None:
        cal = IsotonicCalibrator()
        with pytest.raises(RuntimeError, match="cannot serialize unfitted"):
            cal.to_dict()

    def test_empty_input_raises(self) -> None:
        cal = IsotonicCalibrator()
        with pytest.raises(ValueError, match="empty"):
            cal.fit(np.array([]), np.array([]))

    def test_shape_mismatch_raises(self) -> None:
        cal = IsotonicCalibrator()
        with pytest.raises(ValueError, match="shape mismatch"):
            cal.fit(np.array([0.1, 0.2]), np.array([0, 1, 0]))

    def test_round_trip_serialization(self) -> None:
        rng = np.random.default_rng(0)
        n = 200
        raw = rng.random(n)
        labels = (raw > 0.5).astype(int)
        cal = IsotonicCalibrator().fit(raw, labels)
        payload = cal.to_dict()
        cal_restored = IsotonicCalibrator.from_dict(payload)
        # Predictions must match within numerical tolerance.
        test_raw = np.linspace(0, 1, 20)
        np.testing.assert_allclose(cal.predict(test_raw), cal_restored.predict(test_raw), atol=1e-9)


# -- stratified_train_cal_split ----------------------------------------------


class TestStratifiedTrainCalSplit:
    def test_split_preserves_proportions(self) -> None:
        labels = np.array([0] * 80 + [1] * 20)
        train_idx, cal_idx = stratified_train_cal_split(labels, cal_size=0.20, seed=0)
        # Cal should have ~16 negatives + ~4 positives = ~20% of each stratum.
        cal_pos = int((labels[cal_idx] == 1).sum())
        cal_neg = int((labels[cal_idx] == 0).sum())
        assert cal_pos >= 1 and cal_pos <= 5
        assert cal_neg >= 14 and cal_neg <= 18

    def test_train_and_cal_partition_all_indices(self) -> None:
        labels = np.array([0] * 80 + [1] * 20)
        train_idx, cal_idx = stratified_train_cal_split(labels, cal_size=0.20, seed=0)
        all_idx = np.sort(np.concatenate([train_idx, cal_idx]))
        np.testing.assert_array_equal(all_idx, np.arange(100))

    def test_seeded_determinism(self) -> None:
        labels = np.array([0] * 80 + [1] * 20)
        a_train, a_cal = stratified_train_cal_split(labels, cal_size=0.20, seed=42)
        b_train, b_cal = stratified_train_cal_split(labels, cal_size=0.20, seed=42)
        np.testing.assert_array_equal(a_train, b_train)
        np.testing.assert_array_equal(a_cal, b_cal)

    def test_no_overlap_between_train_and_cal(self) -> None:
        labels = np.array([0] * 100 + [1] * 50)
        train_idx, cal_idx = stratified_train_cal_split(labels, cal_size=0.20, seed=0)
        assert len(np.intersect1d(train_idx, cal_idx)) == 0

    def test_invalid_cal_size_raises(self) -> None:
        with pytest.raises(ValueError, match="cal_size must be in"):
            stratified_train_cal_split(np.array([0, 1]), cal_size=0.0)
        with pytest.raises(ValueError, match="cal_size must be in"):
            stratified_train_cal_split(np.array([0, 1]), cal_size=1.0)

    def test_empty_labels_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            stratified_train_cal_split(np.array([]), cal_size=0.20)

    def test_minimum_one_per_fold_per_stratum(self) -> None:
        # With only 2 positives, ensure at least 1 in each fold.
        labels = np.array([0] * 80 + [1] * 2)
        train_idx, cal_idx = stratified_train_cal_split(labels, cal_size=0.20, seed=0)
        cal_pos = int((labels[cal_idx] == 1).sum())
        train_pos = int((labels[train_idx] == 1).sum())
        assert cal_pos >= 1
        assert train_pos >= 1
