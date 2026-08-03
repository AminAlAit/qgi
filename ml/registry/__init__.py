"""QGI Flagship Endogenous Model Registry & Trend Catalog (Decisions D30 & D33).

Strictly enforces the Endogenous-Only Modeling Constraint:
- Exogenous shock models (`natural_disaster`, `epidemic_and_pandemic`) are
  permanently deactivated (`is_active=False`) and excluded from the active
  walking fleet and trajectory catalog.
- Registers the 12 Flagship Endogenous Models across the 5 quantitative families.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class FlagshipModelSpec:
    code: str
    recipe_id: str
    display_name: str
    family: str
    horizon_months: int
    primary_metric: str
    is_active: bool = True
    is_endogenous: bool = True


FLAGSHIP_ENDOGENOUS_MODELS: Dict[str, FlagshipModelSpec] = {
    "SCVI": FlagshipModelSpec(
        code="SCVI",
        recipe_id="sovereign_conflict_velocity",
        display_name="Sovereign Conflict Velocity Index",
        family="autoregressive_regime",
        horizon_months=12,
        primary_metric="Brier / ROC-AUC",
    ),
    "SCDP": FlagshipModelSpec(
        code="SCDP",
        recipe_id="coup_and_destabilization",
        display_name="Structural Coup & Destabilization Probability",
        family="institutional_fragility",
        horizon_months=24,
        primary_metric="PR-AUC / Log-Loss",
    ),
    "SDCP": FlagshipModelSpec(
        code="SDCP",
        recipe_id="sovereign_debt_and_currency_pressure",
        display_name="Sovereign Debt & Currency Pressure",
        family="state_space_trajectories",
        horizon_months=18,
        primary_metric="RMSE / CRPS",
    ),
    "CMSS": FlagshipModelSpec(
        code="CMSS",
        recipe_id="chokepoint_and_maritime_supply_stress",
        display_name="Chokepoint & Maritime Supply Stress",
        family="conflict_diffusion_graph",
        horizon_months=6,
        primary_metric="MAE / Hit-Rate@K",
    ),
    "DEAI": FlagshipModelSpec(
        code="DEAI",
        recipe_id="diplomatic_escalation_and_alignment",
        display_name="Diplomatic Escalation & Alignment Index",
        family="conflict_diffusion_graph",
        horizon_months=12,
        primary_metric="Spearman Rho",
    ),
    "ETGR": FlagshipModelSpec(
        code="ETGR",
        recipe_id="energy_policy",
        display_name="Energy Transition & Grid Resilience",
        family="state_space_trajectories",
        horizon_months=36,
        primary_metric="Out-of-Sample R2",
    ),
    "SSTM": FlagshipModelSpec(
        code="SSTM",
        recipe_id="sanctions_spillover_and_trade_contagion",
        display_name="Sanctions Spillover & Trade Contagion",
        family="conflict_diffusion_graph",
        horizon_months=12,
        primary_metric="CRPS / Calibration",
    ),
    "CTDI": FlagshipModelSpec(
        code="CTDI",
        recipe_id="cyber_and_telecom_disruption",
        display_name="Cyber & Telecom Disruption Index",
        family="shock_decay",
        horizon_months=6,
        primary_metric="Brier Score",
    ),
    "CWKC": FlagshipModelSpec(
        code="CWKC",
        recipe_id="civil_war_and_insurgency",
        display_name="Civil War & Kinetic Conflict",
        family="autoregressive_regime",
        horizon_months=12,
        primary_metric="ROC-AUC / Brier",
    ),
    "DIRSM": FlagshipModelSpec(
        code="DIRSM",
        recipe_id="democratic_backsliding_and_institutional_decay",
        display_name="Democratic Backsliding & Institutional Decay",
        family="institutional_fragility",
        horizon_months=24,
        primary_metric="Concordance Index",
    ),
    "FSSI": FlagshipModelSpec(
        code="FSSI",
        recipe_id="food_and_strategic_commodity_stress",
        display_name="Food & Strategic Commodity Stress",
        family="state_space_trajectories",
        horizon_months=12,
        primary_metric="RMSE / Directional",
    ),
    "MACM": FlagshipModelSpec(
        code="MACM",
        recipe_id="military_expenditure_and_arms_trajectory",
        display_name="Military Expenditure & Arms Trajectory",
        family="autoregressive_regime",
        horizon_months=24,
        primary_metric="MASE / Coverage@90",
    ),
}

DEACTIVATED_EXOGENOUS_MODELS: Dict[str, FlagshipModelSpec] = {
    "natural_disaster": FlagshipModelSpec(
        code="EXOG_ND",
        recipe_id="natural_disaster",
        display_name="Natural Disaster Shock (Deactivated per D30/D33)",
        family="shock_decay",
        horizon_months=12,
        primary_metric="N/A",
        is_active=False,
        is_endogenous=False,
    ),
    "epidemic_and_pandemic": FlagshipModelSpec(
        code="EXOG_EP",
        recipe_id="epidemic_and_pandemic",
        display_name="Epidemic & Pandemic Shock (Deactivated per D30/D33)",
        family="shock_decay",
        horizon_months=12,
        primary_metric="N/A",
        is_active=False,
        is_endogenous=False,
    ),
}

FORBIDDEN_EXOGENOUS_RECIPES = frozenset({"natural_disaster", "epidemic_and_pandemic"})


def get_flagship_models() -> Dict[str, FlagshipModelSpec]:
    """Return the 12 active flagship endogenous models."""
    return dict(FLAGSHIP_ENDOGENOUS_MODELS)


def is_recipe_endogenous(recipe_id: str) -> bool:
    """Return True iff the recipe is permitted under Decisions D30 & D33."""
    return recipe_id not in FORBIDDEN_EXOGENOUS_RECIPES


# Re-export indicator enrichment candidate registry helpers so legacy `import registry` callers work
from scripts.enrichment.registry import *  # noqa: F401, F403

