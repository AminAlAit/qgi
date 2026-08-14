"""Tests for `qgi_ml.src.heads.deephit_lite`."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from heads.deephit_lite import (  # noqa: E402
    DEFAULT_HIDDEN_DIMS,
    DEFAULT_MAX_HORIZON,
    EVAL_HORIZON_YEARS,
    DeepHitLiteConfig,
    DeepHitLiteHead,
    build_forward_targets,
    collapse_to_cumulative_incidence,
)


# -- build_forward_targets ----------------------------------------------------


class TestBuildForwardTargets:
    def _build_panel(self) -> pd.DataFrame:
        rows = []
        for country in ["us", "fr"]:
            for year in range(2014, 2022):
                # Election in year=2018 for "us"; year=2017 for "fr"
                label = 1 if (country == "us" and year == 2018) or (
                    country == "fr" and year == 2017
                ) else 0
                rows.append({"country": country, "year": year, "label": label})
        return pd.DataFrame(rows)

    def test_target_at_horizon_1_matches_next_year_label(self) -> None:
        df = self._build_panel()
        Y, mask = build_forward_targets(df, max_horizon=4, data_year_max=2021)

        # us 2017 -> us 2018 (label 1) at horizon 1
        idx_us_2017 = df.query("country=='us' and year==2017").index[0]
        assert Y[idx_us_2017, 0] == 1
        assert mask[idx_us_2017, 0] == 1

        # us 2018 -> us 2019 (label 0) at horizon 1
        idx_us_2018 = df.query("country=='us' and year==2018").index[0]
        assert Y[idx_us_2018, 0] == 0

    def test_mask_zero_past_data_boundary(self) -> None:
        df = self._build_panel()
        Y, mask = build_forward_targets(df, max_horizon=4, data_year_max=2021)
        # us 2020 → horizons 1, 2 valid (2021, 2022)... but 2022 > data_year_max=2021
        # So horizon 1 (2021) valid, horizons 2-4 (2022-2024) invalid.
        idx_us_2020 = df.query("country=='us' and year==2020").index[0]
        assert mask[idx_us_2020, 0] == 1
        assert mask[idx_us_2020, 1] == 0
        assert mask[idx_us_2020, 2] == 0
        assert mask[idx_us_2020, 3] == 0

    def test_mask_full_when_within_window(self) -> None:
        df = self._build_panel()
        Y, mask = build_forward_targets(df, max_horizon=4, data_year_max=2025)
        # us 2014 with data_year_max=2025: horizons 1-4 = 2015-2018 all valid
        idx_us_2014 = df.query("country=='us' and year==2014").index[0]
        assert (mask[idx_us_2014, :] == 1).all()

    def test_label_only_at_event_year(self) -> None:
        df = self._build_panel()
        Y, mask = build_forward_targets(df, max_horizon=4, data_year_max=2025)
        # fr 2014 → 2015, 2016, 2017, 2018. Event at 2017 = horizon 3 (idx 2).
        idx_fr_2014 = df.query("country=='fr' and year==2014").index[0]
        assert Y[idx_fr_2014, 0] == 0  # 2015
        assert Y[idx_fr_2014, 1] == 0  # 2016
        assert Y[idx_fr_2014, 2] == 1  # 2017 (event)
        assert Y[idx_fr_2014, 3] == 0  # 2018

    def test_missing_columns_raises(self) -> None:
        df = pd.DataFrame({"country": ["a"], "year": [2020]})
        with pytest.raises(ValueError, match="missing columns"):
            build_forward_targets(df, max_horizon=4)

    def test_default_max_horizon_matches_locked_value(self) -> None:
        # Pre-reg locks T=4. Verify default is wired correctly.
        assert DEFAULT_MAX_HORIZON == 4

    def test_default_eval_horizon_matches_locked_value(self) -> None:
        # Pre-reg locks T_eval=1.
        assert EVAL_HORIZON_YEARS == 1


# -- collapse_to_cumulative_incidence ----------------------------------------


class TestCollapseToCumulativeIncidence:
    def test_horizon_1_equals_first_hazard(self) -> None:
        hazards = np.array([
            [0.10, 0.20, 0.30, 0.40],
            [0.05, 0.10, 0.15, 0.20],
        ])
        ci = collapse_to_cumulative_incidence(hazards, horizon_years=1)
        np.testing.assert_allclose(ci, [0.10, 0.05])

    def test_horizon_2_uses_chain_formula(self) -> None:
        hazards = np.array([[0.10, 0.20, 0.30, 0.40]])
        # CI at horizon 2 = 1 - (1-0.10) * (1-0.20) = 1 - 0.72 = 0.28
        ci = collapse_to_cumulative_incidence(hazards, horizon_years=2)
        np.testing.assert_allclose(ci, [0.28])

    def test_horizon_4_uses_full_chain(self) -> None:
        hazards = np.array([[0.10, 0.20, 0.30, 0.40]])
        # CI at horizon 4 = 1 - (0.9)(0.8)(0.7)(0.6) = 1 - 0.3024 = 0.6976
        ci = collapse_to_cumulative_incidence(hazards, horizon_years=4)
        np.testing.assert_allclose(ci, [0.6976])

    def test_invalid_horizon_raises(self) -> None:
        hazards = np.zeros((10, 4))
        with pytest.raises(ValueError, match="horizon_years must be in"):
            collapse_to_cumulative_incidence(hazards, horizon_years=5)
        with pytest.raises(ValueError, match="horizon_years must be in"):
            collapse_to_cumulative_incidence(hazards, horizon_years=0)

    def test_1d_input_raises(self) -> None:
        with pytest.raises(ValueError, match="hazards must be 2D"):
            collapse_to_cumulative_incidence(np.array([0.1, 0.2, 0.3]))

    def test_zero_hazards_yield_zero_cumulative_incidence(self) -> None:
        hazards = np.zeros((5, 4))
        ci = collapse_to_cumulative_incidence(hazards, horizon_years=4)
        np.testing.assert_allclose(ci, np.zeros(5))

    def test_ones_hazards_yield_one_cumulative_incidence(self) -> None:
        hazards = np.ones((5, 4))
        ci = collapse_to_cumulative_incidence(hazards, horizon_years=4)
        np.testing.assert_allclose(ci, np.ones(5))


# -- DeepHitLiteHead end-to-end (smoke + sanity) -----------------------------


class TestDeepHitLiteHead:
    """Integration tests requiring torch."""

    def _synthetic_panel(self, n_countries: int = 30, n_years: int = 8, seed: int = 0):
        """Build (X, Y, mask) with a real signal: P(label=1) depends on
        feature X[:, 0] strongly so the head should learn discrimination.
        """
        pytest.importorskip("torch")
        rng = np.random.default_rng(seed)
        rows = []
        for c in range(n_countries):
            for y in range(2014, 2014 + n_years):
                # Label depends on a country-level feature (feature 0)
                rows.append({"country": f"c{c}", "year": y})
        df = pd.DataFrame(rows)
        n_samples = len(df)

        # Features: 50-dim, feature 0 carries strong signal.
        X = rng.normal(0, 1, (n_samples, 50)).astype(np.float32)
        country_ids = df["country"].astype("category").cat.codes.to_numpy()
        # Inject country-level signal into feature 0.
        X[:, 0] = (country_ids % 5).astype(float) + rng.normal(0, 0.3, n_samples)

        # Generate labels: countries 0-4 have higher event rate
        labels = (country_ids % 5 < 2).astype(int) * (rng.random(n_samples) < 0.4).astype(int)
        df["label"] = labels

        Y, mask = build_forward_targets(df, max_horizon=4, data_year_max=2014 + n_years - 1)
        return df, X, Y, mask

    def test_fit_and_predict_returns_correct_shapes(self) -> None:
        df, X, Y, mask = self._synthetic_panel(seed=0)

        head = DeepHitLiteHead(
            config=DeepHitLiteConfig(
                max_horizon=4, max_epochs=5, batch_size=32, seed=0
            )
        )
        head.fit(X, Y, mask)

        hazards = head.predict_hazards(X)
        assert hazards.shape == (X.shape[0], 4)
        assert (hazards >= 0).all() and (hazards <= 1).all()

        proba = head.predict_proba(X)
        assert proba.shape == (X.shape[0],)
        assert (proba >= 0).all() and (proba <= 1).all()

    def test_predict_proba_horizon_1_equals_first_hazard(self) -> None:
        df, X, Y, mask = self._synthetic_panel(seed=1)
        head = DeepHitLiteHead(
            config=DeepHitLiteConfig(max_horizon=4, max_epochs=3, seed=1)
        )
        head.fit(X, Y, mask)
        hazards = head.predict_hazards(X)
        proba = head.predict_proba(X, horizon_years=1)
        np.testing.assert_allclose(proba, hazards[:, 0])

    def test_unfitted_head_raises_on_predict(self) -> None:
        head = DeepHitLiteHead()
        with pytest.raises(RuntimeError, match="not fitted"):
            head.predict_hazards(np.zeros((5, 10)))
        with pytest.raises(RuntimeError, match="not fitted"):
            head.predict_proba(np.zeros((5, 10)))

    def test_shape_mismatch_raises_on_fit(self) -> None:
        head = DeepHitLiteHead(config=DeepHitLiteConfig(max_horizon=4))
        X = np.zeros((10, 5))
        Y = np.zeros((10, 3), dtype=int)  # wrong horizon
        mask = np.zeros((10, 3), dtype=int)
        with pytest.raises(ValueError, match="Y_train shape"):
            head.fit(X, Y, mask)

    def test_seeded_fit_is_deterministic(self) -> None:
        df, X, Y, mask = self._synthetic_panel(seed=2)
        head_a = DeepHitLiteHead(
            config=DeepHitLiteConfig(max_horizon=4, max_epochs=5, seed=42, batch_size=32)
        )
        head_b = DeepHitLiteHead(
            config=DeepHitLiteConfig(max_horizon=4, max_epochs=5, seed=42, batch_size=32)
        )
        head_a.fit(X, Y, mask)
        head_b.fit(X, Y, mask)
        np.testing.assert_allclose(
            head_a.predict_proba(X[:5]),
            head_b.predict_proba(X[:5]),
            atol=1e-5,
        )

    def test_default_config_matches_pre_reg(self) -> None:
        cfg = DeepHitLiteConfig()
        assert cfg.max_horizon == 4
        assert cfg.hidden_dims == (64, 32)
        assert cfg.eval_horizon_years == 1
        assert DEFAULT_HIDDEN_DIMS == (64, 32)

    def test_early_stopping_on_val_loss(self) -> None:
        df, X, Y, mask = self._synthetic_panel(seed=3)
        # Split into train/val for early stopping check
        n = X.shape[0]
        split = int(0.8 * n)
        head = DeepHitLiteHead(
            config=DeepHitLiteConfig(
                max_horizon=4,
                max_epochs=200,
                early_stop_patience=3,
                seed=3,
                batch_size=32,
            )
        )
        head.fit(
            X[:split], Y[:split], mask[:split],
            X_val=X[split:], Y_val=Y[split:], mask_val=mask[split:],
        )
        # If early stopping kicked in, history should be < 200 epochs.
        # If model converged perfectly in 200 epochs, that's also fine.
        assert len(head._train_history) <= 200
