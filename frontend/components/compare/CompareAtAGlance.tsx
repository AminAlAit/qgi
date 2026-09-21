/**
 * CompareAtAGlance — four neutral tiles, each split A | B.
 *
 * Tiles: Recipes in play / Lit families / Top recipe rank gap / Overlap.
 * NEUTRAL_SLATE magnitude bars normalized within each tile.
 * Marcus mitigation 2 (inline caption on "Recipes in play" tile) is
 * rendered as a permanent, visible note, not a tooltip.
 *
 * V4.1 bar: no em-dashes, no banned vocab.
 */
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { NEUTRAL_SLATE } from "@/lib/te-mock/l1-families";
import type { CountryV4 } from "@/lib/te-mock/countries-v4-data";
import type { AtAGlance } from "@/lib/te-mock/compare-data";

function SplitTile({
  label,
  captionNode,
  countryA,
  countryB,
  valueA,
  valueB,
  formattedA,
  formattedB,
  tooltip,
}: {
  label: string;
  captionNode?: React.ReactNode;
  countryA: CountryV4;
  countryB: CountryV4;
  valueA: number;
  valueB: number;
  formattedA: string;
  formattedB: string;
  tooltip?: string;
}) {
  const max = Math.max(valueA, valueB, 1);
  const barA = (valueA / max) * 100;
  const barB = (valueB / max) * 100;

  return (
    <div
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "6px",
        padding: "14px 16px 12px",
        minWidth: 0,
        display: "flex",
        flexDirection: "column",
        gap: "10px",
      }}
      title={tooltip}
    >
      {/* Tile label */}
      <div
        style={{
          fontSize: "10px",
          letterSpacing: "0.7px",
          textTransform: "uppercase",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
          fontWeight: 600,
        }}
      >
        {label}
      </div>

      {/* Marcus mitigation 2 — inline visible caption for "Recipes in play" */}
      {captionNode && (
        <p
          style={{
            fontSize: "11px",
            lineHeight: 1.5,
            color: "var(--qgi-text-dim)",
            margin: 0,
            fontFamily: "ui-monospace, monospace",
          }}
        >
          {captionNode}
        </p>
      )}

      {/* Two-column halves */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
        {/* Country A half */}
        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <FlagImg emoji={countryA.flag_emoji} name={countryA.name} width={14} />
            <span
              style={{
                fontSize: "10px",
                color: "var(--qgi-text-dim)",
                fontFamily: "ui-monospace, monospace",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {countryA.iso}
            </span>
          </div>
          <span
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: "22px",
              fontWeight: 700,
              color: "var(--qgi-text)",
              lineHeight: 1,
            }}
          >
            {formattedA}
          </span>
          {/* Magnitude bar */}
          <div
            style={{
              height: "3px",
              background: "var(--qgi-border)",
              borderRadius: "2px",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${barA}%`,
                height: "100%",
                background: NEUTRAL_SLATE,
                borderRadius: "2px",
              }}
            />
          </div>
        </div>

        {/* Country B half */}
        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <FlagImg emoji={countryB.flag_emoji} name={countryB.name} width={14} />
            <span
              style={{
                fontSize: "10px",
                color: "var(--qgi-text-dim)",
                fontFamily: "ui-monospace, monospace",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {countryB.iso}
            </span>
          </div>
          <span
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: "22px",
              fontWeight: 700,
              color: "var(--qgi-text)",
              lineHeight: 1,
            }}
          >
            {formattedB}
          </span>
          <div
            style={{
              height: "3px",
              background: "var(--qgi-border)",
              borderRadius: "2px",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${barB}%`,
                height: "100%",
                background: NEUTRAL_SLATE,
                borderRadius: "2px",
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

export function CompareAtAGlance({
  countryA,
  countryB,
  glance,
}: {
  countryA: CountryV4;
  countryB: CountryV4;
  glance: AtAGlance;
}) {
  const gapLabel = glance.top_rank_gap_recipe
    ? `+${glance.top_rank_gap} on ${glance.top_rank_gap_recipe}`
    : `${glance.top_rank_gap}`;

  return (
    <div
      data-tour="compare-at-a-glance"
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
        gap: "12px",
      }}
    >
      <SplitTile
        label="Trends in play"
        captionNode="More trends in play is not more risk. Each trend is a distinct structural pattern; the count tells you how many patterns currently match, not how strongly the country is at risk."
        countryA={countryA}
        countryB={countryB}
        valueA={glance.recipes_a}
        valueB={glance.recipes_b}
        formattedA={String(glance.recipes_a)}
        formattedB={String(glance.recipes_b)}
      />
      {/* V4.1 §1.3: "Lit families" → "Matched categories"; "L1" removed from tooltip. */}
      <SplitTile
        label="Matched categories"
        countryA={countryA}
        countryB={countryB}
        valueA={glance.lit_families_a}
        valueB={glance.lit_families_b}
        formattedA={String(glance.lit_families_a)}
        formattedB={String(glance.lit_families_b)}
        tooltip="Distinct risk categories each country currently matches."
      />
      <SplitTile
        label="Top trend rank gap"
        countryA={countryA}
        countryB={countryB}
        valueA={glance.top_rank_gap}
        valueB={0}
        formattedA={gapLabel}
        formattedB="shared trend"
        tooltip="Largest single-trend rank gap between A and B on any shared trend."
      />
      <SplitTile
        label="Overlap"
        countryA={countryA}
        countryB={countryB}
        valueA={glance.overlap_count}
        valueB={glance.overlap_count}
        formattedA={String(glance.overlap_count)}
        formattedB="shared trends"
        tooltip="Count of trends both countries are in play on simultaneously."
      />
    </div>
  );
}
