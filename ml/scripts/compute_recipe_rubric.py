#!/usr/bin/env python3
"""
Compute the ML-Track Recipe Prioritization Rubric
==================================================

Implements the deterministic recipe-ranking formula from the Kwame + Ji-Hoon
mini-consult (2026-05-04), spec at:
  docs/specs/internal/ops/ml-track/05-recipe-prioritization-rubric.md

Formula (per Layer-3 event category r):

    S(r) = 0.35 * A(r) + 0.25 * B(r) + 0.25 * C(r) + 0.15 * D(r)

with HARD GATE: if n_positive_verified(r) < 8 across the 2014-2025 training
window, A(r) = 0 and the recipe is excluded (S=0, rank=None).

Verified-only n_positive (per Kwame's spec language and founder decision
2026-05-04): the gate counts unique (country, year) pairs whose curated
events carry verified=True. Unverified events are reported as
n_positive_total for transparency but do NOT enter the gate or Factor A.

Factor definitions:
    A — Ground-Truth Density. Unique VERIFIED (country, year) pairs per
        category in [2014, 2025] / max across all 71 categories.
    B — Label Clarity. 1.0 (external dataset binary onset), 0.5 (QGI-internal),
        0.0 (graded/ambiguous). Manual lookup per category, sourced from the
        canonical event-source manifest.
    C — Directional Indicator Coverage. Until cascade-Opus's Phase 5 v0.1a
        annotation sprint produces direction-of-effect annotations, this script
        falls back to the SECTOR PROXY: count indicators whose sector (per
        qgi-data/reference/indicator-sectors.json -- note: the Stage 0 spec
        cites docs/specs/methodology/ but the canonical file lives in qgi-data/)
        is in the relevance map for this recipe / 10, capped at 1.0.
    D — Cross-Recipe Pooling Utility. Iterative: compute S' = 0.35A + 0.25B +
        0.25C, identify top-20 by S', then for each r count other r' in top-20
        sharing >=3 indicators in the same sector / 5, capped at 1.0.

Survival-eligibility flag (Ji-Hoon's F2-F4) is computed independently of S(r):
    F2  Event-timing clarity      0-3
    F3  Right-censoring tractability  0-2
    F4  Label dating precision    0-2
    survival_eligible := (F2 + F3 + F4) >= 5

F5 (architecture head fit) is the tiebreaker / head-class hint:
    3  survival head warranted  (survival_eligible AND n_positive >= 20)
    2  asymmetric-loss GBM      (rare class, n_positive in [8, 20))
    1  standard GBM             (n_positive >= 20 but not survival-eligible)
    0  excluded by hard gate

Outputs JSON to qgi-data/reference/ml-recipe-ranking-2026-05.json (or path
supplied via --output).

Usage:
    python qgi-ml/scripts/compute_recipe_rubric.py
    python qgi-ml/scripts/compute_recipe_rubric.py --output /tmp/test.json
    python qgi-ml/scripts/compute_recipe_rubric.py --print-summary
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CURATED_DIR = REPO_ROOT / "qgi-data" / "events" / "curated"
DEFAULT_CATEGORY_MAPPING = REPO_ROOT / "qgi-data" / "events" / "taxonomy_hierarchy.json"
DEFAULT_INDICATOR_SECTORS = REPO_ROOT / "qgi-data" / "reference" / "indicator-sectors.json"
DEFAULT_OUTPUT = REPO_ROOT / "qgi-data" / "reference" / "ml-recipe-ranking-2026-05.json"

TRAINING_WINDOW = (2014, 2025)
HARD_GATE_MIN_N_POSITIVE = 8
WEIGHTS = {"A": 0.35, "B": 0.25, "C": 0.25, "D": 0.15}
C_DIVISOR = 10
D_TOP_N = 20
D_DIVISOR = 5
D_MIN_SHARED_INDICATORS = 3


# Label clarity per category (Factor B).
# 1.0 = binary event with external-source dataset that publishes onset year.
# 0.5 = curated by QGI agents, no external canonical dataset for this concept.
# 0.0 = gradient definition; binary onset requires discretionary cutoffs.
#
# Source provenance is the *external dataset(s)* whose existence justifies the
# 1.0 score. For 0.5 categories, we list the curation source. The pre-registration
# document (Stage 0 deliverable) freezes this table for the duration of the
# mandate; later updates require a Majles convening.
LABEL_CLARITY_B: dict[str, tuple[float, list[str]]] = {
    # A — Political Power & Regime
    "elections_and_voting": (1.0, ["NELDA", "IFES", "V-Dem v2xel_frefair"]),
    "government_formation": (0.5, ["QGI internal curation"]),
    "constitutional_change": (1.0, ["CCP (Comparative Constitutions Project)"]),
    "decentralization_and_federalism": (0.5, ["QGI internal curation"]),
    "democratic_transition": (1.0, ["V-Dem v2x_regime category transitions", "Polity"]),
    "executive_power_consolidation": (0.5, ["QGI internal curation"]),
    "military_coup": (1.0, ["Powell-Thyne coup database", "Marshall CSP"]),
    "transitional_justice": (0.5, ["QGI internal curation"]),
    "peacekeeping_and_peace_process": (1.0, ["UCDP PA-X peace agreement database"]),
    # B — Conflict & Political Violence
    "interstate_war": (1.0, ["UCDP", "COW"]),
    "civil_war_and_insurgency": (1.0, ["UCDP intrastate conflict onset"]),
    "terrorist_attack": (1.0, ["GTD", "ACLED"]),
    "foreign_intervention": (1.0, ["COW intervention dataset", "UCDP"]),
    "ethnic_and_communal_conflict": (1.0, ["UCDP non-state", "ACLED"]),
    "political_violence": (1.0, ["UCDP one-sided violence", "ACLED"]),
    # C — State Authority & Governance
    "political_repression": (0.5, ["QGI internal curation"]),
    "political_corruption": (0.5, ["QGI internal curation; TI CPI is gradient"]),
    "human_rights_violation": (0.5, ["QGI internal curation; CIRI/HRMI gradients"]),
    "human_rights_reform": (0.5, ["QGI internal curation"]),
    "military_policy_and_reform": (0.5, ["QGI internal curation"]),
    # D — Economic & Financial Stress
    "currency_crisis": (1.0, ["Laeven-Valencia"]),
    "banking_and_financial_crisis": (1.0, ["Laeven-Valencia"]),
    "economic_recession": (1.0, ["IMF WEO NGDP_RPCH contraction"]),
    "fiscal_policy_change": (0.5, ["QGI internal curation"]),
    "monetary_policy_change": (0.5, ["QGI internal curation"]),
    "economic_liberalization": (0.5, ["QGI internal curation"]),
    "economic_nationalization": (0.5, ["QGI internal curation"]),
    "economic_recovery": (0.5, ["QGI internal curation"]),
    "economic_growth_milestone": (0.5, ["QGI internal curation"]),
    "trade_agreement": (1.0, ["WTO RTA database"]),
    "trade_dispute": (1.0, ["WTO disputes database"]),
    "foreign_direct_investment": (0.5, ["UNCTAD flow data; no event canon"]),
    "industrial_policy": (0.5, ["QGI internal curation"]),
    "sanctions_and_arms_embargo": (1.0, ["GSDB Global Sanctions Database", "SIPRI arms embargo"]),
    "foreign_aid_and_development": (0.5, ["OECD DAC flows; no event canon"]),
    # E — Social Mobilization & Civil Society
    "mass_protest": (1.0, ["ACLED protests", "Mass Mobilization Database"]),
    "labor_action": (0.5, ["QGI internal curation; ILO TIPS spotty"]),
    "social_policy_reform": (0.5, ["QGI internal curation"]),
    "public_health_reform": (0.5, ["QGI internal curation"]),
    "poverty_and_inequality_crisis": (0.0, ["Gradient definition; no canonical onset"]),
    "religious_and_social_movement": (0.5, ["QGI internal curation"]),
    "migration_and_refugees": (1.0, ["UNHCR refugee statistics"]),
    # F — Diplomatic & Geopolitical Relations
    "bilateral_treaty": (0.5, ["QGI internal curation; news-derived"]),
    "multilateral_agreement": (1.0, ["UN treaty database"]),
    "diplomatic_rupture": (0.5, ["QGI internal curation; news-derived"]),
    "territorial_disputes": (1.0, ["ICOW Territorial Claims"]),
    "regional_integration": (1.0, ["EU/AU/ASEAN accession lists"]),
    # G — Humanitarian & Environmental Crisis
    "earthquake": (1.0, ["EM-DAT", "USGS"]),
    "flood_and_cyclone": (1.0, ["EM-DAT", "IBTrACS"]),
    "volcanic_eruption": (1.0, ["EM-DAT", "Smithsonian GVP"]),
    "natural_disaster": (1.0, ["EM-DAT (catch-all)"]),
    "drought_and_famine": (1.0, ["FEWS-NET IPC", "EM-DAT"]),
    "epidemic_and_pandemic": (1.0, ["WHO", "EM-DAT"]),
    "humanitarian_crisis": (1.0, ["UNOCHA", "IOM"]),
    "water_crisis": (0.5, ["QGI internal curation"]),
    # H — Structural & Development Context
    "energy_policy": (0.5, ["QGI internal curation"]),
    "oil_and_gas": (0.5, ["QGI internal curation"]),
    "renewable_energy": (0.5, ["QGI internal curation"]),
    "environmental_policy": (0.5, ["QGI internal curation"]),
    "climate_agreement": (1.0, ["UNFCCC NDC database"]),
    "resource_conflict": (0.5, ["QGI internal curation; partial UCDP overlap"]),
    "infrastructure_project": (0.5, ["QGI internal curation"]),
    "urban_development": (0.5, ["QGI internal curation"]),
    "education_reform": (0.5, ["QGI internal curation"]),
    "education_and_research": (0.5, ["QGI internal curation"]),
    "digital_policy": (0.5, ["QGI internal curation"]),
    "technology_breakthrough": (0.5, ["QGI internal curation"]),
    "cyberattack": (0.5, ["QGI internal curation; CSIS Significant Cyber Incidents partial"]),
    "cultural_and_heritage": (0.5, ["QGI internal curation"]),
    "sport_and_international_event": (0.5, ["QGI internal curation"]),
    "agricultural_policy": (0.5, ["QGI internal curation"]),
}


# Sector relevance per category (Factor C proxy).
# Sectors must match keys in qgi-data/reference/indicator-sectors.json:
# CONFLICT, DISPLACE, GOV_INST, REPRESSION, ECON_FISC, LABOR_SOC, FOOD_RES,
# DIPLO_GEO, SOC_MOBIL, STRUCT_DEV.
#
# Falls back per the rubric spec when direction-of-effect annotations are not
# yet available in the catalog. Will be replaced by signed-direction counts
# when cascade-Opus's Phase 5 v0.1a annotation sprint lands.
SECTOR_RELEVANCE: dict[str, list[str]] = {
    # A — Political Power & Regime
    "elections_and_voting": ["GOV_INST", "REPRESSION", "SOC_MOBIL"],
    "government_formation": ["GOV_INST", "REPRESSION"],
    "constitutional_change": ["GOV_INST", "REPRESSION"],
    "decentralization_and_federalism": ["GOV_INST"],
    "democratic_transition": ["GOV_INST", "REPRESSION", "SOC_MOBIL"],
    "executive_power_consolidation": ["GOV_INST", "REPRESSION"],
    "military_coup": ["CONFLICT", "GOV_INST", "REPRESSION"],
    "transitional_justice": ["REPRESSION", "GOV_INST", "CONFLICT"],
    "peacekeeping_and_peace_process": ["DIPLO_GEO", "CONFLICT"],
    # B — Conflict & Political Violence
    "interstate_war": ["CONFLICT", "DIPLO_GEO", "DISPLACE"],
    "civil_war_and_insurgency": ["CONFLICT", "REPRESSION", "GOV_INST", "DISPLACE"],
    "terrorist_attack": ["CONFLICT", "REPRESSION"],
    "foreign_intervention": ["CONFLICT", "DIPLO_GEO"],
    "ethnic_and_communal_conflict": ["CONFLICT", "REPRESSION", "SOC_MOBIL"],
    "political_violence": ["CONFLICT", "REPRESSION", "GOV_INST"],
    # C — State Authority & Governance
    "political_repression": ["REPRESSION", "GOV_INST", "SOC_MOBIL"],
    "political_corruption": ["GOV_INST", "REPRESSION", "ECON_FISC"],
    "human_rights_violation": ["REPRESSION", "GOV_INST"],
    "human_rights_reform": ["REPRESSION", "GOV_INST", "SOC_MOBIL"],
    "military_policy_and_reform": ["CONFLICT", "GOV_INST"],
    # D — Economic & Financial Stress
    "currency_crisis": ["ECON_FISC", "LABOR_SOC"],
    "banking_and_financial_crisis": ["ECON_FISC", "LABOR_SOC"],
    "economic_recession": ["ECON_FISC", "LABOR_SOC"],
    "fiscal_policy_change": ["ECON_FISC"],
    "monetary_policy_change": ["ECON_FISC"],
    "economic_liberalization": ["ECON_FISC", "LABOR_SOC"],
    "economic_nationalization": ["ECON_FISC", "GOV_INST"],
    "economic_recovery": ["ECON_FISC", "LABOR_SOC"],
    "economic_growth_milestone": ["ECON_FISC", "LABOR_SOC", "STRUCT_DEV"],
    "trade_agreement": ["ECON_FISC", "DIPLO_GEO"],
    "trade_dispute": ["ECON_FISC", "DIPLO_GEO"],
    "foreign_direct_investment": ["ECON_FISC", "DIPLO_GEO"],
    "industrial_policy": ["ECON_FISC", "STRUCT_DEV"],
    "sanctions_and_arms_embargo": ["DIPLO_GEO", "ECON_FISC", "CONFLICT"],
    "foreign_aid_and_development": ["DIPLO_GEO", "ECON_FISC", "STRUCT_DEV"],
    # E — Social Mobilization & Civil Society
    "mass_protest": ["SOC_MOBIL", "REPRESSION", "LABOR_SOC", "GOV_INST"],
    "labor_action": ["LABOR_SOC", "SOC_MOBIL"],
    "social_policy_reform": ["LABOR_SOC", "SOC_MOBIL"],
    "public_health_reform": ["LABOR_SOC", "STRUCT_DEV"],
    "poverty_and_inequality_crisis": ["LABOR_SOC", "ECON_FISC"],
    "religious_and_social_movement": ["SOC_MOBIL", "REPRESSION"],
    "migration_and_refugees": ["DISPLACE", "CONFLICT", "ECON_FISC"],
    # F — Diplomatic & Geopolitical Relations
    "bilateral_treaty": ["DIPLO_GEO", "GOV_INST"],
    "multilateral_agreement": ["DIPLO_GEO", "GOV_INST"],
    "diplomatic_rupture": ["DIPLO_GEO", "CONFLICT"],
    "territorial_disputes": ["DIPLO_GEO", "CONFLICT"],
    "regional_integration": ["DIPLO_GEO", "ECON_FISC", "GOV_INST"],
    # G — Humanitarian & Environmental Crisis
    "earthquake": ["FOOD_RES", "STRUCT_DEV"],
    "flood_and_cyclone": ["FOOD_RES", "STRUCT_DEV"],
    "volcanic_eruption": ["FOOD_RES", "STRUCT_DEV"],
    "natural_disaster": ["FOOD_RES", "STRUCT_DEV"],
    "drought_and_famine": ["FOOD_RES", "ECON_FISC"],
    "epidemic_and_pandemic": ["STRUCT_DEV", "FOOD_RES"],
    "humanitarian_crisis": ["CONFLICT", "DISPLACE", "FOOD_RES"],
    "water_crisis": ["FOOD_RES", "STRUCT_DEV"],
    # H — Structural & Development Context
    "energy_policy": ["STRUCT_DEV", "ECON_FISC"],
    "oil_and_gas": ["STRUCT_DEV", "ECON_FISC"],
    "renewable_energy": ["STRUCT_DEV"],
    "environmental_policy": ["STRUCT_DEV", "FOOD_RES"],
    "climate_agreement": ["DIPLO_GEO", "STRUCT_DEV"],
    "resource_conflict": ["CONFLICT", "FOOD_RES", "STRUCT_DEV"],
    "infrastructure_project": ["STRUCT_DEV", "ECON_FISC"],
    "urban_development": ["STRUCT_DEV", "ECON_FISC"],
    "education_reform": ["STRUCT_DEV"],
    "education_and_research": ["STRUCT_DEV"],
    "digital_policy": ["STRUCT_DEV"],
    "technology_breakthrough": ["STRUCT_DEV"],
    "cyberattack": ["CONFLICT", "STRUCT_DEV"],
    "cultural_and_heritage": ["STRUCT_DEV"],
    "sport_and_international_event": ["STRUCT_DEV"],
    "agricultural_policy": ["FOOD_RES", "ECON_FISC"],
}


# Survival sub-factor scores (Ji-Hoon F2/F3/F4) per category.
# F2 (event-timing clarity, 0-3):
#   3 = clean onset with calendar-year precision
#   1 = drift with >=+/-2 year uncertainty
#   0 = definitionally ambiguous
# F3 (right-censoring tractability, 0-2):
#   2 = censoring ignorable (event simply hasn't occurred)
#   1 = censoring partially informative
#   0 = censoring confounds the label
# F4 (label dating precision, 0-2):
#   2 = UCDP/IMF/COW/EM-DAT date confirmed
#   1 = QGI annotation with +/-1 year confidence
#   0 = contested onset
#
# Default for unspecified categories: (2, 2, 1) -- moderate clarity, ignorable
# censoring, QGI dating -- sums to 5 (just barely survival-eligible). Override
# below for known-clear or known-ambiguous categories.
SURVIVAL_SUB_FACTORS_DEFAULT = (2, 2, 1)
SURVIVAL_SUB_FACTORS: dict[str, tuple[int, int, int]] = {
    # Sharp onset, external dating: full marks
    "elections_and_voting": (3, 2, 2),
    "constitutional_change": (3, 2, 2),
    "military_coup": (3, 2, 2),
    "interstate_war": (3, 2, 2),
    "civil_war_and_insurgency": (3, 2, 2),
    "terrorist_attack": (3, 2, 2),
    "currency_crisis": (3, 2, 2),
    "banking_and_financial_crisis": (3, 2, 2),
    "economic_recession": (3, 2, 2),
    "earthquake": (3, 2, 2),
    "flood_and_cyclone": (3, 2, 2),
    "volcanic_eruption": (3, 2, 2),
    "natural_disaster": (3, 2, 2),
    "epidemic_and_pandemic": (3, 2, 2),
    "trade_agreement": (3, 2, 2),
    "trade_dispute": (3, 2, 2),
    "sanctions_and_arms_embargo": (3, 2, 2),
    "multilateral_agreement": (3, 2, 2),
    "regional_integration": (3, 2, 2),
    "climate_agreement": (3, 2, 2),
    "peacekeeping_and_peace_process": (3, 2, 2),
    # Onset clear, dating from QGI corpus
    "government_formation": (3, 2, 1),
    "diplomatic_rupture": (3, 2, 1),
    "bilateral_treaty": (3, 2, 1),
    "foreign_intervention": (2, 2, 2),
    "ethnic_and_communal_conflict": (2, 2, 2),
    "political_violence": (2, 2, 2),
    "mass_protest": (2, 2, 2),
    "drought_and_famine": (2, 2, 2),
    "humanitarian_crisis": (2, 2, 2),
    "migration_and_refugees": (2, 2, 2),
    "territorial_disputes": (2, 2, 1),
    "executive_power_consolidation": (2, 1, 1),
    "democratic_transition": (2, 2, 1),
    # Diffuse / drift events (penalize F2)
    "political_repression": (1, 1, 1),
    "political_corruption": (1, 1, 1),
    "human_rights_violation": (1, 1, 1),
    "human_rights_reform": (1, 1, 1),
    "transitional_justice": (1, 2, 1),
    "military_policy_and_reform": (1, 2, 1),
    "fiscal_policy_change": (2, 2, 1),
    "monetary_policy_change": (2, 2, 1),
    "economic_liberalization": (1, 1, 1),
    "economic_nationalization": (1, 1, 1),
    "economic_recovery": (1, 1, 1),
    "economic_growth_milestone": (1, 1, 1),
    "foreign_direct_investment": (1, 1, 1),
    "industrial_policy": (1, 1, 1),
    "foreign_aid_and_development": (1, 1, 1),
    "labor_action": (2, 1, 1),
    "social_policy_reform": (1, 1, 1),
    "public_health_reform": (1, 1, 1),
    "religious_and_social_movement": (1, 1, 1),
    "decentralization_and_federalism": (2, 2, 1),
    "energy_policy": (1, 1, 1),
    "oil_and_gas": (1, 1, 1),
    "renewable_energy": (1, 1, 1),
    "environmental_policy": (1, 1, 1),
    "resource_conflict": (1, 2, 1),
    "infrastructure_project": (1, 1, 1),
    "urban_development": (1, 1, 1),
    "education_reform": (1, 1, 1),
    "education_and_research": (1, 1, 1),
    "digital_policy": (1, 1, 1),
    "technology_breakthrough": (1, 1, 1),
    "cyberattack": (2, 2, 1),
    "cultural_and_heritage": (1, 1, 1),
    "sport_and_international_event": (3, 2, 2),
    "agricultural_policy": (1, 1, 1),
    "water_crisis": (1, 1, 1),
    "poverty_and_inequality_crisis": (0, 0, 0),  # gradient
}


@dataclass
class RecipeRubricRow:
    rank: int | None
    category_id: str
    layer1_id: str
    layer2_id: str
    layer2_label: str
    n_positive_verified: int  # gates Factor A; Kwame's spec language
    n_positive_total: int     # all curated (verified + unverified) — transparency
    A: float
    B: float
    C: float
    D: float
    S: float
    F2: int
    F3: int
    F4: int
    survival_eligible: bool
    F5: int
    head_class: str
    label_source_examples: list[str]
    relevant_sectors: list[str]
    n_relevant_indicators: int
    excluded_by_hard_gate: bool


# ---------- Pure functions (testable) ----------


def sha256_of_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_of_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _safe_relative(path: Path, root: Path) -> str:
    """Return path relative to root if possible; otherwise return absolute path.

    Used for the JSON metadata block — synthetic test inputs in tmp_path are
    outside REPO_ROOT, and we must not crash on them.
    """
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def load_category_taxonomy(category_mapping_path: Path) -> dict[str, dict[str, str]]:
    """Return category_id -> {layer1_id, layer2_id, layer2_label}.

    Reads the layer1 -> layer2 -> layer3 hierarchy and inverts to layer3 -> ancestors.
    The label stored is the L2 label because the taxonomy file does not carry
    distinct L3 labels (L3 entries are bare string IDs).
    """
    mapping = json.loads(category_mapping_path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, str]] = {}
    for l1 in mapping["layer1"]:
        l1_id = l1["id"]
        for l2 in l1["layer2"]:
            l2_id = l2["id"]
            l2_label = l2["label"]
            for l3 in l2["layer3"]:
                # Some layer3 IDs appear under multiple layer2 (e.g.,
                # sanctions_and_arms_embargo under D7 + F3). Keep the FIRST
                # occurrence (by JSON order) as canonical for ranking purposes;
                # sorted layer1->layer2 order is deterministic.
                if l3 in out:
                    continue
                out[l3] = {
                    "layer1_id": l1_id,
                    "layer2_id": l2_id,
                    "layer2_label": l2_label,
                }
    return out


def load_indicator_sector_map(indicator_sectors_path: Path) -> dict[str, str]:
    """Return indicator_code -> sector_code from indicator-sectors.json."""
    data = json.loads(indicator_sectors_path.read_text(encoding="utf-8"))
    return {code: entry["sector"] for code, entry in data["indicator_to_sector"].items()}


def load_curated_events(curated_dir: Path) -> list[dict[str, Any]]:
    """Return flat list of all events across all country files.

    Each event dict has at minimum: country, year, category, verified.
    Skips files starting with '_' (backups, scratch). Tolerant of malformed
    JSON (logs to stderr, skips file).
    """
    events: list[dict[str, Any]] = []
    for path in sorted(curated_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            print(f"WARN: skipping malformed {path.name}: {err}", file=sys.stderr)
            continue
        if not isinstance(data, list):
            continue
        country = path.stem
        for ev in data:
            if not isinstance(ev, dict):
                continue
            year = ev.get("year")
            cat = ev.get("category")
            if year is None or cat is None:
                continue
            events.append({
                "country": country,
                "year": year,
                "category": cat,
                "verified": bool(ev.get("verified", False)),
            })
    return events


def count_n_positive(
    events: list[dict[str, Any]],
    window: tuple[int, int],
    verified_only: bool = False,
) -> dict[str, int]:
    """Count unique (country, year) pairs per category in the training window."""
    seen: dict[str, set[tuple[str, int]]] = defaultdict(set)
    lo, hi = window
    for ev in events:
        if not (lo <= ev["year"] <= hi):
            continue
        if verified_only and not ev["verified"]:
            continue
        seen[ev["category"]].add((ev["country"], ev["year"]))
    return {cat: len(pairs) for cat, pairs in seen.items()}


def compute_factor_a(
    n_positive: int,
    max_n_positive: int,
    gate_min: int = HARD_GATE_MIN_N_POSITIVE,
) -> tuple[float, bool]:
    """Return (A, excluded_by_gate). HARD GATE: if below gate_min, A=0, excluded=True."""
    if n_positive < gate_min:
        return 0.0, True
    if max_n_positive == 0:
        return 0.0, True
    return n_positive / max_n_positive, False


def compute_factor_b(category: str) -> tuple[float, list[str]]:
    """Look up label clarity. Categories not in LABEL_CLARITY_B default to 0.5."""
    if category in LABEL_CLARITY_B:
        return LABEL_CLARITY_B[category]
    return 0.5, ["unscored - defaults to 0.5 (review at next Majles)"]


def compute_factor_c(
    category: str,
    indicator_sector_map: dict[str, str],
    divisor: int = C_DIVISOR,
) -> tuple[float, list[str], int]:
    """Sector-proxy fallback for direction-of-effect coverage.

    Returns (C, relevant_sectors, n_relevant_indicators).
    """
    relevant = SECTOR_RELEVANCE.get(category, [])
    if not relevant:
        return 0.0, [], 0
    relevant_set = set(relevant)
    n_indicators = sum(1 for s in indicator_sector_map.values() if s in relevant_set)
    c = min(1.0, n_indicators / divisor)
    return c, relevant, n_indicators


def compute_factor_d(
    pre_d_scores: dict[str, float],
    sector_relevance: dict[str, list[str]],
    indicator_sector_map: dict[str, str],
    excluded: set[str],
    top_n: int = D_TOP_N,
    divisor: int = D_DIVISOR,
    min_shared: int = D_MIN_SHARED_INDICATORS,
) -> dict[str, float]:
    """Iterative D computation.

    Identify top-N by S' = 0.35A + 0.25B + 0.25C, then for each r count other
    r' in top-N sharing >=min_shared indicators (sector-proxy: indicators
    whose sector is in r's relevance list AND in r's sector list AND in the same
    sector as the shared count threshold).
    """
    # Indicators relevant per category (sector proxy)
    relevant_per_cat: dict[str, set[str]] = {}
    for cat, sectors in sector_relevance.items():
        if cat in excluded:
            continue
        sset = set(sectors)
        relevant_per_cat[cat] = {
            ind for ind, sec in indicator_sector_map.items() if sec in sset
        }

    # Top-N by S' (gated categories already excluded from pre_d_scores)
    eligible = [(cat, score) for cat, score in pre_d_scores.items() if cat not in excluded]
    eligible.sort(key=lambda kv: (-kv[1], kv[0]))  # stable: ties broken by name
    top = {kv[0] for kv in eligible[:top_n]}

    out: dict[str, float] = {}
    for cat in pre_d_scores:
        if cat in excluded:
            out[cat] = 0.0
            continue
        cat_inds = relevant_per_cat.get(cat, set())
        if not cat_inds:
            out[cat] = 0.0
            continue
        shared_count = 0
        for other in top:
            if other == cat:
                continue
            other_inds = relevant_per_cat.get(other, set())
            # Count indicators that are (a) shared AND (b) in the same sector.
            # Since each indicator belongs to one sector, "in the same sector"
            # is automatic for shared indicators.
            n_shared = len(cat_inds & other_inds)
            if n_shared >= min_shared:
                shared_count += 1
        out[cat] = min(1.0, shared_count / divisor)
    return out


def assign_head_class(survival_eligible: bool, n_positive: int) -> tuple[int, str]:
    """Return (F5_score, head_class_label).

    Per spec 05-recipe-prioritization-rubric.md F5 table:
      3 — survival head warranted (survival_eligible AND n_positive >= 20)
      2 — asymmetric-loss GBM (rare class, n_positive < 20)
      1 — standard GBM (n_positive >= 20 but not survival-eligible)
      0 — excluded by hard gate (n_positive < 8)

    Survival-eligible recipes with n_positive in [8, 20) get F5=2 with a
    label that explicitly notes the survival-deferred state -- they will
    be reconsidered for survival heads if n_positive grows past 20 in
    a future mandate cycle (per the re-entry-of-falsified-recipes protocol).
    """
    if n_positive < HARD_GATE_MIN_N_POSITIVE:
        return 0, "excluded"
    if survival_eligible and n_positive >= 20:
        return 3, "discrete-time hazard (DeepHit-lite)"
    if n_positive < 20:
        if survival_eligible:
            return 2, "asymmetric-loss GBM (rare-class; survival deferred until n>=20)"
        return 2, "asymmetric-loss GBM (rare-class)"
    return 1, "standard GBM"


def survival_subfactors(category: str) -> tuple[int, int, int]:
    return SURVIVAL_SUB_FACTORS.get(category, SURVIVAL_SUB_FACTORS_DEFAULT)


# ---------- Main orchestrator ----------


def compute_recipe_rubric(
    curated_dir: Path = DEFAULT_CURATED_DIR,
    category_mapping_path: Path = DEFAULT_CATEGORY_MAPPING,
    indicator_sectors_path: Path = DEFAULT_INDICATOR_SECTORS,
    window: tuple[int, int] = TRAINING_WINDOW,
) -> dict[str, Any]:
    taxonomy = load_category_taxonomy(category_mapping_path)
    indicator_sector_map = load_indicator_sector_map(indicator_sectors_path)
    events = load_curated_events(curated_dir)

    # Per Kwame's spec language ("Count VERIFIED positive country-year occurrences"),
    # the HARD GATE and Factor A normalization use verified-only counts. The
    # all-curated count (n_positive_total) is reported as a transparency field.
    n_pos_total = count_n_positive(events, window)
    n_pos_verified = count_n_positive(events, window, verified_only=True)

    # Use the taxonomy as source of truth for "all 71 categories" -- include
    # zero-coverage ones too so the founder sees gaps.
    all_categories = sorted(taxonomy.keys())
    max_n = max((n_pos_verified.get(c, 0) for c in all_categories), default=0)

    # Pass 1: A, B, C, pre-D score
    rows: dict[str, dict[str, Any]] = {}
    excluded: set[str] = set()
    for cat in all_categories:
        n_v = n_pos_verified.get(cat, 0)
        n_t = n_pos_total.get(cat, 0)
        a, gated = compute_factor_a(n_v, max_n)
        b, src = compute_factor_b(cat)
        c, sectors, n_inds = compute_factor_c(cat, indicator_sector_map)
        if gated:
            excluded.add(cat)
        rows[cat] = {
            "n_positive_verified": n_v,
            "n_positive_total": n_t,
            "A": a, "B": b, "C": c,
            "label_source_examples": src,
            "relevant_sectors": sectors,
            "n_relevant_indicators": n_inds,
            "excluded_by_hard_gate": gated,
        }

    pre_d = {cat: WEIGHTS["A"] * r["A"] + WEIGHTS["B"] * r["B"] + WEIGHTS["C"] * r["C"]
             for cat, r in rows.items()}

    # Pass 2: D (iterative)
    d_scores = compute_factor_d(pre_d, SECTOR_RELEVANCE, indicator_sector_map, excluded)

    # Pass 3: final S, survival flags, F5
    final_rows: list[RecipeRubricRow] = []
    for cat in all_categories:
        r = rows[cat]
        d = d_scores.get(cat, 0.0)
        # Per spec: hard-gated recipes have S=0 (excluded from ML track).
        if r["excluded_by_hard_gate"]:
            s = 0.0
        else:
            s = (
                WEIGHTS["A"] * r["A"]
                + WEIGHTS["B"] * r["B"]
                + WEIGHTS["C"] * r["C"]
                + WEIGHTS["D"] * d
            )
        f2, f3, f4 = survival_subfactors(cat)
        survival_eligible = (f2 + f3 + f4) >= 5
        f5, head_class = assign_head_class(survival_eligible, r["n_positive_verified"])
        meta = taxonomy.get(cat, {"layer1_id": "?", "layer2_id": "?", "layer2_label": cat})
        final_rows.append(RecipeRubricRow(
            rank=None,  # filled after sort
            category_id=cat,
            layer1_id=meta["layer1_id"],
            layer2_id=meta["layer2_id"],
            layer2_label=meta["layer2_label"],
            n_positive_verified=r["n_positive_verified"],
            n_positive_total=r["n_positive_total"],
            A=round(r["A"], 4), B=round(r["B"], 4),
            C=round(r["C"], 4), D=round(d, 4),
            S=round(s, 4),
            F2=f2, F3=f3, F4=f4,
            survival_eligible=survival_eligible,
            F5=f5,
            head_class=head_class,
            label_source_examples=r["label_source_examples"],
            relevant_sectors=r["relevant_sectors"],
            n_relevant_indicators=r["n_relevant_indicators"],
            excluded_by_hard_gate=r["excluded_by_hard_gate"],
        ))

    # Rank: descending S; ties broken alphabetically by category_id; excluded
    # rows get rank=None and sit at the bottom.
    eligible = [r for r in final_rows if not r.excluded_by_hard_gate]
    eligible.sort(key=lambda r: (-r.S, r.category_id))
    for i, r in enumerate(eligible, start=1):
        r.rank = i
    excluded_rows = sorted(
        (r for r in final_rows if r.excluded_by_hard_gate),
        key=lambda r: r.category_id,
    )
    ordered = eligible + excluded_rows

    # Compute event-corpus state hash for reproducibility (sorted triples).
    triples = sorted(
        (e["country"], e["year"], e["category"]) for e in events
        if window[0] <= e["year"] <= window[1]
    )
    corpus_state_hash = sha256_of_str("\n".join(f"{c}|{y}|{cat}" for c, y, cat in triples))

    payload = {
        "schema_version": 1,
        "generated_for_stage": "ml-track stage-0 pre-registration",
        "training_window": list(window),
        "weights": WEIGHTS,
        "hard_gate": {"min_n_positive": HARD_GATE_MIN_N_POSITIVE},
        "factor_d_params": {
            "top_n": D_TOP_N,
            "divisor": D_DIVISOR,
            "min_shared_indicators": D_MIN_SHARED_INDICATORS,
        },
        "factor_c_divisor": C_DIVISOR,
        "n_categories_total": len(all_categories),
        "n_categories_excluded_by_hard_gate": sum(1 for r in final_rows if r.excluded_by_hard_gate),
        "n_indicators_in_sector_map": len(indicator_sector_map),
        "sources": {
            "category_mapping_path": _safe_relative(category_mapping_path, REPO_ROOT),
            "category_mapping_sha256": sha256_of_file(category_mapping_path),
            "indicator_sectors_path": _safe_relative(indicator_sectors_path, REPO_ROOT),
            "indicator_sectors_sha256": sha256_of_file(indicator_sectors_path),
            "events_curated_dir": _safe_relative(curated_dir, REPO_ROOT),
            "events_curated_n_files": sum(
                1 for p in curated_dir.glob("*.json") if not p.name.startswith("_")
            ),
            "events_curated_state_hash_in_window": corpus_state_hash,
            "events_in_window": len(triples),
            "structural_break_audit_present": _structural_break_audit_path().exists(),
        },
        "notes": [
            "HARD GATE + Factor A use VERIFIED-only n_positive (Kwame's spec language).",
            "n_positive_total field reports all-curated count for transparency.",
            "Factor C uses SECTOR PROXY -- direction-of-effect annotations not yet present in catalog.",
            "F5 head_class is a hint, not a binding contract; Stage 2 may revert survival -> GBM via Rule F3.",
            "Hard-gated recipes (n_positive_verified < 8) carry rank=None and S=0.0 per spec.",
            "B=0.0 categories indicate gradient definitions; revisit at next Majles convening.",
            "B=0.5 for human_rights / corruption / repression categories: gradient indices like CIRI/HRMI"
            " are externally maintained but continuous, not binary onsets. 2026-05-04 Stage-0 consult"
            " (Kwame + Ji-Hoon) converged STRICT: B=1.0 only for binary external events.",
        ] + (
            [] if _structural_break_audit_path().exists()
            else ["structural-break-audit-2026-05.json absent at gen time -- C and "
                  "feature-engineering refinements deferred until cascade-Opus ships it."]
        ),
        "ranking": [asdict(r) for r in ordered],
    }
    return payload


def _structural_break_audit_path() -> Path:
    return REPO_ROOT / "qgi-data" / "reference" / "structural-break-audit-2026-05.json"


def render_summary(payload: dict[str, Any], top_k: int = 25) -> str:
    """Return a plain-text top-K summary table for stdout / founder review.

    Columns: n+v = n_positive_verified (gates the rubric); n+t = n_positive_total
    (all curated, for transparency).
    """
    lines: list[str] = []
    lines.append(
        f"Recipe rubric  -- {payload['n_categories_total']} categories total, "
        f"{payload['n_categories_excluded_by_hard_gate']} excluded by hard gate "
        f"(n_positive_verified < {payload['hard_gate']['min_n_positive']})."
    )
    lines.append(
        f"Weights: A={payload['weights']['A']} B={payload['weights']['B']} "
        f"C={payload['weights']['C']} D={payload['weights']['D']}"
    )
    lines.append(f"Training window: {payload['training_window']}")
    lines.append("")
    header = (
        f"{'#':>3}  {'category':<38} {'n+v':>4} {'n+t':>4} {'A':>5} {'B':>4} {'C':>4} {'D':>4} "
        f"{'S':>6} {'F5':>2}  head_class"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for r in payload["ranking"][:top_k]:
        if r["rank"] is None:
            continue
        lines.append(
            f"{r['rank']:>3}  {r['category_id']:<38} "
            f"{r['n_positive_verified']:>4} {r['n_positive_total']:>4} "
            f"{r['A']:>5.3f} {r['B']:>4.2f} {r['C']:>4.2f} {r['D']:>4.2f} "
            f"{r['S']:>6.4f} {r['F5']:>2}  {r['head_class']}"
        )
    excluded = [r for r in payload["ranking"] if r["excluded_by_hard_gate"]]
    if excluded:
        lines.append("")
        lines.append(f"Excluded by hard gate (n_positive_verified < {payload['hard_gate']['min_n_positive']}):")
        for r in excluded:
            lines.append(f"  {r['category_id']:<38} n+v={r['n_positive_verified']:>4}  n+t={r['n_positive_total']:>4}")
    return "\n".join(lines)


# ---------- CLI ----------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help=f"Output JSON path (default: {DEFAULT_OUTPUT.relative_to(REPO_ROOT)})")
    parser.add_argument("--curated-dir", type=Path, default=DEFAULT_CURATED_DIR)
    parser.add_argument("--category-mapping", type=Path, default=DEFAULT_CATEGORY_MAPPING)
    parser.add_argument("--indicator-sectors", type=Path, default=DEFAULT_INDICATOR_SECTORS)
    parser.add_argument("--print-summary", action="store_true",
                        help="Print top-25 ranking to stdout for founder review")
    parser.add_argument("--top-k", type=int, default=25)
    parser.add_argument("--dry-run", action="store_true", help="Compute but don't write file")
    args = parser.parse_args(argv)

    payload = compute_recipe_rubric(
        curated_dir=args.curated_dir,
        category_mapping_path=args.category_mapping,
        indicator_sectors_path=args.indicator_sectors,
    )

    if args.print_summary:
        print(render_summary(payload, top_k=args.top_k))

    if not args.dry_run:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        print(f"\nwrote {_safe_relative(args.output, REPO_ROOT)}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
