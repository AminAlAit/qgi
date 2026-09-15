/**
 * OverviewTiles — Section 2: three inline catalogue-at-a-glance tiles.
 *
 * Total pairs / median window length / longest pair.
 * Sits inside the hero block, just under the lede.
 */
import type { PairRow } from "@/lib/te-mock/patterns-v4-main-data";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { pairFlagFor } from "@/lib/te-mock/patterns-v4-main-data";

interface OverviewTilesProps {
  totalPairs: number;
  medianWindowYears: number;
  longestPair: PairRow;
}

export function OverviewTiles({
  totalPairs,
  medianWindowYears,
  longestPair,
}: OverviewTilesProps) {
  return (
    <div
      data-tour="patterns-overview-tiles"
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
        gap: "12px",
        marginTop: "20px",
      }}
    >
      <Tile
        label="PAIRS ON FILE"
        value={String(totalPairs)}
        sub="country pairs in the catalogue"
      />
      <Tile
        label="MEDIAN WINDOW"
        value={`${medianWindowYears} years`}
        sub="median run length across all pairs"
      />
      <LongestTile pair={longestPair} />
    </div>
  );
}

function Tile({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "8px",
        padding: "16px 18px",
      }}
    >
      <div
        style={{
          fontSize: "9px",
          letterSpacing: "1.6px",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
          marginBottom: "8px",
          fontWeight: 600,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: "28px",
          fontWeight: 700,
          color: "var(--qgi-text)",
          lineHeight: 1.1,
          marginBottom: "6px",
          fontFamily: "ui-monospace, monospace",
        }}
      >
        {value}
      </div>
      <div style={{ fontSize: "11px", color: "var(--qgi-text-muted)", lineHeight: 1.4 }}>
        {sub}
      </div>
    </div>
  );
}

function LongestTile({ pair }: { pair: PairRow }) {
  return (
    <div
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "8px",
        padding: "16px 18px",
      }}
    >
      <div
        style={{
          fontSize: "9px",
          letterSpacing: "1.6px",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
          marginBottom: "8px",
          fontWeight: 600,
        }}
      >
        LONGEST PAIR ON RECORD
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          marginBottom: "6px",
          flexWrap: "wrap",
        }}
      >
        <FlagImg
          emoji={pairFlagFor(pair.country_a_name)}
          name={pair.country_a_name}
          width={18}
        />
        <span style={{ fontSize: "14px", fontWeight: 600, color: "var(--qgi-text)" }}>
          {pair.country_a_name}
        </span>
        <span
          style={{
            fontSize: "13px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          ↔
        </span>
        <FlagImg
          emoji={pairFlagFor(pair.country_b_name)}
          name={pair.country_b_name}
          width={18}
        />
        <span style={{ fontSize: "14px", fontWeight: 600, color: "var(--qgi-text)" }}>
          {pair.country_b_name}
        </span>
      </div>
      <div
        style={{
          fontSize: "11px",
          color: "var(--qgi-text-muted)",
          fontFamily: "ui-monospace, monospace",
        }}
      >
        {pair.start_year}
        {"–"}
        {pair.end_year} · {pair.window_years} years
      </div>
    </div>
  );
}
