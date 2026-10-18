# 2. Cross-Border Contagion & Bilateral Diffusion Topology

## 2.1 Pairwise Lead-Lag Cross-Correlation Tensor

Across $C = 196$ sovereign polities and $K > 100$ standardized indicators, the QGI vector engine (`pipeline/batch/` and `ml/src/`) evaluates rolling lead-lag cross-correlations across lag offsets $\ell \in [-\ell_{\max}, +\ell_{\max}]$:

$$
\rho_{i,j}^{(k,m)}(\ell; t) = \text{Corr}\!\left(\Delta z_{i,k}(s),\; \Delta z_{j,m}(s + \ell)\right)_{s \in [t - W, t]}
$$

## 2.2 Structural Twins & Spillover Transmission

Country-pair similarity scores combine:
1. **Institutional & Macroeconomic Regime Proximity:** Mahalanobis distance across stationary first-differenced $I(1)$ and demeaned $I(0)$ indicator panels (`ml/scripts/run_i5_substrate_audit.py`).
2. **Trade & Sanctions Contagion (`SSTM` & `CMSS`):** Bilateral trade-share and strategic corridor exposure weights propagating localized shocks across connected trading partners.
