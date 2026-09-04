/**
 * Indicator panels — per-country, per-driver-indicator yearly values.
 *
 * Source: `data/te-fleet-run-2/indicator-panels.json`, baked from the qgi-ml
 * panels (`qgi-ml/data/…parquet`) and **restricted to the indicators that appear
 * as drivers** — i.e. the union of `greedy_walk.selected_indicators` across the
 * 44 run-2 trends (62 indicators at run-2). No other indicator is ever surfaced
 * (every trend page, match page, and analogue page only shows a trend's drivers),
 * so baking only the drivers is the whole, sufficient contract.
 *
 * Shape (compact, ISO-2 keyed):
 *   { [iso2: string]: { [indicatorCode: string]: { [year: string]: number } } }
 *
 * SERVER-ONLY: this module statically imports a ~15 MB JSON. Import it only from
 * server data builders / server components so it never reaches the client bundle.
 *
 * 2026-06-04: introduced for the per-analogue comparison page (subject vs
 * analogue, driver indicators, over the trend's canonical window). This is the
 * contract the streamlined bake should emit going forward — see
 * `docs/specs/internal/ops/sanctions-simulator-rnd-brief-2026-06-04.md` siblings
 * and the analogue-page work.
 */
import rawPanels from "@/data/te-fleet-run-2/indicator-panels.json";

/** `{ iso2 → { indicatorCode → { year(string) → value } } }`. */
export type IndicatorPanels = Record<string, Record<string, Record<string, number>>>;

const PANELS = rawPanels as IndicatorPanels;

/** One point on an indicator's time series. */
export interface IndicatorPoint {
  year: number;
  value: number;
}

/** Raw yearly series for one (country, indicator), or null if absent. */
export function getIndicatorSeries(
  iso2: string | null | undefined,
  indicatorCode: string
): Record<string, number> | null {
  if (!iso2) return null;
  return PANELS[iso2.toLowerCase()]?.[indicatorCode] ?? null;
}

/**
 * A window of an indicator's series, ending at `endYear` (inclusive) and
 * spanning `windowYears` years, ascending by year. Only years with a real value
 * are returned, so a sparse indicator yields a shorter (gappy) array rather than
 * fabricated zeros — callers should treat <2 points as "not enough to draw".
 */
export function getIndicatorWindow(
  iso2: string | null | undefined,
  indicatorCode: string,
  endYear: number,
  windowYears: number
): IndicatorPoint[] {
  const series = getIndicatorSeries(iso2, indicatorCode);
  if (!series) return [];
  const startYear = endYear - windowYears + 1;
  const out: IndicatorPoint[] = [];
  for (let y = startYear; y <= endYear; y++) {
    const v = series[String(y)];
    if (typeof v === "number") out.push({ year: y, value: v });
  }
  return out;
}

/** The most recent year for which this (country, indicator) has a value. */
export function latestYearFor(
  iso2: string | null | undefined,
  indicatorCode: string
): number | null {
  const series = getIndicatorSeries(iso2, indicatorCode);
  if (!series) return null;
  const years = Object.keys(series).map(Number);
  return years.length ? Math.max(...years) : null;
}

/** Whether any driver-panel data exists for a country (cheap presence check). */
export function hasIndicatorPanel(iso2: string | null | undefined): boolean {
  return !!iso2 && !!PANELS[iso2.toLowerCase()];
}
