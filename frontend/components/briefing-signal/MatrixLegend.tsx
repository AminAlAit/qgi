/**
 * MatrixLegend — verdict legend strip + ACTIVE/SIGNAL/LATENT counts.
 * Server component.
 */
import type { HfCell, HfVerdict } from "@/lib/hf/topics-data";

const VERDICT_COLOR: Record<HfVerdict, string> = {
  ACTIVE: "rgba(224,92,92,0.85)",
  SIGNAL: "rgba(245,158,11,0.80)",
  LATENT: "rgba(91,126,153,0.70)",
  QUIET: "rgba(36,51,71,0.50)",
};

const VERDICT_LABEL: Record<HfVerdict, string> = {
  ACTIVE: "Both Firing",
  SIGNAL: "News-Only",
  LATENT: "Elevated & Quiet",
  QUIET: "Quiet",
};

interface Props {
  cells: Record<string, HfCell>;
}

export function MatrixLegend({ cells }: Props) {
  const counts: Record<HfVerdict, number> = { ACTIVE: 0, SIGNAL: 0, LATENT: 0, QUIET: 0 };
  for (const cell of Object.values(cells)) {
    counts[cell.verdict]++;
  }

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        flexWrap: "wrap",
        gap: "10px 16px",
        marginTop: "10px",
        padding: "8px 12px",
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "6px",
      }}
    >
      {/* Legend swatches */}
      <div
        style={{ display: "flex", alignItems: "center", gap: "16px", flexWrap: "wrap" }}
      >
        {(["ACTIVE", "SIGNAL", "LATENT", "QUIET"] as HfVerdict[]).map((v) => (
          <div key={v} style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <div
              style={{
                width: "12px",
                height: "12px",
                borderRadius: "2px",
                background: VERDICT_COLOR[v],
                flexShrink: 0,
              }}
            />
            <span
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "10px",
                letterSpacing: "1px",
                textTransform: "uppercase",
                color: "var(--qgi-text-muted)",
              }}
            >
              {VERDICT_LABEL[v]}
            </span>
          </div>
        ))}
      </div>

      {/* Verdict counts */}
      <div
        style={{ display: "flex", alignItems: "center", gap: "14px", flexWrap: "wrap" }}
      >
        {(["ACTIVE", "SIGNAL", "LATENT"] as HfVerdict[]).map((v) => (
          <div key={v} style={{ display: "flex", alignItems: "center", gap: "4px" }}>
            <span
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "13px",
                fontWeight: 700,
                color:
                  v === "ACTIVE" ? "#E05C5C" : v === "SIGNAL" ? "#f59e0b" : "#5B7E99",
              }}
            >
              {counts[v]}
            </span>
            <span
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "9px",
                letterSpacing: "1px",
                textTransform: "uppercase",
                color: "var(--qgi-text-dim)",
              }}
            >
              {v}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
