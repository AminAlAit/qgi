/**
 * hf/live-pulse-core — the PURE half of the news-pulse staleness gate.
 *
 * No "server-only", no AWS SDK, no clock of its own: just the freshness
 * grading, the verdict rule, and the board overlay, all taking their inputs
 * as arguments so they unit-test cleanly. lib/hf/live-pulse.ts wraps these
 * with the S3 read (and the server-only guard).
 */
import { type HfBoard, type HfCell, type HfVerdict } from "@/lib/hf/topics-data";

export type LiveStatus = "live" | "recent" | "paused" | "absent";

export interface LivePulse {
  status: LiveStatus;
  /** ISO-8601 from the file, or null when absent. */
  generatedAt: string | null;
  /** Whole minutes since generated_at, or null when absent. */
  ageMinutes: number | null;
  /** Cell key ("ISO3|Txx") -> live pulse (0-100). Only non-null cells. */
  cells: Record<string, number>;
  /** Hours after which the poller's own contract says it is no longer "live". */
  staleAfterHours: number;
  vintage: string | null;
  source: "s3" | "local" | "none";
}

export interface RawLive {
  generated_at?: string;
  status?: string;
  stale_after_hours?: number;
  vintage?: string | null;
  cells?: Record<string, { pulse: number | null }>;
}

export interface LiveStamp {
  status: LiveStatus;
  ageMinutes: number | null;
  vintage: string | null;
}

export const ABSENT: LivePulse = {
  status: "absent",
  generatedAt: null,
  ageMinutes: null,
  cells: {},
  staleAfterHours: 2,
  vintage: null,
  source: "none",
};

const RECENT_CUTOFF_HOURS = 26; // beyond this -> paused

/**
 * Classify a parsed live file into a freshness state. Pure (takes `nowMs`)
 * so the gate thresholds are unit-testable without a clock.
 */
export function gradeLive(
  raw: RawLive,
  source: "s3" | "local",
  nowMs: number
): LivePulse {
  const staleAfterHours =
    typeof raw.stale_after_hours === "number" ? raw.stale_after_hours : 2;
  const gen = raw.generated_at ?? null;
  if (!gen || raw.status === "seeding" || raw.status === "warming") {
    // The poller is alive but has no real cells yet -> treat as absent so
    // the monthly board shows. Carry no stamp.
    return { ...ABSENT, source };
  }

  const genMs = Date.parse(gen);
  if (Number.isNaN(genMs)) return { ...ABSENT, source };
  const ageMinutes = Math.max(0, Math.round((nowMs - genMs) / 60000));
  const ageHours = ageMinutes / 60;

  let status: LiveStatus;
  if (ageHours <= staleAfterHours) status = "live";
  else if (ageHours <= RECENT_CUTOFF_HOURS) status = "recent";
  else status = "paused";

  // Pull only the cells that carry a real (non-null) live pulse.
  const cells: Record<string, number> = {};
  for (const [key, v] of Object.entries(raw.cells ?? {})) {
    if (v && typeof v.pulse === "number") cells[key] = v.pulse;
  }

  // A paused file contributes no values — only the "paused" stamp.
  return {
    status,
    generatedAt: gen,
    ageMinutes,
    cells: status === "paused" ? {} : cells,
    staleAfterHours,
    vintage: raw.vintage ?? null,
    source,
  };
}

/**
 * The four-way verdict, identical to the monthly bake's rule: ACTIVE when
 * both structural resemblance and pulse clear their thresholds, SIGNAL when
 * only pulse does, LATENT when only structure does, QUIET otherwise.
 */
export function verdictFor(
  struct: number | null,
  pulse: number,
  thresholds: { struct: number; pulse: number }
): HfVerdict {
  const s = struct != null && struct >= thresholds.struct;
  const p = pulse >= thresholds.pulse;
  if (s && p) return "ACTIVE";
  if (p) return "SIGNAL";
  if (s) return "LATENT";
  return "QUIET";
}

/**
 * Overlay live pulse onto the monthly board cells (pure). A cell is replaced
 * ONLY when the live file carries a value for it; its verdict is recomputed
 * from the SAME thresholds. Everything else passes through untouched, so an
 * empty `live.cells` returns a board identical to the input. Returns the new
 * cells map plus the set of keys that went live (for a per-cell marker).
 */
export function overlayCells(
  board: HfBoard,
  live: LivePulse
): { cells: Record<string, HfCell>; liveKeys: Set<string> } {
  const liveKeys = new Set<string>();
  if (live.status === "absent" || live.status === "paused") {
    return { cells: board.cells, liveKeys };
  }
  const next: Record<string, HfCell> = { ...board.cells };
  for (const [key, pulse] of Object.entries(live.cells)) {
    const base = board.cells[key];
    if (!base) continue; // never invent a cell the board doesn't have
    next[key] = {
      ...base,
      pulse,
      prevPulse: base.pulse, // the monthly value becomes the "prior"
      verdict: verdictFor(base.struct, pulse, board.thresholds),
    };
    liveKeys.add(key);
  }
  return { cells: next, liveKeys };
}
