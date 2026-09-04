/**
 * hf/news-scale: shared labels for the news layer's TWO normalizations, and the
 * Topic→Trend crosswalk reveal.
 *
 * QGI shows two different 0-100 "news pulse" scales and they must never be
 * silently confused (Majles 2026-06-28):
 *   - Topic surfaces (risk-board, dashboard, live-pulse): a WITHIN-COUNTRY
 *     z-score, 50 is that country's own normal month.
 *   - Per-Trend surfaces (/trends, /countries): a GLOBAL percentile across all
 *     countries and months, 50 is the global median for that trend.
 *
 * Client-safe: hardcodes the 6 per-Trend slugs rather than importing the
 * per-Trend pulse JSON (which would bundle ~450KB into client components).
 */

/** Visible caption for Topic surfaces (within-country z-score). */
export const WITHIN_COUNTRY_NOTE =
  "News pulse is scaled to each country's own baseline: 50 is its normal month.";

/**
 * Visible caption for per-Trend surfaces. Unified scale (Topics->Trends
 * migration, founder 2026-07-04): the whole site now uses ONE "news pressure"
 * scale (0-100, global percentile across all covered countries and months).
 */
export const GLOBAL_PERCENTILE_NOTE =
  "News pressure is a 0 to 100 reading, ranked across all covered countries and months (50 is the median for this trend).";

/** The 6 trends that carry a native per-Trend news pulse (mirror of PER_TREND_SLUGS
 *  in lib/hf/trend-pulse.ts; hardcoded here to keep this module client-safe). */
const PER_TREND_PULSE_SLUGS = new Set<string>([
  "currency_crisis",
  "mass_protest",
  "migration_and_refugees",
  "elections_and_voting",
  "political_corruption",
  "labor_action",
]);

export interface MappedTrend {
  slug: string;
  label: string;
  /** True when this trend has a native per-Trend news pulse (one of the 6). */
  hasPulse: boolean;
}

function humanizeSlug(slug: string): string {
  return slug
    .replace(/_and_/g, " & ")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * The Trends a news Topic crosswalks to, each flagged by whether it has a
 * native per-Trend news pulse (so the reveal never implies more coverage than
 * exists (Marcus's caveat, Majles 2026-06-28).
 */
export function topicTrendMapping(trendSlugs: string[]): MappedTrend[] {
  return trendSlugs.map((slug) => ({
    slug,
    label: humanizeSlug(slug),
    hasPulse: PER_TREND_PULSE_SLUGS.has(slug),
  }));
}

/** A compact one-line "maps to" string for tooltips, e.g.
 *  "Maps to trends: Currency Crisis (pulse), Banking & Financial Crisis (structural only)". */
export function topicTrendMappingText(trendSlugs: string[]): string {
  const mapped = topicTrendMapping(trendSlugs);
  if (mapped.length === 0) return "";
  const parts = mapped.map(
    (m) => `${m.label} (${m.hasPulse ? "news pulse" : "no per-Trend pulse"})`
  );
  return `Maps to ${mapped.length === 1 ? "trend" : "trends"}: ${parts.join(", ")}.`;
}
