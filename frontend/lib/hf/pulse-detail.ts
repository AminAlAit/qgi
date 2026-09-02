/**
 * hf/pulse-detail — server-side slicer for the news layer's deep data.
 *
 * data/hf-pulse-detail.json carries the FULL monthly pulse history
 * (2015->present) for every covered country x topic, plus the verified
 * event markers (elections from public calendars, conflict from UCDP,
 * economic from World Bank/IMF series). ~380KB: this module is imported
 * ONLY by server components (country page, live-pulse page), which slice
 * out one country's series before anything crosses to the client.
 */

// Build-time guard (PR #179 review): this module carries the ~380KB full
// history file and must never reach a client bundle. Importing it from a
// "use client" module now fails the build instead of silently shipping it.
import "server-only";

import detail from "@/data/hf-pulse-detail.json";
import {
  getHfBoard,
  type HfCell,
  type HfTopic,
  type HfVerdict,
} from "@/lib/hf/topics-data";
import {
  getTrendPulse,
  getTrendPulseSeries,
  isPulseOnly,
  PER_TREND_SLUGS,
  TREND_PULSE_MONTHS,
} from "@/lib/hf/trend-pulse";
import { getRecipeFullScoreMap } from "@/lib/te-mock/risk-board-data";
import { getRecipe } from "@/lib/te-mock/recipes";
import { primaryThemeFor } from "@/lib/hf/trend-signal";

export interface HfEventMarker {
  date: string; // YYYY-MM
  label: string;
}

export interface HfTopicSeries {
  topic: HfTopic;
  cell: HfCell | null;
  months: string[];
  pulse: number[];
  events: HfEventMarker[];
}

export interface HfCountryDetail {
  name: string;
  iso3: string;
  built: string;
  vintage: string;
  thresholds: { struct: number; pulse: number };
  verdicts: ReturnType<typeof getHfBoard>["verdicts"];
  /** Board topics first (founder-ratified six), then the rest. */
  series: HfTopicSeries[];
}

const raw = detail as unknown as {
  built: string;
  history: Record<string, { months: string[]; pulse: number[] }>;
  events: Record<string, Array<{ date: string; label: string }>>;
};

/** Full news-layer detail for one country, or null when not covered. */
export function getHfCountryDetail(iso3Upper: string): HfCountryDetail | null {
  const board = getHfBoard();
  const country = board.countries.find((c) => c.iso3 === iso3Upper.toUpperCase());
  if (!country) return null;

  const ordered = [
    ...board.topics.filter((t) => t.board),
    ...board.topics.filter((t) => !t.board),
  ];
  const series: HfTopicSeries[] = [];
  for (const topic of ordered) {
    const key = `${country.iso3}|${topic.id}`;
    const h = raw.history[key];
    if (!h) continue;
    series.push({
      topic,
      cell: board.cells[key] ?? null,
      months: h.months,
      pulse: h.pulse,
      // Belt against a bad bake: never let an unresolved Wikidata id render
      // as an event label (the generator already drops them).
      events: (raw.events[key] ?? []).filter((e) => !/^Q\d+$/.test(e.label)),
    });
  }
  if (series.length === 0) return null;

  // The heatmaps index every series positionally against series[0]'s month
  // axis. All bakes to date are aligned (one shared 2015->present axis); a
  // ragged future bake should degrade visibly, not silently shift cells.
  const axis = series[0];
  const aligned = series.filter(
    (s) =>
      s.months.length === axis.months.length &&
      s.months[0] === axis.months[0] &&
      s.months[s.months.length - 1] === axis.months[axis.months.length - 1]
  );
  if (aligned.length !== series.length) {
    console.warn(
      `hf/pulse-detail: dropped ${series.length - aligned.length} misaligned series for ${country.iso3}`
    );
  }

  return {
    name: country.name,
    iso3: country.iso3,
    built: raw.built,
    vintage: board.vintage,
    thresholds: board.thresholds,
    verdicts: board.verdicts,
    series: aligned,
  };
}

/** ISO3 (lowercase) list of covered countries — for generateStaticParams. */
export function hfCoveredIso3(): string[] {
  return getHfBoard().countries.map((c) => c.iso3.toLowerCase());
}

/* ── Per-Trend country panel data ────────────────────────────────────────── */

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

/**
 * Per-TREND country panel data: the 6 two-layer trends (each with its native
 * GDELT per-Trend news pulse) in place of the 14-Topic board. This is the
 * country-page counterpart to the per-Trend swap on /trends.
 *
 *  - labor_action / migration_and_refugees / political_corruption render
 *    NEWS-ONLY (struct = null): no structural line, verdict reads off the pulse.
 *  - Event markers are crosswalked from each trend's primary news theme — the
 *    per-Trend pulse file carries no events of its own.
 *  - Low-doc months (null pulse) render as 0 (lowest percentile) so the line and
 *    heatmap stay aligned to the shared 137-month axis.
 *
 * Descriptive only: the pulse is recall-validated, NOT a leading indicator.
 */
export function getTrendCountryPanelData(iso3Upper: string): HfCountryDetail | null {
  const board = getHfBoard();
  const country = board.countries.find((c) => c.iso3 === iso3Upper.toUpperCase());
  if (!country) return null;

  const series: HfTopicSeries[] = [];
  for (const slug of PER_TREND_SLUGS) {
    const rawPulse = getTrendPulseSeries(country.iso3, slug);
    if (!rawPulse) continue; // country absent for this trend
    const pulseNow = getTrendPulse(country.iso3, slug);
    if (pulseNow == null) continue; // no readable pulse at all

    const pulseOnly = isPulseOnly(slug);

    // Structural score, 0-100 (null for news-only trends).
    let struct: number | null = null;
    if (!pulseOnly) {
      const scores = getRecipeFullScoreMap(slug);
      const rawScore = scores ? scores[country.name] : undefined;
      if (typeof rawScore === "number") {
        const maxScore = Math.max(...Object.values(scores));
        const scale = maxScore <= 1.5 ? 100 : 1;
        struct = Math.round(rawScore * scale * 10) / 10;
      }
    }

    // Events crosswalked from the trend's primary news theme.
    const primary = primaryThemeFor(slug);
    const events = primary
      ? (raw.events[`${country.iso3}|${primary.id}`] ?? []).filter(
          (e) => !/^Q\d+$/.test(e.label)
        )
      : [];

    const label = getRecipe(slug)?.label ?? slug;
    const topic: HfTopic = {
      id: slug,
      label,
      name: label,
      scope: primary?.scope ?? "",
      validated: primary?.validated ?? false,
      board: true,
      trends: [slug],
    };

    const cell: HfCell = {
      struct,
      pulse: pulseNow,
      prevPulse: null,
      verdict: trendVerdict(struct, pulseNow, board.thresholds),
    };

    series.push({
      topic,
      cell,
      months: TREND_PULSE_MONTHS,
      pulse: rawPulse.map((p) => (p == null ? 0 : p)),
      events,
    });
  }
  if (series.length === 0) return null;

  // News-only trends sort after fused ones; then strongest combined reading.
  series.sort((a, b) => {
    const leg = (s: HfTopicSeries) =>
      s.cell && s.cell.struct != null
        ? Math.min(s.cell.struct, s.cell.pulse)
        : -1 + (s.cell ? s.cell.pulse / 1000 : 0);
    return leg(b) - leg(a);
  });

  return {
    name: country.name,
    iso3: country.iso3,
    built: raw.built,
    vintage: board.vintage,
    thresholds: board.thresholds,
    verdicts: board.verdicts,
    series,
  };
}

/**
 * Country-page slice: the six board topics, FULL monthly history (2015->now).
 *
 * The profile "News signals" chart defaults to the last 12 months and the
 * reader scrolls back through earlier years (Surface-A redesign 2026-06-13),
 * so it needs the whole series, not a 36-month trim. TopicDriftPanel's
 * stacked share-of-attention view is also full history (default window last
 * ~24 months). Payload stays ~tens of KB (6 topics x ~140 months).
 */
export function getHfCountryPanelData(iso3Upper: string): HfCountryDetail | null {
  const d = getHfCountryDetail(iso3Upper);
  if (!d) return null;
  const series = d.series.filter((s) => s.topic.board);
  // No board coverage -> no panels (never render empty frames).
  if (series.length === 0) return null;
  return { ...d, series };
}
