/**
 * PairSummaryPanel -- §2 Strength + window summary.
 *
 * Four tiles:
 *   1. Catalogue rank with magnitude bar (NEUTRAL_SLATE)
 *   2. Window (years range + count)
 *   3. Shared indicators count
 *   4. Correlation (real Pearson r over the shared window)
 *
 * No status chip. No family color. No probability framing.
 */
import { NEUTRAL_SLATE } from "@/lib/te-mock/l1-families";

interface PairSummaryPanelProps {
  catalogueRank: number;
  catalogueSize: number;
  startYear: number;
  endYear: number;
  windowLength: number;
  sharedIndicatorCount: number;
  /** Pearson correlation of the best shared window (real). */
  correlation: number;
}

export function PairSummaryPanel({
  catalogueRank,
  catalogueSize,
  startYear,
  endYear,
  windowLength,
  sharedIndicatorCount,
  correlation,
}: PairSummaryPanelProps) {
  const rankFraction = 1 - (catalogueRank - 1) / Math.max(catalogueSize - 1, 1);
  const rankBarWidth = Math.round(rankFraction * 100);

  return (
    <div
      data-tour="pair-summary"
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "10px",
        padding: "20px 22px",
        marginBottom: "20px",
      }}
    >
      <div
        style={{
          fontSize: "9px",
          letterSpacing: "1.6px",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
          marginBottom: "14px",
          fontWeight: 600,
        }}
      >
        PAIR SUMMARY
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
          gap: "16px",
        }}
      >
        {/* Tile 1: Catalogue rank */}
        <div style={tileStyle}>
          <div style={tileLabelStyle}>Catalogue rank</div>
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              gap: "6px",
              marginBottom: "8px",
            }}
          >
            <span style={{ ...tileValueStyle, color: "var(--qgi-accent)" }}>
              #{catalogueRank}
            </span>
            <span
              style={{
                fontSize: "12px",
                color: "var(--qgi-text-dim)",
                fontFamily: "ui-monospace, monospace",
              }}
            >
              of {catalogueSize}
            </span>
          </div>
          {/* Magnitude bar -- position in catalogue (higher rank = more filled) */}
          <div
            style={{
              width: "100%",
              height: "5px",
              background: "var(--qgi-border)",
              borderRadius: "3px",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${rankBarWidth}%`,
                height: "100%",
                background: NEUTRAL_SLATE,
                borderRadius: "3px",
                transition: "width 0.25s",
              }}
            />
          </div>
          <div
            style={{
              fontSize: "10px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
              marginTop: "4px",
            }}
          >
            Rank, not probability.
          </div>
        </div>

        {/* Tile 2: Window */}
        <div style={tileStyle}>
          <div style={tileLabelStyle}>Window</div>
          <div style={{ ...tileValueStyle, marginBottom: "4px" }}>
            {startYear}
            {"–"}
            {endYear}
          </div>
          <div
            style={{
              fontSize: "13px",
              color: "var(--qgi-text-muted)",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            {windowLength} years
          </div>
        </div>

        {/* Tile 3: Shared indicators */}
        <div style={tileStyle}>
          <div style={tileLabelStyle}>Shared indicators</div>
          <div style={{ ...tileValueStyle, marginBottom: "4px" }}>
            {sharedIndicatorCount}
          </div>
          <div
            style={{
              fontSize: "11px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
              lineHeight: 1.4,
            }}
          >
            indicators contributing to this pair&apos;s resemblance score
          </div>
        </div>

        {/* Tile 4: Correlation (real Pearson r) */}
        <div style={tileStyle}>
          <div style={tileLabelStyle}>Correlation</div>
          <div style={{ ...tileValueStyle, marginBottom: "4px" }}>
            {correlation.toFixed(2)}
          </div>
          <div
            style={{
              fontSize: "11px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
              lineHeight: 1.4,
            }}
          >
            Pearson r across the shared window
          </div>
        </div>
      </div>
    </div>
  );
}

const tileStyle: React.CSSProperties = {
  background: "var(--qgi-bg)",
  border: "1px solid var(--qgi-border)",
  borderRadius: "8px",
  padding: "14px 16px",
};

const tileLabelStyle: React.CSSProperties = {
  fontSize: "9px",
  letterSpacing: "1.2px",
  color: "var(--qgi-text-dim)",
  fontFamily: "ui-monospace, monospace",
  marginBottom: "8px",
  fontWeight: 600,
  textTransform: "uppercase" as const,
};

const tileValueStyle: React.CSSProperties = {
  fontSize: "22px",
  fontWeight: 800,
  color: "var(--qgi-text)",
  fontFamily: "ui-monospace, monospace",
  lineHeight: 1,
};
