/**
 * TrendsBriefing — compact Trends catalog status.
 *
 * Wraps ClosestMatches with a stat bar at the top showing in-play count,
 * total trends, and family count.
 *
 * Server component — wraps ClosestMatches (server).
 */
import Link from "next/link";
import type { Route } from "next";
import { PanelBase } from "@/components/dashboard-v4-1/PanelBase";
import { ClosestMatches } from "@/components/dashboard-v4-1/ClosestMatches";
import type { ClosestMatch } from "@/lib/te-mock/dashboard-v4-1-data";

interface TrendsBriefingProps {
  matches: ClosestMatch[];
  inPlayCount: number;
  recipesTotal: number;
  familyCount: number;
  vintageQuarter: string;
}

export function TrendsBriefing({
  matches,
  inPlayCount,
  recipesTotal,
  familyCount,
  vintageQuarter,
}: TrendsBriefingProps) {
  const vintageChip = (
    <span
      style={{
        fontSize: "10px",
        padding: "2px 8px",
        borderRadius: "3px",
        background: "rgba(123,94,230,0.12)",
        border: "1px solid rgba(123,94,230,0.3)",
        color: "var(--qgi-text-dim)",
        fontFamily: "ui-monospace, monospace",
        letterSpacing: "0.4px",
        whiteSpace: "nowrap",
      }}
    >
      {vintageQuarter}
    </span>
  );

  const rightSlot = (
    <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
      {vintageChip}
      <Link
        href={"/trends" as Route}
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: "11px",
          color: "#7B5EE6",
          textDecoration: "none",
        }}
      >
        Browse all →
      </Link>
    </div>
  );

  return (
    <PanelBase
      title={`Trends In Play · ${vintageQuarter}`}
      accent="#7B5EE6"
      rightSlot={rightSlot}
    >
      {/* Stat bar */}
      <div
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: "11px",
          color: "var(--qgi-text-dim)",
          marginBottom: "10px",
          display: "flex",
          gap: "6px",
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        <span style={{ color: "var(--qgi-text)", fontWeight: 700 }}>{inPlayCount}</span>
        <span>in play</span>
        <span style={{ color: "var(--qgi-border)" }}>·</span>
        <span style={{ color: "var(--qgi-text)", fontWeight: 700 }}>{recipesTotal}</span>
        <span>total trends</span>
        <span style={{ color: "var(--qgi-border)" }}>·</span>
        <span style={{ color: "var(--qgi-text)", fontWeight: 700 }}>{familyCount}</span>
        <span>families</span>
      </div>

      {/* Editorial lead line */}
      <p
        style={{
          fontSize: "12px",
          color: "var(--qgi-text-muted)",
          lineHeight: 1.55,
          margin: "0 0 16px",
          fontStyle: "italic",
        }}
      >
        Countries whose current structural readings most closely trace a documented event
        pattern. Each score measures resemblance to a real historical precedent — not a
        probability of occurrence.
      </p>

      <ClosestMatches matches={matches} />
    </PanelBase>
  );
}
