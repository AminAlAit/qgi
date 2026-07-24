"""Isotonic calibration for the F5=3 DeepHit-lite head's collapsed
`predicted_probability` output.

Pre-reg `§3` LOCKED:
- Method: scikit-learn `IsotonicRegression(out_of_bounds='clip')`
- Input: collapsed cumulative incidence at locked horizon T_eval=1y
- Fit on a held-out cal-fold from the training window (NOT 2022-2025);
  fold is constructed by stratified 80/20 split of 2014-2021 by recipe
  label.

Pure functions; tests in `tests/test_walk_calibrate.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class IsotonicCalibrator:
    """Thin wrapper around `sklearn.isotonic.IsotonicRegression`.

    Provides a JSON-serializable `to_dict` / `from_dict` so the walk
    runner can persist the calibrator alongside model artifacts and the
    pre-reg replication signature.
    """

    out_of_bounds: str = "clip"
    _calibrator: Any = field(init=False, default=None)
    _is_fitted: bool = field(init=False, default=False)

    def fit(self, raw_probs: np.ndarray, labels: np.ndarray) -> "IsotonicCalibrator":
        from sklearn.isotonic import IsotonicRegression  # noqa: PLC0415

        raw_probs = np.asarray(raw_probs, dtype=float)
        labels = np.asarray(labels, dtype=int)
        if raw_probs.shape != labels.shape:
            msg = f"shape mismatch: {raw_probs.shape} vs {labels.shape}"
            raise ValueError(msg)
        if raw_probs.size == 0:
            msg = "cannot fit IsotonicCalibrator on empty input"
            raise ValueError(msg)
        self._calibrator = IsotonicRegression(out_of_bounds=self.out_of_bounds)
        self._calibrator.fit(raw_probs, labels)
        self._is_fitted = True
        return self

    def predict(self, raw_probs: np.ndarray) -> np.ndarray:
        if not self._is_fitted:
            msg = "IsotonicCalibrator not fitted"
            raise RuntimeError(msg)
        raw_probs = np.asarray(raw_probs, dtype=float)
        return np.asarray(self._calibrator.predict(raw_probs), dtype=float)

    def to_dict(self) -> dict[str, Any]:
        if not self._is_fitted:
            msg = "cannot serialize unfitted IsotonicCalibrator"
            raise RuntimeError(msg)
        # sklearn's IsotonicRegression stores X_thresholds_ + y_thresholds_
        # which are sufficient to reconstruct the step function.
        return {
            "method": "sklearn.isotonic.IsotonicRegression",
            "out_of_bounds": self.out_of_bounds,
            "x_thresholds": self._calibrator.X_thresholds_.tolist(),
            "y_thresholds": self._calibrator.y_thresholds_.tolist(),
            "x_min": float(self._calibrator.X_min_),
            "x_max": float(self._calibrator.X_max_),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "IsotonicCalibrator":
        from sklearn.isotonic import IsotonicRegression  # noqa: PLC0415

        cal = cls(out_of_bounds=payload.get("out_of_bounds", "clip"))
        x_thr = np.asarray(payload["x_thresholds"], dtype=float)
        y_thr = np.asarray(payload["y_thresholds"], dtype=float)
        # Refit on the saved threshold pairs — this reconstructs the
        # underlying step function exactly because (x_thresholds,
        # y_thresholds) IS a valid (X, y) for IsotonicRegression and
        # the algorithm is deterministic on monotone inputs. This
        # produces a fully-fitted IsotonicRegression with f_ properly
        # built (vs setting f_=None which leaves a non-callable
        # interpolator that crashes on first predict).
        sk = IsotonicRegression(out_of_bounds=cal.out_of_bounds)
        sk.fit(x_thr, y_thr)
        # Override the X_min_ / X_max_ to the originally-fitted values
        # (refit may shrink them since fitting on the threshold pairs
        # only sees those points; the original training set's min/max
        # may have extended further with `clip` semantics).
        sk.X_min_ = float(payload["x_min"])
        sk.X_max_ = float(payload["x_max"])
        cal._calibrator = sk
        cal._is_fitted = True
        return cal


def stratified_train_cal_split(
    labels: np.ndarray,
    *,
    cal_size: float = 0.20,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """Stratified split of indices by binary label.

    Per pre-reg §3 (LOCKED): 80/20 by recipe label. 80% trains the head;
    20% fits the isotonic calibrator. Test window 2022-2025 is reserved
    for F-rule evaluation only and never touches the calibrator.

    Returns (train_idx, cal_idx) both 1-D int arrays into the input
    `labels` array. Each index is in exactly one of the two folds.
    """
    if not 0 < cal_size < 1:
        msg = f"cal_size must be in (0, 1), got {cal_size}"
        raise ValueError(msg)
    labels = np.asarray(labels, dtype=int)
    n = labels.size
    if n == 0:
        msg = "cannot split empty labels array"
        raise ValueError(msg)

    rng = np.random.default_rng(seed)
    pos_idx = np.where(labels == 1)[0]
    neg_idx = np.where(labels == 0)[0]
    train_parts: list[np.ndarray] = []
    cal_parts: list[np.ndarray] = []

    for stratum_idx in (pos_idx, neg_idx):
        if stratum_idx.size == 0:
            continue
        shuffled = rng.permutation(stratum_idx)
        n_cal = int(np.ceil(stratum_idx.size * cal_size))
        # Ensure at least 1 in each fold per stratum if possible.
        n_cal = max(1, min(n_cal, stratum_idx.size - 1)) if stratum_idx.size >= 2 else 0
        cal_parts.append(shuffled[:n_cal])
        train_parts.append(shuffled[n_cal:])

    train_idx = np.concatenate(train_parts) if train_parts else np.array([], dtype=int)
    cal_idx = np.concatenate(cal_parts) if cal_parts else np.array([], dtype=int)
    train_idx.sort()
    cal_idx.sort()
    return train_idx, cal_idx
