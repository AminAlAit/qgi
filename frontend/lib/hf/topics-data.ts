/**
 * hf/topics-data — the news-layer (Topics) board for /risk-board.
 *
 * Topics are the news-driven complement to the structural Trends: 14
 * news-native categories (GDELT GKG), each mapped many-to-many onto the
 * trend catalog. A country x topic cell combines the structural
 * resemblance (weighted mean of the crosswalked trends' scores) with the
 * monthly news pulse (share-of-country-news z-score, 0-100) into one of
 * four verdicts: ACTIVE / SIGNAL / LATENT / QUIET (thresholds 60/60).
 *
 * Data: data/hf-topics.json, generated from the validated GDELT PoC
 * artifacts (backfill 2015-02..present; recall-validated 2026-06-10:
 * Electoral + Economic news coverage clusters reliably around events on
 * the verified record. Any lead relationship between news pulse and events
 * is not established — the layer is descriptive, not predictive).
 */

import hfTopics from "@/data/hf-topics.json";
import { getCountryByIso } from "@/lib/te-mock/countries-v4-data";

export type HfVerdict = "ACTIVE" | "SIGNAL" | "LATENT" | "QUIET";

export interface HfTopic {
  id: string;
  /** Short column label, e.g. "Electoral". */
  label: string;
  /** Full name, e.g. "Electoral & Regime Change". */
  name: string;
  scope: string;
  /** True for topics whose news coverage is recall-validated against the event record (Electoral, Economic). No lead relationship established. */
  validated: boolean;
  /** True for the six founder-ratified board topics. */
  board: boolean;
  /** HIGH-confidence crosswalked trend ids. */
  trends: string[];
}

export interface HfCell {
  struct: number | null;
  pulse: number;
  prevPulse: number | null;
  verdict: HfVerdict;
}

export interface HfCountry {
  name: string;
  iso3: string;
  /** True when /countries/{iso3} exists (curated country set). */
  linkable: boolean;
}

export interface HfBoard {
  built: string;
  vintage: string;
  thresholds: { struct: number; pulse: number };
  verdicts: Record<HfVerdict, string>;
  topics: HfTopic[];
  boardTopics: HfTopic[];
  countries: HfCountry[];
  cells: Record<string, HfCell>;
  history: Record<string, { months: string[]; pulse: number[] }>;
}

let _cache: HfBoard | null = null;

export function getHfBoard(): HfBoard {
  if (_cache) return _cache;
  const raw = hfTopics as unknown as {
    built: string;
    vintage: string;
    thresholds: { struct: number; pulse: number };
    verdicts: Record<HfVerdict, string>;
    topics: HfTopic[];
    countries: Array<{ name: string; iso3: string }>;
    cells: Record<string, HfCell>;
    history: Record<string, { months: string[]; pulse: number[] }>;
  };
  _cache = {
    built: raw.built,
    vintage: raw.vintage,
    thresholds: raw.thresholds,
    verdicts: raw.verdicts,
    topics: raw.topics,
    boardTopics: raw.topics.filter((t) => t.board),
    countries: raw.countries.map((c) => ({
      ...c,
      linkable: Boolean(getCountryByIso(c.iso3)),
    })),
    cells: raw.cells,
    history: raw.history,
  };
  return _cache;
}

export function hfCellKey(iso3: string, topicId: string): string {
  return `${iso3}|${topicId}`;
}
