/**
 * hf/trend-taxonomy — single source of truth for the news-layer Trend taxonomy
 * after the Topics->Trends migration (founder 2026-07-04).
 *
 * The whole site now speaks "Trends" for news. Only 6 trends have a native
 * GDELT news feed ("news pressure", 0-100). A curated set of high-salience
 * trends render as elegant "coming soon" placeholders on the board until their
 * feeds are built. Everything else has no news surface.
 *
 * Client-safe: no heavy imports (never pulls the per-Trend pulse JSON).
 */

/** The 6 trends with a native per-Trend GDELT news feed (real news pressure). */
export const LIVE_NEWS_TRENDS = [
  "currency_crisis",
  "mass_protest",
  "migration_and_refugees",
  "elections_and_voting",
  "political_corruption",
  "labor_action",
] as const;

/**
 * Curated "coming soon" columns on the migrated board: high-salience trends we
 * will build native feeds for later. No values yet — rendered as elegant
 * placeholders (see the board component). Expandable.
 */
export const COMING_SOON_TREND_COLUMNS: { slug: string; label: string }[] = [
  { slug: "civil_war_and_insurgency", label: "Conflict" },
  { slug: "terrorist_attack", label: "Terrorism" },
  { slug: "diplomatic_rupture", label: "Diplomacy" },
];

/**
 * The news themes QGI does NOT yet cover as a live Trend. Shown as one honest
 * "coverage roadmap" note on the board (founder 2026-07-06) — replaces the old
 * teaser placeholder columns. Broader than COMING_SOON_TREND_COLUMNS (which only
 * carries the 3 themes that already have a slug). No forecast, no dates.
 */
export const COVERAGE_ROADMAP_THEMES: string[] = [
  "Armed conflict",
  "Terrorism",
  "Repression & human rights",
  "Trade & sanctions",
  "Diplomacy",
  "Energy & resources",
  "Cyber & technology",
];

/**
 * Trends shown NEWS-ONLY (a news feed but no structural line). EMPTY now:
 * labor_action was promoted to FULL two-layer (founder 2026-07-05) because its
 * structural resemblance score is already shown in the Countries panel, so
 * hiding it in the News Pulse panel while ranking by it next door was inconsistent.
 * Kept as a Set so the mechanism survives if a future trend ever needs it.
 */
export const NEWS_ONLY_TRENDS = new Set<string>([]);

const LIVE = new Set<string>(LIVE_NEWS_TRENDS);

/** 'live' = has a native news feed; 'coming_soon' = no native feed yet. */
export function trendNewsStatus(slug: string): "live" | "coming_soon" {
  return LIVE.has(slug) ? "live" : "coming_soon";
}

/** Human label for a trend slug, e.g. currency_crisis -> "Currency Crisis". */
export function trendLabel(slug: string): string {
  return slug
    .replace(/_and_/g, " & ")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** The single scale label used everywhere now (Topics->Trends unified the scale). */
export const NEWS_PRESSURE_LABEL =
  "News pressure is a 0 to 100 reading of how much of a country's news runs on this trend, ranked across all covered countries and months.";
