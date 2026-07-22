"""QGI Trajectory Engine & Endogenous Trend Catalog (Decisions D30 & D33).

Provides `get_active_trend_catalog()` enforcing the strict endogenous-only
modeling rule:
1. Exogenous shock models (`natural_disaster` and `epidemic_and_pandemic`) are
   permanently deactivated and excluded from the active catalog.
2. Total active trend recipes are capped at <= 69 endogenous categories.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

FORBIDDEN_EXOGENOUS_MODELS = frozenset({"natural_disaster", "epidemic_and_pandemic"})
MAX_ACTIVE_TREND_RECIPES = 69

_DEFAULT_ENDOGENOUS_RECIPES: tuple[str, ...] = (
    "civil_war_and_insurgency",
    "terrorist_attack",
    "energy_policy",
    "peacekeeping_and_peace_process",
    "foreign_intervention",
    "humanitarian_crisis",
    "government_formation",
    "human_rights_violation",
    "economic_recession",
    "sovereign_debt_crisis",
    "currency_crisis",
    "banking_crisis",
    "hyperinflation",
    "trade_dispute_and_sanctions",
    "supply_chain_disruption",
    "maritime_chokepoint_disruption",
    "cyber_attack_on_critical_infrastructure",
    "coup_d_etat",
    "constitutional_crisis",
    "electoral_violence_and_dispute",
    "mass_protest_and_civil_unrest",
    "general_strike",
    "state_of_emergency_and_martial_law",
    "political_assassination",
    "judicial_independence_erosion",
    "media_censorship_and_shutdown",
    "border_skirmish_and_militarized_dispute",
    "military_mobilization_and_buildup",
    "arms_transfer_and_proliferation",
    "defense_pact_and_alliance_shift",
    "diplomatic_expulsion_and_severing",
    "treaty_withdrawal_and_abrogation",
    "refugee_and_forced_displacement_surge",
    "food_insecurity_and_price_shock",
    "water_scarcity_and_transboundary_dispute",
    "critical_minerals_export_restriction",
)


def _load_taxonomy_categories() -> list[str]:
    """Load event categories from data-tools reference mapping if available."""
    repo_root = Path(__file__).resolve().parents[3]
    for subdir in ("data-tools", "qgi-data"):
        mapping_path = repo_root / subdir / "reference" / "event-category-l1-mapping.json"
        if mapping_path.exists():
            try:
                payload = json.loads(mapping_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    cats = payload.get("category_to_l1") or payload.get("categories") or payload
                    if isinstance(cats, dict):
                        return [str(k) for k in cats.keys() if not str(k).startswith("_")]
            except Exception:
                pass
    return list(_DEFAULT_ENDOGENOUS_RECIPES)


def get_active_trend_catalog() -> Dict[str, Dict[str, Any]]:
    """Return the active endogenous trend catalog (<= 69 recipes).

    Explicitly filters out `natural_disaster` and `epidemic_and_pandemic` per
    Decisions D30 and D33.
    """
    raw_categories = _load_taxonomy_categories()
    catalog: Dict[str, Dict[str, Any]] = {}

    for category in raw_categories:
        if category in FORBIDDEN_EXOGENOUS_MODELS:
            continue
        if len(catalog) >= MAX_ACTIVE_TREND_RECIPES:
            break
        catalog[category] = {
            "recipe_id": category,
            "is_active": True,
            "is_endogenous": True,
            "exogenous_excluded": True,
        }

    # Guarantee flagship endogenous recipes are present and within the 69 cap
    for flagship_recipe in _DEFAULT_ENDOGENOUS_RECIPES:
        if flagship_recipe in FORBIDDEN_EXOGENOUS_MODELS:
            continue
        if flagship_recipe not in catalog and len(catalog) < MAX_ACTIVE_TREND_RECIPES:
            catalog[flagship_recipe] = {
                "recipe_id": flagship_recipe,
                "is_active": True,
                "is_endogenous": True,
                "exogenous_excluded": True,
            }

    return catalog
