/**
 * lib/dashboard/briefing-insights.ts — Perpetual briefing insight derivation.
 *
 * Server-only module. Derives 4 fresh news-intelligence panels from the real
 * data bakes at build time:
 *
 *   1. Pulse Movers    — biggest month-on-month pulse shifts (rises + falls)
 *   2. Silent Alarms   — high-struct LATENT cells (structural signal, no news yet)
 *   3. News Caught Up  — cells where pulse just crossed 80% of struct this month
 *   4. Historic Highs  — cells at or above 95% of their 10-year pulse maximum
 *
 * Every value is derived from the data files. Nothing is hardcoded. When a new
 * GDELT poll bakes updated hf-topics.json / hf-pulse-detail.json the outputs
 * auto-update on the next build (ISR revalidate = 300s).
 *
 * Import pattern mirrors pulse-detail.ts: import "server-only" guard at top,
 * JSON imported directly at module level.
 */
import "server-only";

import detail from "@/data/hf-pulse-detail.json";
import { getTrendBoard } from "@/lib/hf/trend-board";
import type { HfVerdict, HfCell, HfBoard } from "@/lib/hf/topics-data";

// ── Thresholds ────────────────────────────────────────────────────────────────

/** Pulse must have crossed this fraction of struct in the current month. */
const CATCH_UP_RATIO = 0.8;

/** Minimum struct score for a cell to qualify for the caught-up panel. */
const MIN_STRUCT_FOR_CATCHUP = 60;

/** Minimum fraction of historic max to qualify as "at a high". */
const AT_HIGH_PCT = 0.95;

/** Minimum history length for a historic-high computation to be meaningful. */
const MIN_HISTORY_MONTHS = 24;

// ── Types (exported for component props) ──────────────────────────────────────

export interface PulseMover {
  key: string;
  iso3: string;
  topicId: string;
  countryName: string;
  topicLabel: string;
  /** pulse − prevPulse; positive = rising, negative = falling. */
  delta: number;
  pulse: number;
  prevPulse: number;
  struct: number;
  verdict: HfVerdict;
  direction: "rising" | "falling";
}

export interface SilentAlarm {
  key: string;
  iso3: string;
  topicId: string;
  countryName: string;
  topicLabel: string;
  struct: number;
  pulse: number;
  /** struct − pulse: the unmet-news gap. */
  gap: number;
}

export interface CaughtUpCell {
  key: string;
  iso3: string;
  topicId: string;
  countryName: string;
  topicLabel: string;
  struct: number;
  pulse: number;
  prevPulse: number;
  /** Math.round((pulse / struct) * 100) — can exceed 100. */
  crossoverPct: number;
}

export interface HistoricHighCell {
  key: string;
  iso3: string;
  topicId: string;
  countryName: string;
  topicLabel: string;
  currentPulse: number;
  historicMax: number;
  /** (currentPulse / historicMax) * 100, rounded. Can exceed 100 = NEW HIGH. */
  pct: number;
  verdict: HfVerdict;
}

export interface BriefingInsights {
  /** Top 4 rising cells by delta. */
  topRisers: PulseMover[];
  /** Top 2 falling cells by delta (most negative first). */
  topFallers: PulseMover[];
  /** Loudest topic label, e.g. "Energy". */
  loudestTopicLabel: string;
  /** Sum of pulse across all countries for the loudest topic. */
  loudestTopicPulse: number;
  /** Top 6 LATENT cells by struct desc (structural pressure, quiet news). */
  silentAlarms: SilentAlarm[];
  /** Cells where pulse just crossed 80% of struct this month. */
  caughtUp: CaughtUpCell[];
  /** Cells at or above 95% of their all-time pulse max, non-QUIET. */
  atHistoricHigh: HistoricHighCell[];
}

// ── Internal detail type ──────────────────────────────────────────────────────

const rawDetail = detail as unknown as {
  built: string;
  history: Record<string, { months: string[]; pulse: number[] }>;
  events: Record<string, Array<{ date: string; label: string }>>;
};

// ── Internal helpers (pure, testable) ─────────────────────────────────────────

function computeMovers(cells: Record<string, HfCell>, board: HfBoard): PulseMover[] {
  const result: PulseMover[] = [];
  for (const [key, cell] of Object.entries(cells)) {
    if (cell.prevPulse == null) continue;
    const [iso3, topicId] = key.split("|");
    if (!iso3 || !topicId) continue;
    const country = board.countries.find((c) => c.iso3 === iso3);
    const topic = board.topics.find((t) => t.id === topicId);
    if (!country || !topic) continue;
    const delta = cell.pulse - cell.prevPulse;
    if (delta === 0) continue;
    result.push({
      key,
      iso3,
      topicId,
      countryName: country.name,
      topicLabel: topic.label,
      delta,
      pulse: cell.pulse,
      prevPulse: cell.prevPulse,
      struct: cell.struct ?? 0,
      verdict: cell.verdict,
      direction: delta >= 0 ? "rising" : "falling",
    });
  }
  return result;
}

function computeSilentAlarms(
  cells: Record<string, HfCell>,
  board: HfBoard
): SilentAlarm[] {
  const result: SilentAlarm[] = [];
  for (const [key, cell] of Object.entries(cells)) {
    if (cell.verdict !== "LATENT") continue;
    const [iso3, topicId] = key.split("|");
    if (!iso3 || !topicId) continue;
    const country = board.countries.find((c) => c.iso3 === iso3);
    const topic = board.topics.find((t) => t.id === topicId);
    if (!country || !topic) continue;
    const struct = cell.struct ?? 0;
    result.push({
      key,
      iso3,
      topicId,
      countryName: country.name,
      topicLabel: topic.label,
      struct,
      pulse: cell.pulse,
      gap: struct - cell.pulse,
    });
  }
  return result.sort((a, b) => b.struct - a.struct);
}

function computeCaughtUp(cells: Record<string, HfCell>, board: HfBoard): CaughtUpCell[] {
  const result: CaughtUpCell[] = [];
  for (const [key, cell] of Object.entries(cells)) {
    const s = cell.struct ?? 0;
    if (s < MIN_STRUCT_FOR_CATCHUP) continue;
    if (cell.prevPulse == null) continue;
    const floor = s * CATCH_UP_RATIO;
    if (!(cell.pulse >= floor && cell.prevPulse < floor)) continue;
    const [iso3, topicId] = key.split("|");
    if (!iso3 || !topicId) continue;
    const country = board.countries.find((c) => c.iso3 === iso3);
    const topic = board.topics.find((t) => t.id === topicId);
    if (!country || !topic) continue;
    result.push({
      key,
      iso3,
      topicId,
      countryName: country.name,
      topicLabel: topic.label,
      struct: s,
      pulse: cell.pulse,
      prevPulse: cell.prevPulse,
      crossoverPct: Math.round((cell.pulse / s) * 100),
    });
  }
  return result.sort((a, b) => b.struct - a.struct);
}

function computeHistoricHighs(
  cells: Record<string, HfCell>,
  board: HfBoard,
  longHistory: Record<string, { months: string[]; pulse: number[] }>
): HistoricHighCell[] {
  const result: HistoricHighCell[] = [];
  for (const [key, h] of Object.entries(longHistory)) {
    if (!h.pulse || h.pulse.length < MIN_HISTORY_MONTHS) continue;
    const cell = cells[key];
    if (!cell || cell.verdict === "QUIET") continue;
    // Historic max = all months EXCEPT the most recent (current month).
    const historicMax = Math.max(...h.pulse.slice(0, -1));
    if (historicMax <= 0) continue;
    const currentPulse = h.pulse[h.pulse.length - 1];
    const pct = (currentPulse / historicMax) * 100;
    if (pct < AT_HIGH_PCT * 100) continue;
    const [iso3, topicId] = key.split("|");
    if (!iso3 || !topicId) continue;
    const country = board.countries.find((c) => c.iso3 === iso3);
    const topic = board.topics.find((t) => t.id === topicId);
    if (!country || !topic) continue;
    result.push({
      key,
      iso3,
      topicId,
      countryName: country.name,
      topicLabel: topic.label,
      currentPulse,
      historicMax: Math.round(historicMax),
      pct: Math.round(pct),
      verdict: cell.verdict,
    });
  }
  return result.sort((a, b) => b.pct - a.pct);
}

function computeLoudestTopic(
  cells: Record<string, HfCell>,
  board: HfBoard
): { label: string; total: number } {
  const totals: Record<string, number> = {};
  for (const [key, cell] of Object.entries(cells)) {
    const topicId = key.split("|")[1];
    if (!topicId) continue;
    totals[topicId] = (totals[topicId] ?? 0) + cell.pulse;
  }
  const sorted = Object.entries(totals).sort((a, b) => b[1] - a[1]);
  if (sorted.length === 0) return { label: "Unknown", total: 0 };
  const [loudestId, total] = sorted[0];
  const label = board.topics.find((t) => t.id === loudestId)?.label ?? loudestId;
  return { label, total };
}

// ── Primary export ─────────────────────────────────────────────────────────────

/**
 * Derives all briefing insight panels from the current data bakes.
 *
 * Call once in a server component (dashboard/page.tsx). Pure CPU — no I/O,
 * no await. Re-derives on every ISR revalidation.
 */
export function deriveBriefingInsights(): BriefingInsights {
  const board = getTrendBoard();
  const cells = board.cells;
  const longHistory = rawDetail.history;

  // 1. Movers
  const allMovers = computeMovers(cells, board);
  const topRisers = allMovers
    .filter((m) => m.delta > 0)
    .sort((a, b) => b.delta - a.delta)
    .slice(0, 4);
  const topFallers = allMovers
    .filter((m) => m.delta < 0)
    .sort((a, b) => a.delta - b.delta) // most negative first
    .slice(0, 2);

  // 2. Loudest topic
  const { label: loudestTopicLabel, total: loudestTopicPulse } = computeLoudestTopic(
    cells,
    board
  );

  // 3. Silent alarms
  const silentAlarms = computeSilentAlarms(cells, board).slice(0, 6);

  // 4. Caught-up cells
  const caughtUp = computeCaughtUp(cells, board).slice(0, 5);

  // 5. Historic highs (uses full 2015-present history from pulse-detail.json)
  const atHistoricHigh = computeHistoricHighs(cells, board, longHistory).slice(0, 6);

  return {
    topRisers,
    topFallers,
    loudestTopicLabel,
    loudestTopicPulse: Math.round(loudestTopicPulse),
    silentAlarms,
    caughtUp,
    atHistoricHigh,
  };
}
