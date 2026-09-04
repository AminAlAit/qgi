/**
 * hf/trend-board — the per-TREND board data source for /risk-board (and the
 * dashboard), replacing the 14-Topic getHfBoard() as the grid's primary feed
 * (Topics->Trends migration, founder-approved 2026-07-04).
 *
 * Columns are the 6 founder-ratified LIVE_NEWS_TRENDS (each with a native
 * GDELT per-Trend news feed) followed by the COMING_SOON_TREND_COLUMNS
 * placeholders (no cells yet — struct/pulse data doesn't exist for them).
 *
 * Cell logic mirrors getTrendCountryPanelData / trendVerdict in
 * lib/hf/pulse-detail.ts exactly:
 *   - struct is null for NEWS_ONLY_TRENDS (labor_action) — verdict reads off
 *     the pulse alone (SIGNAL/QUIET). All other live trends fuse struct+pulse
 *     into ACTIVE/SIGNAL/LATENT/QUIET at the 60/60 thresholds.
 *   - struct is the recipe discrimination score for the trend, scaled to
 *     0-100 (scores files are either already 0-100 or a 0-1 fraction).
 *
 * Shape-compatible with HfBoard (topics, boardTopics, cells, countries,
 * thresholds, verdicts, history) so existing consumers of that shape (e.g.
 * TopicBoard.tsx) keep compiling unchanged. `comingSoon` is additive.
 */

import "server-only";

import {
  getHfBoard,
  type HfBoard,
  type HfCell,
  type HfTopic,
  type HfVerdict,
} from "@/lib/hf/topics-data";
import {
  getTrendPulse,
  getTrendPulseSeries,
  TREND_PULSE_MONTHS,
} from "@/lib/hf/trend-pulse";
import { getRecipeFullScoreMap } from "@/lib/te-mock/risk-board-data";
import {
  COMING_SOON_TREND_COLUMNS,
  LIVE_NEWS_TRENDS,
  NEWS_ONLY_TRENDS,
  trendLabel,
} from "@/lib/hf/trend-taxonomy";

export interface TrendBoard extends HfBoard {
  /** Slugs of the curated "coming soon" columns — no cells/history yet. */
  comingSoon: string[];
}

/** Mirrors trendVerdict() in lib/hf/pulse-detail.ts exactly. */
function trendVerdict(
  struct: number | null,
  pulse: number,
  th: { struct: number; pulse: number }
): HfVerdict {
  const hiP = pulse >= th.pulse;
  if (struct == null) return hiP ? "SIGNAL" : "QUIET"; // news-only trends
  const hiS = struct >= th.struct;
  if (hiS && hiP) return "ACTIVE";
  if (!hiS && hiP) return "SIGNAL";
  if (hiS && !hiP) return "LATENT";
  return "QUIET";
}

let _cache: TrendBoard | null = null;

export function getTrendBoard(): TrendBoard {
  if (_cache) return _cache;

  const base = getHfBoard();

  const liveTopics: HfTopic[] = LIVE_NEWS_TRENDS.map((slug) => ({
    id: slug,
    label: trendLabel(slug),
    name: trendLabel(slug),
    scope: "",
    validated: false,
    board: true,
    trends: [slug],
  }));

  const comingSoonTopics: HfTopic[] = COMING_SOON_TREND_COLUMNS.map((c) => ({
    id: c.slug,
    label: c.label,
    name: c.label,
    scope: "",
    validated: false,
    board: true,
    trends: [c.slug],
  }));

  const topics: HfTopic[] = [...liveTopics, ...comingSoonTopics];

  const cells: Record<string, HfCell> = {};
  const history: Record<string, { months: string[]; pulse: number[] }> = {};

  for (const slug of LIVE_NEWS_TRENDS) {
    const pulseOnly = NEWS_ONLY_TRENDS.has(slug);
    // Hoisted per-slug (not per-country) — same recipe map reused for every
    // country, matching getRecipeFullScoreMap's per-recipe cost profile.
    const scores = pulseOnly ? null : getRecipeFullScoreMap(slug);
    const maxScore =
      scores && Object.keys(scores).length > 0
        ? Math.max(...Object.values(scores))
        : null;
    const scale = maxScore != null && maxScore <= 1.5 ? 100 : 1;

    for (const country of base.countries) {
      const key = `${country.iso3}|${slug}`;

      const series = getTrendPulseSeries(country.iso3, slug);
      if (series) {
        history[key] = {
          months: TREND_PULSE_MONTHS,
          pulse: series.map((p) => (p == null ? 0 : p)),
        };
      }

      const pulseNow = getTrendPulse(country.iso3, slug);
      if (pulseNow == null) continue; // skip: no readable pulse

      let struct: number | null = null;
      if (!pulseOnly && scores) {
        const rawScore = scores[country.name];
        if (typeof rawScore === "number") {
          struct = Math.round(rawScore * scale * 10) / 10;
        }
      }

      cells[key] = {
        struct,
        pulse: pulseNow,
        prevPulse: null,
        verdict: trendVerdict(struct, pulseNow, base.thresholds),
      };
    }
  }
  // NO cells/history for coming-soon trends — placeholders only.

  _cache = {
    built: base.built,
    vintage: base.vintage,
    thresholds: base.thresholds,
    verdicts: base.verdicts,
    topics,
    boardTopics: topics,
    countries: base.countries,
    cells,
    history,
    comingSoon: COMING_SOON_TREND_COLUMNS.map((c) => c.slug),
  };
  return _cache;
}
