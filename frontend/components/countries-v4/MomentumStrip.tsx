/**
 * MomentumStrip — for each top-lit recipe, render a 12-quarter rank-shift
 * sparkline showing the country's movement through the score
 * distribution.
 *
 * Honesty: this is RETROSPECTIVE only — the line shows where the country
 * has been, never extrapolated forward.
 *
 * 2026-05-26 schema-align (R&D reply docs-specs #169 §3): rank_history /
 * score_history need ~12 quarterly vintages to accrue. At vintage 1 the
 * arrays are length 1; the component renders <HistoryAccumulatingGate />
 * until enough vintages exist for a meaningful sparkline (length ≥ 2).
 * Mock data ships with full 12-quarter arrays for visual development;
 * the real bake will start short and grow.
 */
import { iconForRecipe } from "@/lib/te-mock/icons";
import type { CountryMomentum } from "@/lib/te-mock/countries-v4-data";
import { HistoryAccumulatingGate } from "@/components/te-v4-shared/HistoryAccumulatingGate";
import { RecipeIcon } from "@/components/te-v4-shared/RecipeIcon";

interface Props {
  momentum: readonly CountryMomentum[];
  /** Source-of-truth vintage stamp from the bake — used by the gate copy. */
  vintage: string;
}

/** Minimum history length to render the sparkline. Below this we gate honestly. */
const MIN_HISTORY_FOR_SPARK = 2;

export function MomentumStrip({ momentum, vintage }: Props) {
  if (momentum.length === 0) {
    return (
      <HistoryAccumulatingGate
        vintage={vintage}
        label="Rank momentum"
        nextAvailableAt="release 2 (~Q2 2027)"
      />
    );
  }

  // If ALL recipes have insufficient history, render a single gate.
  const allShort = momentum.every((m) => m.rank_history.length < MIN_HISTORY_FOR_SPARK);
  if (allShort) {
    return (
      <HistoryAccumulatingGate
        vintage={vintage}
        label="Rank momentum (per recipe)"
        nextAvailableAt="release 2 (~Q2 2027)"
      />
    );
  }

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
        gap: "12px",
      }}
    >
      {momentum.map((m) =>
        m.rank_history.length >= MIN_HISTORY_FOR_SPARK ? (
          <MomentumRow key={m.recipe_id} m={m} />
        ) : (
          <PerRecipeGate key={m.recipe_id} m={m} vintage={vintage} />
        )
      )}
    </div>
  );
}

/**
 * Per-recipe gate — for the mixed case where some recipes have history and
 * others don't. Compact card-shaped variant so it slots into the grid.
 */
function PerRecipeGate({ m, vintage }: { m: CountryMomentum; vintage: string }) {
  return (
    <div
      style={{
        background: "var(--qgi-surface)",
        border: "1px dashed var(--qgi-border)",
        borderRadius: "6px",
        padding: "12px",
        display: "flex",
        flexDirection: "column",
        gap: "10px",
        borderLeft: `3px dashed ${m.l1_color}`,
        opacity: 0.85,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
        <div
          style={{
            width: "28px",
            height: "28px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: m.l1_color,
            border: `1px dashed ${m.l1_color}`,
            borderRadius: "5px",
            flexShrink: 0,
          }}
        >
          <RecipeIcon recipeId={m.recipe_id} size={16} strokeWidth={1.7} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: "12.5px",
              fontWeight: 600,
              color: "var(--qgi-text)",
              lineHeight: 1.2,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {m.label}
          </div>
        </div>
      </div>
      <HistoryAccumulatingGate
        vintage={vintage}
        label="Rank history"
        nextAvailableAt="release 2 (~Q2 2027)"
        variant="row"
      />
    </div>
  );
}

function MomentumRow({ m }: { m: CountryMomentum }) {
  const first = m.rank_history[0];
  const last = m.rank_history[m.rank_history.length - 1];
  const delta = last - first;
  // Rank-shift: positive delta means the country MOVED UP the rank order
  // (score increased). Color: rising scores = warmer; falling = cooler.
  const dirLabel = delta > 1 ? "rising" : delta < -1 ? "falling" : "stable";
  const dirColor =
    delta > 1 ? "#E68F29" : delta < -1 ? "#5EE6C4" : "var(--qgi-text-muted)";

  return (
    <div
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "6px",
        padding: "12px",
        display: "flex",
        flexDirection: "column",
        gap: "10px",
        borderLeft: `3px solid ${m.l1_color}`,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "10px",
        }}
      >
        <div
          style={{
            width: "28px",
            height: "28px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: m.l1_color,
            background: `${m.l1_color}1A`,
            border: `1px solid ${m.l1_color}`,
            borderRadius: "5px",
            flexShrink: 0,
          }}
        >
          <RecipeIcon recipeId={m.recipe_id} size={16} strokeWidth={1.7} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: "12.5px",
              fontWeight: 600,
              color: "var(--qgi-text)",
              lineHeight: 1.2,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {m.label}
          </div>
          <div
            style={{
              fontSize: "9.5px",
              color: dirColor,
              fontFamily: "ui-monospace, monospace",
              letterSpacing: "0.3px",
              marginTop: "2px",
              textTransform: "uppercase",
              fontWeight: 600,
            }}
          >
            {dirLabel} · Δ {delta > 0 ? "+" : ""}
            {delta.toFixed(1)}
          </div>
        </div>
        <span
          style={{
            fontSize: "13px",
            fontWeight: 600,
            color: m.l1_color,
            fontFamily: "ui-monospace, monospace",
            lineHeight: 1,
          }}
        >
          {last.toFixed(0)}
        </span>
      </div>
      <MomentumSpark history={m.rank_history} stroke={m.l1_color} />
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: "9.5px",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
          letterSpacing: "0.3px",
        }}
      >
        <span>q-12</span>
        <span style={{ fontStyle: "italic" }}>retrospective only</span>
        <span>q-0</span>
      </div>
    </div>
  );
}

function MomentumSpark({
  history,
  stroke,
}: {
  history: readonly number[];
  stroke: string;
}) {
  const width = 260;
  const height = 56;
  const pad = { x: 4, y: 6 };
  const innerW = width - pad.x * 2;
  const innerH = height - pad.y * 2;
  // Fixed 0..100 axis so different recipes are visually comparable.
  const min = 0;
  const max = 100;
  const xScale = (i: number) => pad.x + (i / (history.length - 1)) * innerW;
  const yScale = (v: number) => pad.y + innerH - ((v - min) / (max - min)) * innerH;
  const d = history
    .map(
      (v, i) => `${i === 0 ? "M" : "L"} ${xScale(i).toFixed(1)} ${yScale(v).toFixed(1)}`
    )
    .join(" ");

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="12-quarter rank momentum sparkline"
      style={{ display: "block" }}
    >
      {/* Gridline at 50 (midpoint of distribution) */}
      <line
        x1={pad.x}
        x2={pad.x + innerW}
        y1={yScale(50)}
        y2={yScale(50)}
        stroke="var(--qgi-border)"
        strokeDasharray="2 3"
        strokeWidth={0.5}
      />
      <path d={d} fill="none" stroke={stroke} strokeWidth={1.8} opacity={0.95} />
      <circle
        cx={xScale(history.length - 1)}
        cy={yScale(history[history.length - 1])}
        r={2.8}
        fill={stroke}
      />
    </svg>
  );
}
