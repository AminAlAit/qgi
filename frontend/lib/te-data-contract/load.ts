/**
 * TE fleet-run-2 loader module.
 *
 * Provides typed access to every file in `data/te-fleet-run-2/`.
 * JSON imports are resolved at build-time by Next.js (resolveJsonModule: true).
 *
 * Runtime sanity checks: each loader verifies the shape is non-empty and
 * throws a contract-drift error rather than silently returning garbage data.
 *
 * The 44 fleet-run-2 recipe IDs are enumerated in FLEET_RUN_2_RECIPE_IDS.
 * data/te-sample-10/ stays on disk for back-compat but is no longer imported.
 */

import type { CardV3 } from "./card-v3";
import type { RecipeScoresFile } from "./scores";
import type { CountryIndex } from "./country-index";
import type { CurrentStateAnalogs } from "./analogs";
import type { ProgramFeed } from "./activity-feed";

// ─── Static JSON imports — each resolved at build time ─────────────────────
// Cards v3 — 44 recipes
import rawCard_agricultural_policy from "@/data/te-fleet-run-2/cards-v3/agricultural_policy.card.json";
import rawCard_banking_and_financial_crisis from "@/data/te-fleet-run-2/cards-v3/banking_and_financial_crisis.card.json";
import rawCard_bilateral_treaty from "@/data/te-fleet-run-2/cards-v3/bilateral_treaty.card.json";
import rawCard_civil_war_and_insurgency from "@/data/te-fleet-run-2/cards-v3/civil_war_and_insurgency.card.json";
import rawCard_constitutional_change from "@/data/te-fleet-run-2/cards-v3/constitutional_change.card.json";
import rawCard_currency_crisis from "@/data/te-fleet-run-2/cards-v3/currency_crisis.card.json";
import rawCard_democratic_transition from "@/data/te-fleet-run-2/cards-v3/democratic_transition.card.json";
import rawCard_diplomatic_rupture from "@/data/te-fleet-run-2/cards-v3/diplomatic_rupture.card.json";
import rawCard_economic_growth_milestone from "@/data/te-fleet-run-2/cards-v3/economic_growth_milestone.card.json";
import rawCard_economic_liberalization from "@/data/te-fleet-run-2/cards-v3/economic_liberalization.card.json";
import rawCard_economic_nationalization from "@/data/te-fleet-run-2/cards-v3/economic_nationalization.card.json";
import rawCard_economic_recession from "@/data/te-fleet-run-2/cards-v3/economic_recession.card.json";
import rawCard_elections_and_voting from "@/data/te-fleet-run-2/cards-v3/elections_and_voting.card.json";
import rawCard_energy_policy from "@/data/te-fleet-run-2/cards-v3/energy_policy.card.json";
import rawCard_epidemic_and_pandemic from "@/data/te-fleet-run-2/cards-v3/epidemic_and_pandemic.card.json";
import rawCard_ethnic_and_communal_conflict from "@/data/te-fleet-run-2/cards-v3/ethnic_and_communal_conflict.card.json";
import rawCard_executive_power_consolidation from "@/data/te-fleet-run-2/cards-v3/executive_power_consolidation.card.json";
import rawCard_fiscal_policy_change from "@/data/te-fleet-run-2/cards-v3/fiscal_policy_change.card.json";
import rawCard_foreign_intervention from "@/data/te-fleet-run-2/cards-v3/foreign_intervention.card.json";
import rawCard_government_formation from "@/data/te-fleet-run-2/cards-v3/government_formation.card.json";
import rawCard_human_rights_reform from "@/data/te-fleet-run-2/cards-v3/human_rights_reform.card.json";
import rawCard_human_rights_violation from "@/data/te-fleet-run-2/cards-v3/human_rights_violation.card.json";
import rawCard_infrastructure_project from "@/data/te-fleet-run-2/cards-v3/infrastructure_project.card.json";
import rawCard_interstate_war from "@/data/te-fleet-run-2/cards-v3/interstate_war.card.json";
import rawCard_labor_action from "@/data/te-fleet-run-2/cards-v3/labor_action.card.json";
import rawCard_mass_protest from "@/data/te-fleet-run-2/cards-v3/mass_protest.card.json";
import rawCard_migration_and_refugees from "@/data/te-fleet-run-2/cards-v3/migration_and_refugees.card.json";
import rawCard_military_coup from "@/data/te-fleet-run-2/cards-v3/military_coup.card.json";
import rawCard_military_policy_and_reform from "@/data/te-fleet-run-2/cards-v3/military_policy_and_reform.card.json";
import rawCard_monetary_policy_change from "@/data/te-fleet-run-2/cards-v3/monetary_policy_change.card.json";
import rawCard_multilateral_agreement from "@/data/te-fleet-run-2/cards-v3/multilateral_agreement.card.json";
import rawCard_natural_disaster from "@/data/te-fleet-run-2/cards-v3/natural_disaster.card.json";
import rawCard_peacekeeping_and_peace_process from "@/data/te-fleet-run-2/cards-v3/peacekeeping_and_peace_process.card.json";
import rawCard_political_corruption from "@/data/te-fleet-run-2/cards-v3/political_corruption.card.json";
import rawCard_political_repression from "@/data/te-fleet-run-2/cards-v3/political_repression.card.json";
import rawCard_political_violence from "@/data/te-fleet-run-2/cards-v3/political_violence.card.json";
import rawCard_regional_integration from "@/data/te-fleet-run-2/cards-v3/regional_integration.card.json";
import rawCard_religious_and_social_movement from "@/data/te-fleet-run-2/cards-v3/religious_and_social_movement.card.json";
import rawCard_sanctions_and_arms_embargo from "@/data/te-fleet-run-2/cards-v3/sanctions_and_arms_embargo.card.json";
import rawCard_technology_breakthrough from "@/data/te-fleet-run-2/cards-v3/technology_breakthrough.card.json";
import rawCard_territorial_disputes from "@/data/te-fleet-run-2/cards-v3/territorial_disputes.card.json";
import rawCard_terrorist_attack from "@/data/te-fleet-run-2/cards-v3/terrorist_attack.card.json";
import rawCard_trade_agreement from "@/data/te-fleet-run-2/cards-v3/trade_agreement.card.json";
import rawCard_transitional_justice from "@/data/te-fleet-run-2/cards-v3/transitional_justice.card.json";

// Scores — 44 recipes
import rawScores_agricultural_policy from "@/data/te-fleet-run-2/scores/agricultural_policy.scores.json";
import rawScores_banking_and_financial_crisis from "@/data/te-fleet-run-2/scores/banking_and_financial_crisis.scores.json";
import rawScores_bilateral_treaty from "@/data/te-fleet-run-2/scores/bilateral_treaty.scores.json";
import rawScores_civil_war_and_insurgency from "@/data/te-fleet-run-2/scores/civil_war_and_insurgency.scores.json";
import rawScores_constitutional_change from "@/data/te-fleet-run-2/scores/constitutional_change.scores.json";
import rawScores_currency_crisis from "@/data/te-fleet-run-2/scores/currency_crisis.scores.json";
import rawScores_democratic_transition from "@/data/te-fleet-run-2/scores/democratic_transition.scores.json";
import rawScores_diplomatic_rupture from "@/data/te-fleet-run-2/scores/diplomatic_rupture.scores.json";
import rawScores_economic_growth_milestone from "@/data/te-fleet-run-2/scores/economic_growth_milestone.scores.json";
import rawScores_economic_liberalization from "@/data/te-fleet-run-2/scores/economic_liberalization.scores.json";
import rawScores_economic_nationalization from "@/data/te-fleet-run-2/scores/economic_nationalization.scores.json";
import rawScores_economic_recession from "@/data/te-fleet-run-2/scores/economic_recession.scores.json";
import rawScores_elections_and_voting from "@/data/te-fleet-run-2/scores/elections_and_voting.scores.json";
import rawScores_energy_policy from "@/data/te-fleet-run-2/scores/energy_policy.scores.json";
import rawScores_epidemic_and_pandemic from "@/data/te-fleet-run-2/scores/epidemic_and_pandemic.scores.json";
import rawScores_ethnic_and_communal_conflict from "@/data/te-fleet-run-2/scores/ethnic_and_communal_conflict.scores.json";
import rawScores_executive_power_consolidation from "@/data/te-fleet-run-2/scores/executive_power_consolidation.scores.json";
import rawScores_fiscal_policy_change from "@/data/te-fleet-run-2/scores/fiscal_policy_change.scores.json";
import rawScores_foreign_intervention from "@/data/te-fleet-run-2/scores/foreign_intervention.scores.json";
import rawScores_government_formation from "@/data/te-fleet-run-2/scores/government_formation.scores.json";
import rawScores_human_rights_reform from "@/data/te-fleet-run-2/scores/human_rights_reform.scores.json";
import rawScores_human_rights_violation from "@/data/te-fleet-run-2/scores/human_rights_violation.scores.json";
import rawScores_infrastructure_project from "@/data/te-fleet-run-2/scores/infrastructure_project.scores.json";
import rawScores_interstate_war from "@/data/te-fleet-run-2/scores/interstate_war.scores.json";
import rawScores_labor_action from "@/data/te-fleet-run-2/scores/labor_action.scores.json";
import rawScores_mass_protest from "@/data/te-fleet-run-2/scores/mass_protest.scores.json";
import rawScores_migration_and_refugees from "@/data/te-fleet-run-2/scores/migration_and_refugees.scores.json";
import rawScores_military_coup from "@/data/te-fleet-run-2/scores/military_coup.scores.json";
import rawScores_military_policy_and_reform from "@/data/te-fleet-run-2/scores/military_policy_and_reform.scores.json";
import rawScores_monetary_policy_change from "@/data/te-fleet-run-2/scores/monetary_policy_change.scores.json";
import rawScores_multilateral_agreement from "@/data/te-fleet-run-2/scores/multilateral_agreement.scores.json";
import rawScores_natural_disaster from "@/data/te-fleet-run-2/scores/natural_disaster.scores.json";
import rawScores_peacekeeping_and_peace_process from "@/data/te-fleet-run-2/scores/peacekeeping_and_peace_process.scores.json";
import rawScores_political_corruption from "@/data/te-fleet-run-2/scores/political_corruption.scores.json";
import rawScores_political_repression from "@/data/te-fleet-run-2/scores/political_repression.scores.json";
import rawScores_political_violence from "@/data/te-fleet-run-2/scores/political_violence.scores.json";
import rawScores_regional_integration from "@/data/te-fleet-run-2/scores/regional_integration.scores.json";
import rawScores_religious_and_social_movement from "@/data/te-fleet-run-2/scores/religious_and_social_movement.scores.json";
import rawScores_sanctions_and_arms_embargo from "@/data/te-fleet-run-2/scores/sanctions_and_arms_embargo.scores.json";
import rawScores_technology_breakthrough from "@/data/te-fleet-run-2/scores/technology_breakthrough.scores.json";
import rawScores_territorial_disputes from "@/data/te-fleet-run-2/scores/territorial_disputes.scores.json";
import rawScores_terrorist_attack from "@/data/te-fleet-run-2/scores/terrorist_attack.scores.json";
import rawScores_trade_agreement from "@/data/te-fleet-run-2/scores/trade_agreement.scores.json";
import rawScores_transitional_justice from "@/data/te-fleet-run-2/scores/transitional_justice.scores.json";

// Reference files
import rawCountryIndex from "@/data/te-fleet-run-2/countries/country-index.json";
import rawRankHistory from "@/data/te-fleet-run-2/countries/country-rank-history.json";
import rawAnalogs from "@/data/te-fleet-run-2/analogs/current-state-analogs.json";
import rawActivityFeed from "@/data/te-fleet-run-2/activity/program-feed.json";
import rawManifest from "@/data/te-fleet-run-2/MANIFEST.json";

// ─── Type assertions ─────────────────────────────────────────────────────────
// JSON imports come in as `unknown`-like — we assert to the contract types.
// The sanity checks below validate the shape at runtime.

const CARD_MAP: Record<string, CardV3> = {
  agricultural_policy: rawCard_agricultural_policy as unknown as CardV3,
  banking_and_financial_crisis: rawCard_banking_and_financial_crisis as unknown as CardV3,
  bilateral_treaty: rawCard_bilateral_treaty as unknown as CardV3,
  civil_war_and_insurgency: rawCard_civil_war_and_insurgency as unknown as CardV3,
  constitutional_change: rawCard_constitutional_change as unknown as CardV3,
  currency_crisis: rawCard_currency_crisis as unknown as CardV3,
  democratic_transition: rawCard_democratic_transition as unknown as CardV3,
  diplomatic_rupture: rawCard_diplomatic_rupture as unknown as CardV3,
  economic_growth_milestone: rawCard_economic_growth_milestone as unknown as CardV3,
  economic_liberalization: rawCard_economic_liberalization as unknown as CardV3,
  economic_nationalization: rawCard_economic_nationalization as unknown as CardV3,
  economic_recession: rawCard_economic_recession as unknown as CardV3,
  elections_and_voting: rawCard_elections_and_voting as unknown as CardV3,
  energy_policy: rawCard_energy_policy as unknown as CardV3,
  epidemic_and_pandemic: rawCard_epidemic_and_pandemic as unknown as CardV3,
  ethnic_and_communal_conflict: rawCard_ethnic_and_communal_conflict as unknown as CardV3,
  executive_power_consolidation:
    rawCard_executive_power_consolidation as unknown as CardV3,
  fiscal_policy_change: rawCard_fiscal_policy_change as unknown as CardV3,
  foreign_intervention: rawCard_foreign_intervention as unknown as CardV3,
  government_formation: rawCard_government_formation as unknown as CardV3,
  human_rights_reform: rawCard_human_rights_reform as unknown as CardV3,
  human_rights_violation: rawCard_human_rights_violation as unknown as CardV3,
  infrastructure_project: rawCard_infrastructure_project as unknown as CardV3,
  interstate_war: rawCard_interstate_war as unknown as CardV3,
  labor_action: rawCard_labor_action as unknown as CardV3,
  mass_protest: rawCard_mass_protest as unknown as CardV3,
  migration_and_refugees: rawCard_migration_and_refugees as unknown as CardV3,
  military_coup: rawCard_military_coup as unknown as CardV3,
  military_policy_and_reform: rawCard_military_policy_and_reform as unknown as CardV3,
  monetary_policy_change: rawCard_monetary_policy_change as unknown as CardV3,
  multilateral_agreement: rawCard_multilateral_agreement as unknown as CardV3,
  natural_disaster: rawCard_natural_disaster as unknown as CardV3,
  peacekeeping_and_peace_process:
    rawCard_peacekeeping_and_peace_process as unknown as CardV3,
  political_corruption: rawCard_political_corruption as unknown as CardV3,
  political_repression: rawCard_political_repression as unknown as CardV3,
  political_violence: rawCard_political_violence as unknown as CardV3,
  regional_integration: rawCard_regional_integration as unknown as CardV3,
  religious_and_social_movement:
    rawCard_religious_and_social_movement as unknown as CardV3,
  sanctions_and_arms_embargo: rawCard_sanctions_and_arms_embargo as unknown as CardV3,
  technology_breakthrough: rawCard_technology_breakthrough as unknown as CardV3,
  territorial_disputes: rawCard_territorial_disputes as unknown as CardV3,
  terrorist_attack: rawCard_terrorist_attack as unknown as CardV3,
  trade_agreement: rawCard_trade_agreement as unknown as CardV3,
  transitional_justice: rawCard_transitional_justice as unknown as CardV3,
};

const SCORES_MAP: Record<string, RecipeScoresFile> = {
  agricultural_policy: rawScores_agricultural_policy as unknown as RecipeScoresFile,
  banking_and_financial_crisis:
    rawScores_banking_and_financial_crisis as unknown as RecipeScoresFile,
  bilateral_treaty: rawScores_bilateral_treaty as unknown as RecipeScoresFile,
  civil_war_and_insurgency:
    rawScores_civil_war_and_insurgency as unknown as RecipeScoresFile,
  constitutional_change: rawScores_constitutional_change as unknown as RecipeScoresFile,
  currency_crisis: rawScores_currency_crisis as unknown as RecipeScoresFile,
  democratic_transition: rawScores_democratic_transition as unknown as RecipeScoresFile,
  diplomatic_rupture: rawScores_diplomatic_rupture as unknown as RecipeScoresFile,
  economic_growth_milestone:
    rawScores_economic_growth_milestone as unknown as RecipeScoresFile,
  economic_liberalization:
    rawScores_economic_liberalization as unknown as RecipeScoresFile,
  economic_nationalization:
    rawScores_economic_nationalization as unknown as RecipeScoresFile,
  economic_recession: rawScores_economic_recession as unknown as RecipeScoresFile,
  elections_and_voting: rawScores_elections_and_voting as unknown as RecipeScoresFile,
  energy_policy: rawScores_energy_policy as unknown as RecipeScoresFile,
  epidemic_and_pandemic: rawScores_epidemic_and_pandemic as unknown as RecipeScoresFile,
  ethnic_and_communal_conflict:
    rawScores_ethnic_and_communal_conflict as unknown as RecipeScoresFile,
  executive_power_consolidation:
    rawScores_executive_power_consolidation as unknown as RecipeScoresFile,
  fiscal_policy_change: rawScores_fiscal_policy_change as unknown as RecipeScoresFile,
  foreign_intervention: rawScores_foreign_intervention as unknown as RecipeScoresFile,
  government_formation: rawScores_government_formation as unknown as RecipeScoresFile,
  human_rights_reform: rawScores_human_rights_reform as unknown as RecipeScoresFile,
  human_rights_violation: rawScores_human_rights_violation as unknown as RecipeScoresFile,
  infrastructure_project: rawScores_infrastructure_project as unknown as RecipeScoresFile,
  interstate_war: rawScores_interstate_war as unknown as RecipeScoresFile,
  labor_action: rawScores_labor_action as unknown as RecipeScoresFile,
  mass_protest: rawScores_mass_protest as unknown as RecipeScoresFile,
  migration_and_refugees: rawScores_migration_and_refugees as unknown as RecipeScoresFile,
  military_coup: rawScores_military_coup as unknown as RecipeScoresFile,
  military_policy_and_reform:
    rawScores_military_policy_and_reform as unknown as RecipeScoresFile,
  monetary_policy_change: rawScores_monetary_policy_change as unknown as RecipeScoresFile,
  multilateral_agreement: rawScores_multilateral_agreement as unknown as RecipeScoresFile,
  natural_disaster: rawScores_natural_disaster as unknown as RecipeScoresFile,
  peacekeeping_and_peace_process:
    rawScores_peacekeeping_and_peace_process as unknown as RecipeScoresFile,
  political_corruption: rawScores_political_corruption as unknown as RecipeScoresFile,
  political_repression: rawScores_political_repression as unknown as RecipeScoresFile,
  political_violence: rawScores_political_violence as unknown as RecipeScoresFile,
  regional_integration: rawScores_regional_integration as unknown as RecipeScoresFile,
  religious_and_social_movement:
    rawScores_religious_and_social_movement as unknown as RecipeScoresFile,
  sanctions_and_arms_embargo:
    rawScores_sanctions_and_arms_embargo as unknown as RecipeScoresFile,
  technology_breakthrough:
    rawScores_technology_breakthrough as unknown as RecipeScoresFile,
  territorial_disputes: rawScores_territorial_disputes as unknown as RecipeScoresFile,
  terrorist_attack: rawScores_terrorist_attack as unknown as RecipeScoresFile,
  trade_agreement: rawScores_trade_agreement as unknown as RecipeScoresFile,
  transitional_justice: rawScores_transitional_justice as unknown as RecipeScoresFile,
};

// ─── Sanity check helpers ─────────────────────────────────────────────────────

function assertNonEmpty(val: unknown, ctx: string): void {
  if (typeof val !== "object" || val === null) {
    throw new Error(`contract drift: ${ctx} is not an object`);
  }
}

function assertArrayNonEmpty(arr: unknown[], ctx: string): void {
  if (!Array.isArray(arr) || arr.length === 0) {
    throw new Error(`contract drift: ${ctx} is empty or not an array`);
  }
}

// ─── Public loaders ───────────────────────────────────────────────────────────

/**
 * Load a single card by recipe_id.
 * Throws if the recipe_id is not in the fleet-run-2 set.
 */
export function loadCardV3(recipeId: string): CardV3 {
  const card = CARD_MAP[recipeId];
  if (!card) {
    throw new Error(`contract drift: no card for recipe_id "${recipeId}" in fleet-run-2`);
  }
  assertNonEmpty(card, `card[${recipeId}]`);
  assertNonEmpty(card.greedy_walk, `card[${recipeId}].greedy_walk`);
  return card;
}

/**
 * Load per-country scores for a recipe.
 * Throws if the recipe_id is not in the fleet-run-2 set.
 */
export function loadScores(recipeId: string): RecipeScoresFile {
  const scores = SCORES_MAP[recipeId];
  if (!scores) {
    throw new Error(
      `contract drift: no scores for recipe_id "${recipeId}" in fleet-run-2`
    );
  }
  assertNonEmpty(scores, `scores[${recipeId}]`);
  assertArrayNonEmpty(scores.scores, `scores[${recipeId}].scores`);
  return scores;
}

/** Load the country index. */
export function loadCountryIndex(): CountryIndex {
  const idx = rawCountryIndex as unknown as CountryIndex;
  assertNonEmpty(idx, "country-index");
  assertArrayNonEmpty(idx.countries, "country-index.countries");
  return idx;
}

/** Load the current-state analogs. */
export function loadAnalogs(): CurrentStateAnalogs {
  const data = rawAnalogs as unknown as CurrentStateAnalogs;
  assertNonEmpty(data, "analogs");
  assertArrayNonEmpty(data.entries, "analogs.entries");
  return data;
}

/** Load the program activity feed. */
export function loadActivityFeed(): ProgramFeed {
  const feed = rawActivityFeed as unknown as ProgramFeed;
  assertNonEmpty(feed, "activity-feed");
  assertArrayNonEmpty(feed.events, "activity-feed.events");
  return feed;
}

/** Load all 44 cards at once — returns the full map. */
export function loadAllCards(): Record<string, CardV3> {
  // Validate all cards are accessible
  for (const id of Object.keys(CARD_MAP)) {
    assertNonEmpty(CARD_MAP[id], `card[${id}]`);
  }
  return CARD_MAP;
}

/** Load all 44 scores files at once. */
export function loadAllScores(): Record<string, RecipeScoresFile> {
  for (const id of Object.keys(SCORES_MAP)) {
    assertNonEmpty(SCORES_MAP[id], `scores[${id}]`);
  }
  return SCORES_MAP;
}

/** A single row in the rank-history file. */
export interface RankHistoryRow {
  vintage: string;
  recipe_id: string;
  country: string;
  country_iso2: string;
  score: number;
  rank: number;
  n_countries_scored: number;
}

export interface RankHistoryFile {
  vintage: string;
  produced_at_utc: string;
  schema_note: string;
  n_rows: number;
  rows: RankHistoryRow[];
}

/**
 * Load the cross-vintage country rank history.
 * At fleet-run-2 this contains 7,577 rows (one per country × recipe that
 * was scored). Append-only: vintage 2 rows join by (recipe_id, country).
 */
export function loadRankHistory(): RankHistoryFile {
  const data = rawRankHistory as unknown as RankHistoryFile;
  assertNonEmpty(data, "rank-history");
  assertArrayNonEmpty(data.rows, "rank-history.rows");
  return data;
}

/** Vintage stamp from the MANIFEST. */
export function loadVintage(): string {
  return (rawManifest as { produced_at_utc: string }).produced_at_utc;
}

/** run_index from MANIFEST — increments per quarterly fleet run. */
export function loadRunIndex(): number {
  return (rawManifest as { run_index: number }).run_index;
}

/** indicator_catalog_size from MANIFEST. */
export function loadIndicatorCatalogSize(): number {
  return (rawManifest as { indicator_catalog_size: number }).indicator_catalog_size;
}

/** indicator_corpus_breakdown from MANIFEST: provider → count. */
export function loadIndicatorCorpusBreakdown(): Record<string, number> {
  return (rawManifest as { indicator_corpus_breakdown: Record<string, number> })
    .indicator_corpus_breakdown;
}

/** All 44 recipe IDs in the current vintage (te-fleet-run-2). */
export const FLEET_RUN_2_RECIPE_IDS = Object.keys(CARD_MAP) as string[];

/**
 * @deprecated Use FLEET_RUN_2_RECIPE_IDS. Aliases kept so existing consumers
 * (risk-board-data.ts, countries-v4-data.ts, etc.) compile without a mass
 * rename in one shot.
 */
export const FLEET_RUN_1_RECIPE_IDS = FLEET_RUN_2_RECIPE_IDS;
export const SAMPLE_10_RECIPE_IDS = FLEET_RUN_2_RECIPE_IDS;
