/**
 * HistoryAccumulatingGate — shared empty-state for time-series fields that
 * cannot be populated at vintage 1.
 *
 * Per the R&D pipeline reply (docs-specs #169, 2026-05-26 §3):
 *   - `risk-board.recent_movements` (rank shifts vs prior quarter) is empty
 *     until vintage 2.
 *   - `countries/<iso>.momentum.rank_history` / `score_history` need ~12
 *     quarterly vintages to accrue.
 *   - `countries/<iso>.drivers[].trajectory` is NOT gated (backfillable from
 *     observed panel history at vintage 1).
 *
 * Used wherever the frontend would otherwise render a zero / fake datum.
 * The component shows an honest "history accumulating" message + a small
 * dotted-line placeholder. Never a 0 — that would be a methodology lie.
 *
 * Honesty regime (M8-R5): a time-series we don't yet have is shown as
 * "not yet available," never as a flat line at zero. The dotted placeholder
 * visually rhymes with the live sparklines next to it but reads as absence.
 */
import { Hourglass } from "lucide-react";

interface Props {
  /** Bake vintage string from the source-of-truth JSON (e.g. "2026-05-23"). */
  vintage: string;
  /**
   * What the field is. Used in the message body so the reader knows
   * specifically what's accumulating ("rank history" vs "score history").
   */
  label?: string;
  /**
   * When the field is expected to start filling — e.g. "vintage 2 (~Q2 2027)".
   * Default tracks the pipeline's stated quarterly cadence.
   */
  nextAvailableAt?: string;
  /** Visual variant — "row" sits inline on a recipe row; "card" is a standalone tile. */
  variant?: "row" | "card";
}

export function HistoryAccumulatingGate({
  vintage,
  label = "Quarterly diffs",
  nextAvailableAt = "release 2 (~Q2 2027)",
  variant = "card",
}: Props) {
  const padding = variant === "row" ? "10px 14px" : "18px 20px";
  const fontSize = variant === "row" ? "11.5px" : "12.5px";
  const minHeight = variant === "row" ? "48px" : "76px";

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        display: "flex",
        alignItems: "center",
        gap: "14px",
        padding,
        minHeight,
        border: "1px dashed var(--qgi-border)",
        background: "rgba(255,255,255,0.015)",
        borderRadius: "6px",
        color: "var(--qgi-text-muted)",
      }}
    >
      <div
        style={{
          width: variant === "row" ? "28px" : "36px",
          height: variant === "row" ? "28px" : "36px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--qgi-text-dim)",
          border: "1px dashed var(--qgi-text-dim)",
          borderRadius: "5px",
          flexShrink: 0,
        }}
      >
        <Hourglass size={variant === "row" ? 14 : 18} strokeWidth={1.5} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize,
            fontWeight: 600,
            color: "var(--qgi-text-muted)",
            marginBottom: "2px",
            lineHeight: 1.3,
          }}
        >
          {label}: history accumulating.
        </div>
        <div
          style={{
            fontSize: "10.5px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.3px",
            lineHeight: 1.45,
          }}
        >
          First bake live at {vintage}; quarterly diffs begin at {nextAvailableAt}.
        </div>
      </div>
      {/* Dotted placeholder line — visually rhymes with sparklines but reads as absence. */}
      <svg
        width={variant === "row" ? 96 : 140}
        height={variant === "row" ? 18 : 28}
        viewBox={`0 0 ${variant === "row" ? 96 : 140} ${variant === "row" ? 18 : 28}`}
        aria-hidden="true"
        style={{ flexShrink: 0, opacity: 0.55 }}
      >
        <line
          x1="4"
          x2={variant === "row" ? 92 : 136}
          y1={variant === "row" ? 9 : 14}
          y2={variant === "row" ? 9 : 14}
          stroke="var(--qgi-text-dim)"
          strokeWidth="1.5"
          strokeDasharray="2 4"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}
