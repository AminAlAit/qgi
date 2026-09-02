/**
 * hf/trend-signal — the news layer seen from a TREND's side.
 *
 * A trend's news signal rides its primary incoming theme (the news Topic
 * whose high-confidence crosswalk feeds this trend). For every covered
 * country we pair THIS trend's structural score (fleet run-2, 0-100) with
 * the theme's monthly news pulse and read the same 60/60 verdict the rest
 * of the news layer uses. Server-side only; pages slice and pass props.
 */

import { getHfBoard, type HfTopic, type HfVerdict } from "@/lib/hf/topics-data";
import { getRecipeFullScoreMap } from "@/lib/te-mock/risk-board-data";
import { iso2For } from "@/lib/te-mock/country-flags";
import { getTrendPulse, isPerTrend, isPulseOnly } from "@/lib/hf/trend-pulse";
import { trendNewsStatus, trendLabel } from "@/lib/hf/trend-taxonomy";

export interface TrendSignalRow {
  name: string;
  iso3: string;
  /** ISO-2 (lowercase) — keys the /trends/[slug]/countries/[iso] page. */
  iso2: string | null;
  /** This trend's structural score for the country, 0-100. NULL for news-only
   *  trends (labor_action etc.) where no structural axis is shown. */
  struct: number | null;
  /** The trend's news pulse for the country, 0-100 (per-Trend native where
   *  available, else the primary theme's pulse). */
  pulse: number;
  verdict: HfVerdict;
}

export interface TrendNewsSignal {
  /** 'live' = trend has a native GDELT news feed (see trend-taxonomy).
   *  'coming_soon' = no native feed yet; signal is a placeholder shell with
   *  empty rows, not a borrowed topic pulse. */
  status: "live" | "coming_soon";
  topic: HfTopic;
  rows: TrendSignalRow[];
  /** Covered countries missing from this trend's fleet scoring (indicator
   *  coverage gaps), named in the panel footnote rather than silently
   *  dropped (review finding: Myanmar vanished from currency_crisis). */
  notScored: string[];
  thresholds: { struct: number; pulse: number };
  verdicts: Record<HfVerdict, string>;
  /** True when this trend carries a native per-Trend news pulse (the 6
   *  two-layer trends). When false, pulse falls back to the topic crosswalk. */
  perTrend: boolean;
  /** True when the trend renders NEWS-ONLY: no structural axis/line/score and
   *  the verdict reads off the news pulse alone (labor_action only; see
   *  trend-taxonomy NEWS_ONLY_TRENDS). Descriptive only. */
  pulseOnly: boolean;
}

function verdictAt(
  struct: number,
  pulse: number,
  th: { struct: number; pulse: number }
): HfVerdict {
  const hiS = struct >= th.struct;
  const hiP = pulse >= th.pulse;
  if (hiS && hiP) return "ACTIVE";
  if (!hiS && hiP) return "SIGNAL";
  if (hiS && !hiP) return "LATENT";
  return "QUIET";
}

/**
 * The trend's primary theme: a board theme listing this trend in its
 * high-confidence crosswalk, validated themes first; remaining ties break
 * on the CANONICAL T01..T14 taxonomy order (deliberate, not accidental:
 * e.g. political_violence sits in both Armed Conflict (T02) and Terrorism
 * (T03) — T02 wins, matching the PoC's ratified live mapping). Null when
 * no theme feeds the trend (news-blind or low-confidence only) — callers
 * hide the panel rather than render an empty frame.
 */
export function primaryThemeFor(recipeId: string): HfTopic | null {
  const board = getHfBoard();
  const orderOf = (t: HfTopic) => board.topics.indexOf(t);
  const candidates = board.topics.filter((t) => t.trends.includes(recipeId));
  if (candidates.length === 0) return null;
  candidates.sort(
    (a, b) =>
      Number(b.board) - Number(a.board) ||
      Number(b.validated) - Number(a.validated) ||
      orderOf(a) - orderOf(b)
  );
  return candidates[0];
}

export function getTrendNewsSignal(recipeId: string): TrendNewsSignal | null {
  if (trendNewsStatus(recipeId) === "coming_soon") {
    // Coming-soon trend: no native feed yet. Return a placeholder shell,
    // never a borrowed topic pulse.
    const board = getHfBoard();
    const topic: HfTopic = primaryThemeFor(recipeId) ?? {
      id: recipeId,
      label: trendLabel(recipeId),
      name: trendLabel(recipeId),
      scope: "",
      validated: false,
      board: false,
      trends: [recipeId],
    };
    return {
      status: "coming_soon",
      topic,
      rows: [],
      notScored: [],
      thresholds: board.thresholds,
      verdicts: board.verdicts,
      perTrend: false,
      pulseOnly: false,
    };
  }

  const topic = primaryThemeFor(recipeId);
  if (!topic) return null;
  const board = getHfBoard();

  const perTrend = isPerTrend(recipeId);
  const pulseOnly = isPulseOnly(recipeId);

  // Structural scores only matter for fused (non-news-only) trends.
  const scores = pulseOnly ? null : getRecipeFullScoreMap(recipeId);
  if (!pulseOnly && (!scores || Object.keys(scores).length === 0)) return null;
  // Fleet scores are 0-100; normalize defensively if a future file is 0-1.
  const maxScore = scores ? Math.max(...Object.values(scores)) : 0;
  const scale = maxScore <= 1.5 ? 100 : 1;

  const rows: TrendSignalRow[] = [];
  const notScored: string[] = [];
  for (const c of board.countries) {
    const cell = board.cells[`${c.iso3}|${topic.id}`];
    // Pulse: prefer THIS trend's native per-Trend pulse; fall back to the
    // primary theme's pulse (the legacy crosswalk) for trends without it.
    const pulse = getTrendPulse(c.iso3, recipeId) ?? cell?.pulse ?? null;
    if (pulse == null) continue; // no news reading for this country/trend

    if (pulseOnly) {
      // News-only trend: no structural axis. Verdict reads off the pulse alone.
      rows.push({
        name: c.name,
        iso3: c.iso3,
        iso2: iso2For(c.name) ?? null,
        struct: null,
        pulse,
        verdict: pulse >= board.thresholds.pulse ? "SIGNAL" : "QUIET",
      });
      continue;
    }

    const raw = scores![c.name];
    if (typeof raw !== "number") {
      // Covered by the news layer but not scored on this trend — name it
      // rather than silently dropping it.
      notScored.push(c.name);
      continue;
    }
    const struct = Math.round(raw * scale * 10) / 10;
    rows.push({
      name: c.name,
      iso3: c.iso3,
      iso2: iso2For(c.name) ?? null,
      struct,
      pulse,
      verdict: verdictAt(struct, pulse, board.thresholds),
    });
  }
  if (rows.length === 0) return null;

  // Strongest combined reading first (weakest-leg rule, as everywhere); a
  // news-only row sorts on its pulse alone.
  rows.sort((a, b) => {
    const aMin = a.struct == null ? a.pulse : Math.min(a.struct, a.pulse);
    const bMin = b.struct == null ? b.pulse : Math.min(b.struct, b.pulse);
    return bMin - aMin;
  });

  return {
    status: "live",
    topic,
    rows,
    notScored,
    thresholds: board.thresholds,
    verdicts: board.verdicts,
    perTrend,
    pulseOnly,
  };
}
