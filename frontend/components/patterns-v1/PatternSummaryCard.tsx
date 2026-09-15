"use client";

import dynamic from "next/dynamic";
import { sectorColor, sectorChipBg } from "@/lib/design";
import { CountryFlag } from "@/components/design/CountryFlag";
import { InfoTooltip } from "@/components/design/InfoTooltip";
import countriesList from "@/data/countries.json";

// Build name -> alpha_2 lookup
const NAME_TO_ALPHA2: Record<string, string> = {};
for (const c of countriesList as Array<{ name: string; alpha_2: string }>) {
  NAME_TO_ALPHA2[c.name] = c.alpha_2;
}

const SectorRose = dynamic(
  () => import("@/components/charts/SectorRose").then((m) => m.SectorRose),
  { ssr: false }
);

interface ScdiRow {
  index_name: string;
  sector: string;
  org: string;
  correlation: number;
  predicted: boolean;
}

interface Meta {
  country_a: string;
  country_b: string;
  start_year_a: string;
  start_year_b: string;
  pattern_length: string;
  avg_correlation: string;
  pattern_power_score: string;
  num_indexes: string;
  predicted: string;
}

interface Props {
  meta: Meta;
  scdis: ScdiRow[];
  isEarlyWarning: boolean;
}

// #126: SECTOR_COLORS moved to lib/design.ts — import from there.

export function PatternSummaryCard({ meta, scdis, isEarlyWarning }: Props) {
  const len = Number(meta.pattern_length);
  const pps = Number(meta.pattern_power_score);
  const corr = Number(meta.avg_correlation);
  const lag = Number(meta.start_year_b) - Number(meta.start_year_a);

  // Sector breakdown for rose chart
  const sectorCounts: Record<string, number> = {};
  for (const s of scdis) {
    sectorCounts[s.sector] = (sectorCounts[s.sector] ?? 0) + 1;
  }
  const sectorData = Object.entries(sectorCounts).map(([name, value]) => ({
    name,
    value,
  }));

  return (
    <div className="flex flex-col gap-0">
      {/* Early Warning Banner */}
      {isEarlyWarning && (
        <div
          className="flex items-center gap-3 px-5 py-2.5 text-xs font-semibold"
          style={{
            backgroundColor: "rgba(248, 113, 113, 0.12)",
            borderBottom: "1px solid #f87171",
          }}
        >
          <span style={{ color: "#f87171" }}>⚡ EARLY WARNING SIGNAL</span>
          <span style={{ color: "var(--qgi-text-muted)", fontWeight: 400 }}>
            Predictor country is currently in its historical window. Following country may
            be entering {meta.country_a}&apos;s past trajectory
          </span>
        </div>
      )}

      {/* 5-column summary */}
      <div
        className="grid grid-cols-5 border-b"
        style={{ borderColor: "var(--qgi-border)" }}
      >
        {/* Col 1: Predictor info */}
        <div
          className="flex flex-col justify-center px-5 py-4 border-r gap-1"
          style={{ borderColor: "var(--qgi-border)" }}
        >
          <span
            className="text-[9px] tracking-widest uppercase"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Predictor
          </span>
          <CountryFlag alpha2={NAME_TO_ALPHA2[meta.country_a] ?? ""} size={28} />
          <span
            className="font-data text-xl font-semibold"
            style={{ color: "var(--qgi-country-a)" }}
          >
            {meta.country_a}
          </span>
          <span className="text-xs font-data" style={{ color: "var(--qgi-text-muted)" }}>
            {meta.start_year_a}–{Number(meta.start_year_a) + len - 1}
          </span>
        </div>

        {/* Col 2: Arrow */}
        <div
          className="flex flex-col items-center justify-center px-4 py-4 border-r gap-1"
          style={{ borderColor: "var(--qgi-border)" }}
        >
          <span className="text-2xl" style={{ color: "var(--qgi-text-dim)" }}>
            →
          </span>
          <span className="font-data text-xs" style={{ color: "var(--qgi-text-muted)" }}>
            {len} yrs
          </span>
          {lag !== 0 && (
            <span className="text-[10px]" style={{ color: "var(--qgi-text-dim)" }}>
              {lag > 0 ? `+${lag}` : lag} yr offset
            </span>
          )}
        </div>

        {/* Col 3: PPS + sector rose */}
        <div
          className="flex flex-col items-center justify-center px-4 py-2 border-r gap-1"
          style={{ borderColor: "var(--qgi-border)" }}
        >
          <span
            className="text-[9px] tracking-widest uppercase flex items-center"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Pattern Strength
            <InfoTooltip text="Pattern strength: a composite ranking metric blending correlation, pattern length, and indicator coverage. Higher = more historically grounded match. Range 0–2000+." />
          </span>
          <span
            className="font-data text-3xl font-semibold"
            style={{ color: "var(--qgi-amber)" }}
          >
            {pps.toFixed(3)}
          </span>
          <span
            className="text-[10px] font-data"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            {(corr * 100).toFixed(1)}% avg corr · {meta.num_indexes} indicators
          </span>
          {/* Sector rose — needs enough height for labels to render.
              ECharts auto-hides labels that don't fit. */}
          <div className="w-full h-32">
            <SectorRose data={sectorData} />
          </div>
        </div>

        {/* Col 4: Following */}
        <div
          className="flex flex-col justify-center px-5 py-4 border-r gap-1"
          style={{ borderColor: "var(--qgi-border)" }}
        >
          <span
            className="text-[9px] tracking-widest uppercase"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Following
          </span>
          <CountryFlag alpha2={NAME_TO_ALPHA2[meta.country_b] ?? ""} size={28} />
          <span
            className="font-data text-xl font-semibold"
            style={{ color: "var(--qgi-country-b)" }}
          >
            {meta.country_b}
          </span>
          <span className="text-xs font-data" style={{ color: "var(--qgi-text-muted)" }}>
            {meta.start_year_b}–{Number(meta.start_year_b) + len - 1}
          </span>
        </div>

        {/* Col 5: Sector chips */}
        <div className="flex flex-col justify-center px-4 py-4 gap-1.5 overflow-y-auto">
          <span
            className="text-[9px] tracking-widest uppercase"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Sectors
          </span>
          {sectorData
            .sort((a, b) => b.value - a.value)
            .map((s) => (
              <div key={s.name} className="flex items-center gap-2">
                <span
                  className="text-[9px] rounded px-1.5 py-0.5"
                  style={{
                    color: sectorColor(s.name),
                    backgroundColor: sectorChipBg(s.name),
                  }}
                >
                  {s.name.toUpperCase()}
                </span>
                <span
                  className="font-data text-[10px]"
                  style={{ color: "var(--qgi-text-dim)" }}
                >
                  {s.value}
                </span>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}
