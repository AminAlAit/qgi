# 1. Endogenous Structural Dynamics & State-Space Formulations (Decisions D13, D30, D33)

## 1.1 The Endogenous-Only Modeling Boundary

Geopolitical trajectory forecasting frequently suffers from confounding between **endogenous structural decay** (e.g., institutional erosion, fiscal exhaustion, military expenditure acceleration, bilateral trade decoupling) and **exogenous stochastic shocks** (`natural_disaster` and `epidemic_and_pandemic`).

Under **Decisions D30 and D33**, the QGI Trajectory Engine enforces a strict architectural separation:
1. All active predictive models in `ml/registry/` operate exclusively on **endogenous socio-political, macroeconomic, institutional, and military indicators**.
2. Exogenous shock recipes (`natural_disaster`, `epidemic_and_pandemic`) are permanently deactivated (`is_active = False`) and excluded from the active trend catalog (`len(get_active_trend_catalog()) <= 69`).

---

## 1.2 State-Space & Pre-Event Trajectory Alignment

For each country $c \in \{1, \dots, C\}$, indicator $k \in \{1, \dots, K\}$, and pre-event horizon $T_r$, raw indicator levels $x_{c,k}(t)$ are standardized strictly against a trailing pre-window baseline $[t_0 - T_r - W, t_0 - T_r)$ to prevent lookahead leakage:

$$
z_{c,k}(\tau) = \frac{x_{c,k}(t_0 - T_r + \tau) - \hat{\mu}_{c,k}^{\text{pre}}}{\hat{\sigma}_{c,k}^{\text{pre}}}, \quad \tau \in \{0, \dots, T_r - 1\}
$$

Functional Principal Component Analysis (FPCA) in the Sobolev $H^2$ norm and hierarchical Bayesian Gaussian Process fallbacks (`ml/src/shape_prototype_fit_utils.py`) extract the canonical pre-escalation trajectory signature $\boldsymbol{\mu}_r^{(k)}$ and posterior covariance $\boldsymbol{\Sigma}_r^{(k)}$.
