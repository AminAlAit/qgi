# 3. Out-of-Sample Validation, Calibration & Falsification Benchmarks

## 3.1 Leave-One-Country-Out (LOCO) & Rolling Temporal Validation

Every QGI model family is evaluated under two complementary out-of-sample protocols (`ml/backtesting/` and `ml/scripts/validate_ml_model.py`):
- **Strict Temporal Walk-Forward:** Models trained on observations up to year $t$ are evaluated strictly on $[t + 1, t + h]$ with zero post-event covariate revision leakage.
- **Leave-One-Country-Out (LOCO) Cross-Validation:** Prevents high-event-count polities from dominating cross-national decision boundaries (`ml/config/hybrid_architecture_dispatch.json`).

## 3.2 Calibration & Proper Scoring Rules

Raw classifier logits and hazard outputs are calibrated via three-parameter Beta calibration (`ml/src/beta_calibration.py`) and audited against:
- **Brier Score:** $\text{BS} = \frac{1}{N}\sum_{i=1}^N (\hat{p}_i - y_i)^2$ compared directly against the naive empirical persistence baseline (`ml/backtesting/baselines.py`).
- **Expected Calibration Error (ECE):** Stratified reliability bin gap analysis (`ml/src/cohort_calibration.py`).
- **Pre-Registered Falsification Battery:** 4-arm ablation (`A`, `B`, `C`, `D`) and hierarchical Bayesian partial-pooling verification (`ml/scripts/validate_weight_matrix.py`, `ml/scripts/validate_weight_matrix_bayes.py`).
