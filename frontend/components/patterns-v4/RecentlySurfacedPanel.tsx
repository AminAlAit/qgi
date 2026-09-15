"use client";

/**
 * RecentlySurfacedPanel — Section 7: recently surfaced pairs.
 *
 * 6 small cards: pairs newly added this vintage or whose strength climbed
 * most since the last vintage. Mirrors RecentMovements on /risk-board.
 */
import Link from "next/link";
import type { Route } from "next";
import { TrendingUp } from "lucide-react";
import type { RecentlySurfacedPair } from "@/lib/te-mock/patterns-v4-main-data";
import { pairFlagFor } from "@/lib/te-mock/patterns-v4-main-data";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { NEUTRAL_SLATE } from "@/lib/te-mock/l1-families";

interface RecentlySurfacedPanelProps {
  pairs: RecentlySurfacedPair[];
}

export function RecentlySurfacedPanel({ pairs }: RecentlySurfacedPanelProps) {
  return (
    <div
      data-tour="patterns-recently-surfaced"
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "10px",
        padding: "20px 22px",
        marginTop: "24px",
      }}
    >
      {/* Header */}
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
        RECENTLY SURFACED
      </div>
      <h2
        style={{
          fontSize: "16px",
          fontWeight: 700,
          margin: "0 0 16px",
          color: "var(--qgi-text)",
        }}
      >
        New and rising pairs
      </h2>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
          gap: "10px",
        }}
      >
        {pairs.map((pair) => (
          <SurfacedCard key={pair.pair_id} pair={pair} />
        ))}
      </div>
    </div>
  );
}

function SurfacedCard({ pair }: { pair: RecentlySurfacedPair }) {
  const isNew = pair.surfaced_reason === "new_this_vintage";
  const delta =
    !isNew && pair.prior_strength !== undefined
      ? pair.pair_strength - pair.prior_strength
      : null;

  return (
    <Link
      href={`/patterns/${pair.pair_id}` as Route}
      style={{ textDecoration: "none", color: "inherit" }}
    >
      <div
        style={{
          background: "var(--qgi-bg)",
          border: "1px solid var(--qgi-border)",
          borderRadius: "7px",
          padding: "13px 14px",
          cursor: "pointer",
          transition: "border-color 0.12s",
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLElement).style.borderColor = "var(--qgi-accent)";
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLElement).style.borderColor = "var(--qgi-border)";
        }}
      >
        {/* Reason badge */}
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "4px",
            padding: "2px 7px",
            borderRadius: "3px",
            background: isNew ? "rgba(63,191,143,0.12)" : "rgba(56,189,248,0.12)",
            border: `1px solid ${isNew ? "rgba(63,191,143,0.35)" : "rgba(56,189,248,0.35)"}`,
            fontSize: "9.5px",
            color: isNew ? "#3FBF8F" : "var(--qgi-accent)",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.4px",
            marginBottom: "8px",
          }}
        >
          {isNew ? (
            "NEW THIS RELEASE"
          ) : (
            <>
              <TrendingUp size={9} strokeWidth={2} />
              ROSE IN RANK
            </>
          )}
        </div>

        {/* Pair */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            flexWrap: "wrap",
            marginBottom: "8px",
          }}
        >
          <FlagImg
            emoji={pairFlagFor(pair.country_a_name)}
            name={pair.country_a_name}
            width={15}
          />
          <span style={{ fontSize: "13px", fontWeight: 600, color: "var(--qgi-text)" }}>
            {pair.country_a_name}
          </span>
          <span
            style={{
              fontSize: "12px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            ↔
          </span>
          <FlagImg
            emoji={pairFlagFor(pair.country_b_name)}
            name={pair.country_b_name}
            width={15}
          />
          <span style={{ fontSize: "13px", fontWeight: 600, color: "var(--qgi-text)" }}>
            {pair.country_b_name}
          </span>
        </div>

        {/* Stats row */}
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div
            style={{
              width: "48px",
              height: "5px",
              background: "var(--qgi-border)",
              borderRadius: "3px",
              overflow: "hidden",
              flexShrink: 0,
            }}
          >
            <div
              style={{
                width: `${Math.round((pair.pair_strength / 100) * 48)}px`,
                height: "100%",
                background: NEUTRAL_SLATE,
                borderRadius: "3px",
              }}
            />
          </div>
          <span
            style={{
              fontSize: "13px",
              fontFamily: "ui-monospace, monospace",
              color: "var(--qgi-text)",
              fontWeight: 700,
            }}
          >
            {pair.pair_strength}
          </span>
          {delta !== null && (
            <span
              style={{
                fontSize: "11px",
                fontFamily: "ui-monospace, monospace",
                color: delta > 0 ? "#3FBF8F" : "#E64545",
              }}
            >
              {delta > 0 ? "+" : ""}
              {delta}
            </span>
          )}
          <span
            style={{
              fontSize: "11px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
              marginLeft: "auto",
            }}
          >
            {pair.window_years}y
          </span>
        </div>
      </div>
    </Link>
  );
}
