/**
 * hf/trend-pulse: the PER-TREND news layer.
 *
 * Native GDELT news pulse for the 6 two-layer trends, replacing the old
 * 14-Topic crosswalk as the pulse source for those trends.
 *
 * Data: data/hf-trend-pulse.json
 *   history["ISO3|trend_slug"].pulse = (number|null)[]: 137 months
 *       (2015-02 .. 2026-06), 0-100 GLOBAL cross-country × cross-time
 *       percentile rank per trend; null where a country-month had < min_docs
 *       (20) total docs.
 *   months  = string[]: 137 "YYYY-MM" labels.
 *   trends  = { slug: { domain, role } }: the 6 covered trends.
 *
 * Normalization differs from the Topic model (which is a within-country
 * z-score over broad CAMEO): per-Trend is a GLOBAL percentile, so the numbers
 * are NOT comparable to the old topic pulse. That is by design, not a bug.
 *
 * Phase B lead-lag verdict was INCONCLUSIVE: this layer is DESCRIPTIVE
 * (recall-validated, it fires at known events), NOT a leading indicator.
 * No forecast / "leads" / "early warning" wording anywhere downstream.
 *
 * Server-side only; pages slice and pass props.
 */

import trendPulse from "@/data/hf-trend-pulse.json";
import { NEWS_ONLY_TRENDS } from "@/lib/hf/trend-taxonomy";

export const TREND_PULSE_VINTAGE = trendPulse.vintage; // "trend-pulse-v1"
export const TREND_PULSE_DATA_END = trendPulse.data_end; // "2026-06"
export const TREND_PULSE_MONTHS = trendPulse.months as string[];

type TrendHistory = Record<string, { pulse: (number | null)[] }>;
const HISTORY = trendPulse.history as TrendHistory;
const TRENDS = trendPulse.trends as Record<string, { domain: string; role: string }>;

/** The 6 trend slugs that carry a native per-Trend news pulse. */
export const PER_TREND_SLUGS = Object.keys(TRENDS);

/**
 * News-only trends: render with NO structural line/axis/bar and NO fused
 * struct·pulse verdict: a "News only" badge instead.
 *   - labor_action: its structural CV-AUC is at chance, so a structural score
 *     would be misleading. HARD-GATED to null everywhere (mandate §0).
 * Sourced from NEWS_ONLY_TRENDS in trend-taxonomy.ts (single source of truth
 * for the Topics->Trends migration, founder 2026-07-04): migration_and_refugees
 * and political_corruption now render FULL two-layer, since they carry both a
 * native news feed and a structural score.
 */

/** True when the trend has a native per-Trend news pulse (one of the 6). */
export function isPerTrend(slug: string): boolean {
  return Object.prototype.hasOwnProperty.call(TRENDS, slug);
}

/** True when the trend must render news-only (no structural axis/line/verdict). */
export function isPulseOnly(slug: string): boolean {
  return NEWS_ONLY_TRENDS.has(slug);
}

/** The full monthly pulse series for a (country, trend), or null if absent. */
export function getTrendPulseSeries(
  iso3: string,
  slug: string
): (number | null)[] | null {
  const e = HISTORY[`${iso3}|${slug}`];
  return e ? e.pulse : null;
}

/**
 * The current per-Trend news pulse for a (country, trend): the most recent
 * month with a non-null reading. Returns null when the trend has no native
 * pulse, the country is absent, or every month was below min_docs.
 */
export function getTrendPulse(iso3: string, slug: string): number | null {
  const series = getTrendPulseSeries(iso3, slug);
  if (!series) return null;
  for (let i = series.length - 1; i >= 0; i--) {
    const v = series[i];
    if (typeof v === "number") return v;
  }
  return null;
}
