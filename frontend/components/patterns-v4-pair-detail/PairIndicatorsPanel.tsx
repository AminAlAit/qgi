/**
 * PairIndicatorsPanel -- §4 Shared indicators decomposition.
 *
 * Top 8 indicators by contribution. Per row:
 *   - Indicator name + provider
 *   - Magnitude bar (NEUTRAL_SLATE) showing contribution
 *   - Two timestamps: A: {year}  . B: {year} -- never a delta
 *   - Tooltip on threshold definition
 *
 * HARD constraints (Marcus, binding):
 *   - No "leads by N years" column or sentence.
 *   - No sum, mean, or count of timestamps.
 *   - No aggregate directional claim.
 */
import type { PairIndicator } from "@/lib/te-mock/patterns-v4-pair-detail-mock";
import { NEUTRAL_SLATE } from "@/lib/te-mock/l1-families";

interface PairIndicatorsPanelProps {
  countryA: string;
  countryB: string;
  indicators: PairIndicator[];
}

export function PairIndicatorsPanel({
  countryA,
  countryB,
  indicators,
}: PairIndicatorsPanelProps) {
  const top8 = indicators.slice(0, 8);

  return (
    <div
      data-tour="pair-indicators"
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "10px",
        padding: "20px 22px",
        marginBottom: "20px",
      }}
    >
      {/* Panel header */}
      <div style={{ marginBottom: "14px" }}>
        <div
          style={{
            fontSize: "9px",
            letterSpacing: "1.6px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            marginBottom: "4px",
            fontWeight: 600,
          }}
        >
          SHARED INDICATORS
          {/* Tooltip anchor for panel-level disclaimer */}
          <TooltipInline
            content="This is a decomposition of the score for this pair, not a discrimination test against other pairs."
            aria-label="Panel note: decomposition, not discrimination test"
          />
        </div>
        <h2
          style={{
            fontSize: "15px",
            fontWeight: 700,
            margin: "0 0 6px",
            color: "var(--qgi-text)",
          }}
        >
          What the resemblance was made of
        </h2>
        <p
          style={{
            fontSize: "11px",
            color: "var(--qgi-text-dim)",
            margin: 0,
            lineHeight: 1.5,
            maxWidth: "640px",
          }}
        >
          Indicators that contributed most to the resemblance between {countryA} and{" "}
          {countryB} across the window. Contribution is how much each indicator&apos;s
          parallel movement loaded into the pair-strength score, not how well the
          indicator predicts anything.
        </p>
      </div>

      {/* Column headers */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 90px 120px 100px",
          gap: "8px",
          paddingBottom: "6px",
          borderBottom: "1px solid var(--qgi-border)",
          marginBottom: "4px",
        }}
      >
        <span style={colHeaderStyle}>INDICATOR</span>
        <span style={{ ...colHeaderStyle, textAlign: "right" as const }}>
          CONTRIBUTION
        </span>
        <span style={{ ...colHeaderStyle, textAlign: "center" as const }}>
          {countryA.toUpperCase().slice(0, 3)} THRESHOLD
        </span>
        <span style={{ ...colHeaderStyle, textAlign: "center" as const }}>
          {countryB.toUpperCase().slice(0, 3)} THRESHOLD
        </span>
      </div>

      {/* Rows */}
      <div style={{ display: "flex", flexDirection: "column", gap: "0" }}>
        {top8.map((ind) => (
          <IndicatorRow
            key={ind.code}
            indicator={ind}
            countryA={countryA}
            countryB={countryB}
          />
        ))}
      </div>
    </div>
  );
}

function IndicatorRow({
  indicator,
  countryA,
  countryB,
}: {
  indicator: PairIndicator;
  countryA: string;
  countryB: string;
}) {
  const barWidth = Math.round(indicator.contributionPct * 0.8); // max 80px
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 90px 120px 100px",
        gap: "8px",
        alignItems: "center",
        padding: "8px 0",
        borderBottom: "1px solid var(--qgi-border)",
      }}
    >
      {/* Indicator name + provider */}
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span
            style={{
              fontSize: "12px",
              fontWeight: 600,
              color: "var(--qgi-text)",
              lineHeight: 1.3,
            }}
          >
            {indicator.name}
          </span>
          <TooltipInline
            content={indicator.thresholdDefinition}
            aria-label={`Threshold definition for ${indicator.name}`}
          />
        </div>
        <span
          style={{
            fontSize: "10px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.3px",
          }}
        >
          {indicator.provider}
        </span>
      </div>

      {/* Magnitude bar + pct */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "6px",
          justifyContent: "flex-end",
        }}
      >
        <div
          style={{
            width: "60px",
            height: "5px",
            background: "var(--qgi-border)",
            borderRadius: "3px",
            overflow: "hidden",
            flexShrink: 0,
          }}
        >
          <div
            style={{
              width: `${barWidth}px`,
              height: "100%",
              background: NEUTRAL_SLATE,
              borderRadius: "3px",
            }}
          />
        </div>
        <span
          style={{
            fontSize: "11px",
            fontFamily: "ui-monospace, monospace",
            color: "var(--qgi-text)",
            fontWeight: 600,
            minWidth: "28px",
            textAlign: "right",
          }}
        >
          {indicator.contributionPct}%
        </span>
      </div>

      {/* Country A crossing year */}
      <div style={{ textAlign: "center" as const }}>
        <span
          style={{
            fontSize: "12px",
            fontFamily: "ui-monospace, monospace",
            color: "var(--qgi-text)",
            fontWeight: 600,
          }}
        >
          {indicator.crossingYearA}
        </span>
      </div>

      {/* Country B crossing year */}
      <div style={{ textAlign: "center" as const }}>
        <span
          style={{
            fontSize: "12px",
            fontFamily: "ui-monospace, monospace",
            color: "var(--qgi-text)",
            fontWeight: 600,
          }}
        >
          {indicator.crossingYearB}
        </span>
      </div>
    </div>
  );
}

/**
 * Minimal tooltip anchor: an (i) marker that sets title attribute.
 * Uses native title for accessibility without a dependency.
 */
function TooltipInline({
  content,
  "aria-label": ariaLabel,
}: {
  content: string;
  "aria-label": string;
}) {
  return (
    <span
      title={content}
      aria-label={ariaLabel}
      role="img"
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: "13px",
        height: "13px",
        borderRadius: "50%",
        border: "1px solid var(--qgi-border)",
        color: "var(--qgi-text-dim)",
        fontSize: "8px",
        cursor: "help",
        flexShrink: 0,
        fontFamily: "ui-monospace, monospace",
        userSelect: "none",
      }}
    >
      i
    </span>
  );
}

const colHeaderStyle: React.CSSProperties = {
  fontSize: "9px",
  letterSpacing: "0.8px",
  color: "var(--qgi-text-dim)",
  fontFamily: "ui-monospace, monospace",
  fontWeight: 600,
};
