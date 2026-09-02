/**
 * Static L3 → L1 category mapping derived from the layered taxonomy
 * (qgi-data/taxonomy/taxonomy_hierarchy.json).
 *
 * Every L3 category slug used in country-risks.json maps to its L1 group
 * code and label. This lets the frontend render domain chips, color
 * stripes, and group labels without a pipeline change.
 */

// ---------------------------------------------------------------------------
// L1 domain definitions
// ---------------------------------------------------------------------------

export interface L1Group {
  code: string;
  label: string;
  shortLabel: string;
  color: string;
}

export const L1_GROUPS: L1Group[] = [
  {
    code: "A",
    label: "Political Power & Regime",
    shortLabel: "Political",
    color: "#7B5EE6",
  },
  {
    code: "B",
    label: "Conflict & Political Violence",
    shortLabel: "Conflict",
    color: "#E64545",
  },
  {
    code: "C",
    label: "State Authority & Governance",
    shortLabel: "Governance",
    color: "#E68F29",
  },
  {
    code: "D",
    label: "Economic & Financial Stress",
    shortLabel: "Economic",
    color: "#3FA9F5",
  },
  {
    code: "E",
    label: "Social Mobilization & Civil Society",
    shortLabel: "Social",
    color: "#3FBF8F",
  },
  {
    code: "F",
    label: "Diplomatic & Geopolitical Relations",
    shortLabel: "Diplomacy",
    color: "#9F7AEA",
  },
  {
    code: "G",
    label: "Humanitarian & Environmental Crisis",
    shortLabel: "Humanitarian",
    color: "#E94989",
  },
  {
    code: "H",
    label: "Structural & Development Context",
    shortLabel: "Structural",
    color: "#7A8FA0",
  },
];

// ---------------------------------------------------------------------------
// L3 → L1 lookup  (slug → { group, label })
// ---------------------------------------------------------------------------

export interface L1Mapping {
  group: string; // e.g. "A"
  label: string; // e.g. "Political Power & Regime"
}

export const CATEGORY_L1_MAP: Record<string, L1Mapping> = {
  // ── A: Political Power & Regime ──────────────────────────────────────
  elections_and_voting: { group: "A", label: "Political Power & Regime" },
  government_formation: { group: "A", label: "Political Power & Regime" },
  constitutional_change: { group: "A", label: "Political Power & Regime" },
  decentralization_and_federalism: { group: "A", label: "Political Power & Regime" },
  democratic_transition: { group: "A", label: "Political Power & Regime" },
  executive_power_consolidation: { group: "A", label: "Political Power & Regime" },
  military_coup: { group: "A", label: "Political Power & Regime" },
  coup_attempt_or_succession: { group: "A", label: "Political Power & Regime" }, // T5 #298 fix: Colombia coup page rendered "Uncategorized"
  transitional_justice: { group: "A", label: "Political Power & Regime" },
  peacekeeping_and_peace_process: { group: "A", label: "Political Power & Regime" },
  constitutional_referendum: { group: "A", label: "Political Power & Regime" }, // legacy slug

  // ── B: Conflict & Political Violence ─────────────────────────────────
  interstate_war: { group: "B", label: "Conflict & Political Violence" },
  civil_war_and_insurgency: { group: "B", label: "Conflict & Political Violence" },
  terrorist_attack: { group: "B", label: "Conflict & Political Violence" },
  foreign_intervention: { group: "B", label: "Conflict & Political Violence" },
  ethnic_and_communal_conflict: { group: "B", label: "Conflict & Political Violence" },
  political_violence: { group: "B", label: "Conflict & Political Violence" },
  ceasefire_agreement: { group: "B", label: "Conflict & Political Violence" }, // legacy slug
  west_bank_violence: { group: "B", label: "Conflict & Political Violence" }, // legacy slug
  israeli_military_operation: { group: "B", label: "Conflict & Political Violence" }, // legacy slug
  rocket_attack: { group: "B", label: "Conflict & Political Violence" }, // legacy slug

  // ── C: State Authority & Governance ──────────────────────────────────
  political_repression: { group: "C", label: "State Authority & Governance" },
  political_corruption: { group: "C", label: "State Authority & Governance" },
  human_rights_violation: { group: "C", label: "State Authority & Governance" },
  human_rights_reform: { group: "C", label: "State Authority & Governance" },
  military_policy_and_reform: { group: "C", label: "State Authority & Governance" },

  // ── D: Economic & Financial Stress ───────────────────────────────────
  currency_crisis: { group: "D", label: "Economic & Financial Stress" },
  banking_and_financial_crisis: { group: "D", label: "Economic & Financial Stress" },
  economic_recession: { group: "D", label: "Economic & Financial Stress" },
  fiscal_policy_change: { group: "D", label: "Economic & Financial Stress" },
  monetary_policy_change: { group: "D", label: "Economic & Financial Stress" },
  economic_liberalization: { group: "D", label: "Economic & Financial Stress" },
  economic_nationalization: { group: "D", label: "Economic & Financial Stress" },
  economic_recovery: { group: "D", label: "Economic & Financial Stress" },
  economic_growth_milestone: { group: "D", label: "Economic & Financial Stress" },
  economic_growth: { group: "D", label: "Economic & Financial Stress" }, // legacy slug
  trade_agreement: { group: "D", label: "Economic & Financial Stress" },
  trade_dispute: { group: "D", label: "Economic & Financial Stress" },
  foreign_direct_investment: { group: "D", label: "Economic & Financial Stress" },
  industrial_policy: { group: "D", label: "Economic & Financial Stress" },
  sanctions_and_arms_embargo: { group: "D", label: "Economic & Financial Stress" },
  foreign_aid_and_development: { group: "D", label: "Economic & Financial Stress" },
  economic_struggle: { group: "D", label: "Economic & Financial Stress" }, // legacy slug
  economic_crisi: { group: "D", label: "Economic & Financial Stress" }, // truncated legacy slug
  economic_reform: { group: "D", label: "Economic & Financial Stress" }, // legacy slug

  // ── E: Social Mobilization & Civil Society ───────────────────────────
  mass_protest: { group: "E", label: "Social Mobilization & Civil Society" },
  labor_action: { group: "E", label: "Social Mobilization & Civil Society" },
  social_policy_reform: { group: "E", label: "Social Mobilization & Civil Society" },
  public_health_reform: { group: "E", label: "Social Mobilization & Civil Society" },
  poverty_and_inequality_crisis: {
    group: "E",
    label: "Social Mobilization & Civil Society",
  },
  religious_and_social_movement: {
    group: "E",
    label: "Social Mobilization & Civil Society",
  },
  migration_and_refugees: { group: "E", label: "Social Mobilization & Civil Society" },
  political_unrest: { group: "E", label: "Social Mobilization & Civil Society" }, // legacy slug
  social_program: { group: "E", label: "Social Mobilization & Civil Society" }, // legacy slug

  // ── F: Diplomatic & Geopolitical Relations ───────────────────────────
  bilateral_treaty: { group: "F", label: "Diplomatic & Geopolitical Relations" },
  multilateral_agreement: { group: "F", label: "Diplomatic & Geopolitical Relations" },
  diplomatic_rupture: { group: "F", label: "Diplomatic & Geopolitical Relations" },
  territorial_disputes: { group: "F", label: "Diplomatic & Geopolitical Relations" },
  regional_integration: { group: "F", label: "Diplomatic & Geopolitical Relations" },
  diplomatic_effort: { group: "F", label: "Diplomatic & Geopolitical Relations" }, // legacy slug
  international_diplomacy: { group: "F", label: "Diplomatic & Geopolitical Relations" }, // legacy slug

  // ── G: Humanitarian & Environmental Crisis ───────────────────────────
  earthquake: { group: "G", label: "Humanitarian & Environmental Crisis" },
  flood_and_cyclone: { group: "G", label: "Humanitarian & Environmental Crisis" },
  volcanic_eruption: { group: "G", label: "Humanitarian & Environmental Crisis" },
  natural_disaster: { group: "G", label: "Humanitarian & Environmental Crisis" },
  drought_and_famine: { group: "G", label: "Humanitarian & Environmental Crisis" },
  epidemic_and_pandemic: { group: "G", label: "Humanitarian & Environmental Crisis" },
  humanitarian_crisis: { group: "G", label: "Humanitarian & Environmental Crisis" },
  water_crisis: { group: "G", label: "Humanitarian & Environmental Crisis" },
  pandemic_response: { group: "G", label: "Humanitarian & Environmental Crisis" }, // legacy slug
  humanitarian_crisi: { group: "G", label: "Humanitarian & Environmental Crisis" }, // truncated legacy slug

  // ── H: Structural & Development Context ──────────────────────────────
  energy_policy: { group: "H", label: "Structural & Development Context" },
  oil_and_gas: { group: "H", label: "Structural & Development Context" },
  renewable_energy: { group: "H", label: "Structural & Development Context" },
  environmental_policy: { group: "H", label: "Structural & Development Context" },
  climate_agreement: { group: "H", label: "Structural & Development Context" },
  resource_conflict: { group: "H", label: "Structural & Development Context" },
  infrastructure_project: { group: "H", label: "Structural & Development Context" },
  urban_development: { group: "H", label: "Structural & Development Context" },
  education_reform: { group: "H", label: "Structural & Development Context" },
  education_and_research: { group: "H", label: "Structural & Development Context" },
  digital_policy: { group: "H", label: "Structural & Development Context" },
  technology_breakthrough: { group: "H", label: "Structural & Development Context" },
  cyberattack: { group: "H", label: "Structural & Development Context" },
  cultural_and_heritage: { group: "H", label: "Structural & Development Context" },
  sport_and_international_event: {
    group: "H",
    label: "Structural & Development Context",
  },
  agricultural_policy: { group: "H", label: "Structural & Development Context" },
  environmental_effort: { group: "H", label: "Structural & Development Context" }, // legacy slug
  infrastructure_development: { group: "H", label: "Structural & Development Context" }, // legacy slug
  cultural_heritage: { group: "H", label: "Structural & Development Context" }, // legacy slug
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// T13 #306 MEDIUM fix (2026-04-19): `getL1ForCategory` and `getDomainColor`
// were exported but had ZERO import sites — callers were reaching into
// CATEGORY_L1_MAP + L1_GROUPS directly. Removed to prevent accidental
// re-introduction of the duplicated lookup paths.

/** Get the L1Group definition by its code letter. */
export function getL1Group(code: string): L1Group | undefined {
  return L1_GROUPS.find((g) => g.code === code);
}
