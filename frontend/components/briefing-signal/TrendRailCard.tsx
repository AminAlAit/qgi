/**
 * TrendRailCard — individual closest-match card inside the TrendRail.
 * Pure JSX, no hooks. Used by TrendRail ("use client") but is itself pure.
 */
import Link from "next/link";
import type { Route } from "next";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import { MiniSparkline } from "@/components/countries-v4-1/MiniSparkline";
import { MUTED_GRAY, confidenceT, lerpHexToRgb } from "@/lib/color-lerp";
import type { ClosestMatch } from "@/lib/te-mock/dashboard-v4-1-data";

export function TrendRailCard({ match }: { match: ClosestMatch }) {
  const t = confidenceT(match.score);
  const scoreColor = lerpHexToRgb(MUTED_GRAY, match.l1_color, t);

  return (
    <Link
      href={`/trends/${match.recipe_id}/countries/${match.iso2}` as Route}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "10px",
        padding: "14px",
        textDecoration: "none",
        color: "inherit",
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderLeft: `3px solid ${match.l1_color}`,
        borderRadius: "8px",
        width: "220px",
        minWidth: "220px",
        height: match.zone_label ? "200px" : "160px",
        boxSizing: "border-box",
        flexShrink: 0,
        transition: "transform 140ms ease, box-shadow 140ms ease",
      }}
      className="qgi-trend-rail-card"
    >
      {/* Country + Recipe */}
      <div style={{ display: "flex", alignItems: "center", gap: "6px", minWidth: 0 }}>
        <FlagImg
          emoji={flagFor(match.country)}
          name={match.country}
          width={22}
          radius={2}
        />
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              fontSize: "14px",
              fontWeight: 600,
              color: "var(--qgi-text)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {match.country}
          </div>
          <div
            style={{
              fontSize: "11px",
              color: "var(--qgi-text-muted)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {match.recipe_label}
          </div>
        </div>
      </div>

      {/* Score + Sparkline row */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "space-between",
        }}
      >
        <span
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "36px",
            fontWeight: 700,
            color: scoreColor,
            letterSpacing: "-1px",
            lineHeight: 1,
          }}
        >
          {Math.round(match.score)}
        </span>
        {match.composite.length > 0 && (
          <div style={{ marginBottom: "2px" }}>
            <MiniSparkline
              values={match.composite}
              width={80}
              height={28}
              color={match.l1_color}
            />
          </div>
        )}
      </div>

      {/* Zone label — always shown; fallback placeholder when absent */}
      <div
        style={{
          fontSize: "11px",
          color: match.zone_label ? "var(--qgi-text-dim)" : "var(--qgi-text-dim)",
          lineHeight: 1.4,
          overflow: "hidden",
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
          marginTop: "auto",
          opacity: match.zone_label ? 1 : 0.45,
        }}
      >
        {match.zone_label
          ? match.zone_label.replace(
              /\bcrisis(?=\s+profile\b)/i,
              match.recipe_label.toLowerCase()
            )
          : "Trajectory data pending"}
      </div>
    </Link>
  );
}
