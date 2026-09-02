/**
 * live-pulse-buckets-core — the PURE transform that rebuilds intraday news-pulse
 * SERIES from the poller's raw 15-min bucket cache (dashboard/hf-pulse-buckets.json).
 *
 * It reproduces the poller's own math (modules/live-pulse/src/lambda_function.py),
 * validated to 0 error against the live cells: per window,
 *   share = topic_docs / country_docs,  z = (share - mu) / sigma,
 *   pulse = clamp(2, 100, round(50 + 20 * z))
 * The only difference from the poller is that we roll SEVERAL shorter windows
 * (1H / 4H / 1D) to draw a line, instead of a single trailing-24h "now" value.
 *
 * No imports, no AWS, no clock — pure and unit-testable.
 */

// Bucket vector layout, fixed by the poller: [total, T01, T02, T03, T05, T06, T07].
// Index 0 is the country-doc total (the share denominator); topics follow.
export const BUCKET_BOARD = ["T01", "T02", "T03", "T05", "T06", "T07"] as const;

export type BucketRes = "1H" | "4H" | "1D";

export interface BucketsDoc {
  updated?: string;
  newest?: string;
  /** stamp "YYYYMMDDHHMMSS" -> iso3 -> [total, t01, t02, t03, t05, t06, t07] */
  buckets: Record<string, Record<string, number[]>>;
}

export interface BaselineDoc {
  stats: Record<string, { mu: number; sigma: number; days?: number }>;
}

export interface PulseSeries {
  x: string[];
  y: number[];
  /** False => most windows are too thin to trust the z-score (terminal greys it). */
  reliable: boolean;
}

/** Same mapping as the poller's z_to_100 (build_pressure parity): 50 = own mean. */
export function zTo100(z: number): number {
  return Math.max(2, Math.min(100, Math.round(50 + 20 * z)));
}

/** Window-start label for a 15-min stamp "YYYYMMDDHHMMSS". */
export function windowKey(stamp: string, res: BucketRes): string {
  const y = stamp.slice(0, 4);
  const m = stamp.slice(4, 6);
  const d = stamp.slice(6, 8);
  if (res === "1D") return `${y}-${m}-${d}`;
  const hh = parseInt(stamp.slice(8, 10), 10) || 0;
  const h = res === "4H" ? Math.floor(hh / 4) * 4 : hh;
  return `${y}-${m}-${d} ${String(h).padStart(2, "0")}:00`;
}

// Per-resolution country-doc floor, scaled from the poller's 24h MIN_COUNTRY_DOCS
// (200). A window thinner than this is flagged unreliable rather than dropped,
// so the line stays continuous but the terminal can grey a noisy stretch.
const COUNTRY_FLOOR: Record<BucketRes, number> = { "1H": 25, "4H": 90, "1D": 200 };

// Per-resolution topic-doc floor (mirrors the poller's MIN_TOPIC_DOCS=5 over
// 24h): a window with fewer topic docs than this is too thin to z-score, so it
// reads NEUTRAL 50, never a misleading low pulse. The single-cell poller emits
// null for this case; we emit neutral to keep the line continuous.
const TOPIC_FLOOR: Record<BucketRes, number> = { "1H": 2, "4H": 3, "1D": 5 };

/**
 * Build {topicId -> PulseSeries} at one resolution for one country, or null when
 * the country is absent from the cache. Reproduces the poller's per-cell pulse.
 */
export function buildBucketSeries(
  buckets: BucketsDoc["buckets"],
  baseline: BaselineDoc,
  iso3: string,
  res: BucketRes
): Record<string, PulseSeries> | null {
  const stats = baseline?.stats ?? {};
  const agg = new Map<string, number[]>(); // window label -> summed [total, ...6]
  let present = false;

  for (const [stamp, perCountry] of Object.entries(buckets)) {
    const vec = perCountry[iso3];
    if (!vec) continue;
    present = true;
    const k = windowKey(stamp, res);
    let acc = agg.get(k);
    if (!acc) {
      acc = [0, 0, 0, 0, 0, 0, 0];
      agg.set(k, acc);
    }
    for (let i = 0; i < 7; i++) acc[i] += vec[i] ?? 0;
  }
  if (!present) return null;

  const windows = [...agg.keys()].sort();
  const floor = COUNTRY_FLOOR[res];
  const out: Record<string, PulseSeries> = {};

  BUCKET_BOARD.forEach((topic, idx) => {
    const vi = idx + 1; // vector index (0 is the total)
    const x: string[] = [];
    const y: number[] = [];
    let thick = 0;
    const stat = stats[`${iso3}|${topic}`];
    for (const w of windows) {
      const vec = agg.get(w)!;
      const total = vec[0];
      const topicDocs = vec[vi];
      if (total >= floor) thick++;
      let pulse: number;
      if (!stat || total < 1 || topicDocs < TOPIC_FLOOR[res]) {
        // No baseline, no docs, or too few topic docs this window to read:
        // neutral 50 — never a false spike OR a false dip (poller sparsity rule).
        pulse = 50;
      } else {
        const share = topicDocs / total;
        const sigma = Math.max(stat.sigma, 1e-9);
        pulse = zTo100((share - stat.mu) / sigma);
      }
      x.push(w);
      y.push(pulse);
    }
    out[topic] = {
      x,
      y,
      reliable: windows.length > 0 && thick >= windows.length / 2,
    };
  });
  return out;
}
