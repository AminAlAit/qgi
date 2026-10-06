/**
 * BoardTeaserCell — a single cell in the BoardTeaser mini-grid.
 *
 * 44×44px square: tinted background by verdict, struct value centred,
 * bottom pulse bar, verdict dot top-right.
 *
 * Server component — pure CSS, no "use client".
 */

export type TeaserVerdict = "ACTIVE" | "SIGNAL" | "LATENT" | "QUIET" | "EMPTY";

interface BoardTeaserCellProps {
  struct: number | null;
  pulse: number;
  verdict: TeaserVerdict;
}

function verdictBg(verdict: TeaserVerdict): string {
  switch (verdict) {
    case "ACTIVE":
      return "rgba(224,92,92,0.12)";
    case "SIGNAL":
      return "rgba(245,158,11,0.10)";
    case "LATENT":
      return "rgba(91,126,153,0.08)";
    case "QUIET":
    case "EMPTY":
      return "var(--qgi-bg)";
  }
}

function verdictDot(verdict: TeaserVerdict): string {
  switch (verdict) {
    case "ACTIVE":
      return "#E05C5C";
    case "SIGNAL":
      return "#F59E0B";
    case "LATENT":
      return "#5B7E99";
    case "QUIET":
      return "rgba(148,163,184,0.4)";
    case "EMPTY":
      return "transparent";
  }
}

function pulseBarColor(verdict: TeaserVerdict): string {
  switch (verdict) {
    case "ACTIVE":
      return "#E05C5C";
    case "SIGNAL":
      return "#F59E0B";
    case "LATENT":
      return "#5B7E99";
    case "QUIET":
      return "rgba(148,163,184,0.3)";
    case "EMPTY":
      return "transparent";
  }
}

export function BoardTeaserCell({ struct, pulse, verdict }: BoardTeaserCellProps) {
  const bg = verdictBg(verdict);
  const dot = verdictDot(verdict);
  const barColor = pulseBarColor(verdict);
  const pulseWidth = verdict !== "EMPTY" ? `${Math.min(100, pulse)}%` : "0%";

  return (
    <div
      style={{
        width: "44px",
        height: "44px",
        background: bg,
        border: "1px solid var(--qgi-border)",
        position: "relative",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
        overflow: "hidden",
      }}
    >
      {/* Struct value */}
      {struct !== null && verdict !== "EMPTY" && (
        <span
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "11px",
            fontWeight: 700,
            color: "var(--qgi-text)",
          }}
        >
          {Math.round(struct)}
        </span>
      )}

      {/* Bottom pulse bar */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          height: "2px",
          width: pulseWidth,
          background: barColor,
        }}
      />

      {/* Verdict dot — top-right */}
      <div
        style={{
          position: "absolute",
          top: "3px",
          right: "3px",
          width: "3px",
          height: "3px",
          borderRadius: "50%",
          background: dot,
        }}
      />
    </div>
  );
}
