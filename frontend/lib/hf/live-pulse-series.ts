/**
 * hf/live-pulse-series — per-country multi-resolution news-pulse series + the
 * recent article feed, for the Live Pulse terminal (Surface B).
 *
 * Reads data/live-pulse/{ISO3}.json (built by qgi-console/build_live_pulse_proto.py
 * from the validated GDELT PoC; production will be emitted by the live-pulse
 * Lambda, Track 2). Each (topic, resolution) carries a `reliable` flag: the
 * terminal greys/suppresses thin cells (1h for low-news-volume countries)
 * rather than drawing a noisy line. Server-only: the per-country file is read
 * at request time and never bundled whole.
 */
import "server-only";

export type Resolution = "1H" | "4H" | "1D" | "1W" | "1M";

export interface LiveSeries {
  x: string[];
  y: number[];
  /** False => too few documents at this resolution to trust the z-score. */
  reliable: boolean;
}

export interface LiveArticle {
  dt: string; // GKG stamp YYYYMMDDHHMMSS
  domain: string;
  url: string;
  tone: number | null;
  topic: string;
  topicLabel: string;
}

export interface LivePulseSeriesData {
  iso3: string;
  name: string;
  source: string;
  resolutions: Resolution[];
  topics: Array<{ id: string; label: string; name: string; validated: boolean }>;
  /** topic id -> resolution -> series */
  series: Record<string, Partial<Record<Resolution, LiveSeries>>>;
  articles: LiveArticle[];
}

/** Multi-res series + article feed for one country, or null when not covered. */
export async function getLivePulseSeries(
  iso3: string
): Promise<LivePulseSeriesData | null> {
  try {
    const fs = await import("fs/promises");
    const path = await import("path");
    const file = path.join(
      process.cwd(),
      "data",
      "live-pulse",
      `${iso3.toUpperCase()}.json`
    );
    return JSON.parse(await fs.readFile(file, "utf-8")) as LivePulseSeriesData;
  } catch {
    // Not covered (or prototype data not generated) -> caller falls back to the
    // monthly detail. Never throws into a page render.
    return null;
  }
}
