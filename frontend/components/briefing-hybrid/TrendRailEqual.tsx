"use client";
/**
 * TrendRailEqual — On-Radar horizontal rail with ALL cards at equal fixed size.
 *
 * This is a local copy of briefing-signal/TrendRail + TrendRailCard, kept in
 * the briefing-hybrid namespace so we can enforce equal card dimensions without
 * touching the original /briefing-signal component.
 *
 * Equal-size strategy:
 *   - width: fixed 220px (same as original)
 *   - height: fixed 200px for every card (overrides the `match.zone_label`
 *     conditional height from the original). Content clips to fit; no
 *     content-driven size differences.
 */
import { useRef } from "react";
import Link from "next/link";
import type { Route } from "next";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import { MiniSparkline } from "@/components/countries-v4-1/MiniSparkline";
import { MUTED_GRAY, confidenceT, lerpHexToRgb } from "@/lib/color-lerp";
import type { ClosestMatch } from "@/lib/te-mock/dashboard-v4-1-data";

const CARD_WIDTH = 220;
const CARD_HEIGHT = 200; // fixed for all cards

interface Props {
  matches: ClosestMatch[];
  inPlayCount: number;
}

export function TrendRailEqual({ matches, inPlayCount }: Props) {
  const railRef = useRef<HTMLDivElement>(null);

  if (matches.length === 0) return null;

  function scrollBy(dir: -1 | 1) {
    if (!railRef.current) return;
    railRef.current.scrollBy({ left: dir * (CARD_WIDTH + 12), behavior: "smooth" });
  }

  return (
    <section style={{ marginTop: "0" }}>
      <style>{`
        .qgi-bh-rail-card {
          transition: transform 140ms ease, box-shadow 140ms ease;
        }
        .qgi-bh-rail-card:hover {
          transform: translateY(-3px);
          box-shadow: 0 8px 24px rgba(0,0,0,0.35);
        }
        .qgi-bh-rail::-webkit-scrollbar { display: none; }
      `}</style>

      {/* Section header */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          marginBottom: "14px",
          gap: "12px",
          flexWrap: "wrap",
        }}
      >
        <div>
          <h2
            style={{
              fontSize: "20px",
              fontWeight: 600,
              margin: "0 0 4px",
              letterSpacing: "-0.2px",
            }}
          >
            On The Radar Right Now
          </h2>
          <p
            style={{
              fontSize: "13px",
              color: "var(--qgi-text-muted)",
              margin: 0,
              lineHeight: 1.5,
            }}
          >
            Structural resemblance: precedents, not forecasts.
          </p>
        </div>
        <Link
          href={"/trends" as Route}
          style={{
            fontSize: "12px",
            fontFamily: "ui-monospace, monospace",
            color: "var(--qgi-accent)",
            textDecoration: "none",
            whiteSpace: "nowrap",
            alignSelf: "center",
          }}
        >
          → All {inPlayCount} trends
        </Link>
      </div>

      {/* Rail wrapper with nav arrows */}
      <div style={{ position: "relative" }}>
        {/* Right-edge fade */}
        <div
          aria-hidden="true"
          style={{
            position: "absolute",
            top: 0,
            right: 0,
            width: "60px",
            height: "100%",
            background: "linear-gradient(to right, transparent, var(--qgi-bg))",
            pointerEvents: "none",
            zIndex: 5,
          }}
        />

        {/* Left arrow */}
        <button
          onClick={() => scrollBy(-1)}
          aria-label="Scroll left"
          style={{
            position: "absolute",
            left: "-16px",
            top: "50%",
            transform: "translateY(-50%)",
            zIndex: 10,
            width: "32px",
            height: "32px",
            borderRadius: "50%",
            background: "var(--qgi-surface)",
            border: "1px solid var(--qgi-border)",
            color: "var(--qgi-text-muted)",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "14px",
            lineHeight: 1,
          }}
        >
          ←
        </button>

        {/* Rail */}
        <div
          ref={railRef}
          className="qgi-bh-rail"
          style={{
            display: "flex",
            gap: "12px",
            overflowX: "auto",
            scrollbarWidth: "none",
            paddingBottom: "4px",
          }}
        >
          {matches.map((m, i) => (
            <EqualCard key={`${m.recipe_id}-${m.country}-${i}`} match={m} />
          ))}
        </div>

        {/* Right arrow */}
        <button
          onClick={() => scrollBy(1)}
          aria-label="Scroll right"
          style={{
            position: "absolute",
            right: "-16px",
            top: "50%",
            transform: "translateY(-50%)",
            zIndex: 15,
            width: "32px",
            height: "32px",
            borderRadius: "50%",
            background: "var(--qgi-surface)",
            border: "1px solid var(--qgi-border)",
            color: "var(--qgi-text-muted)",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "14px",
            lineHeight: 1,
          }}
        >
          →
        </button>
      </div>
    </section>
  );
}

// ── Utility: strip em-dashes from data-derived strings at render time ─────────
// Replaces " — " (with surrounding spaces) and bare "—" with ", " so no
// em-dash survives regardless of what the source data contains.
function stripEmDash(s: string): string {
  return s.replace(/\s*—\s*/g, ", ");
}

// ── Individual card — fixed 220×200px for every card ─────────────────────────

function EqualCard({ match }: { match: ClosestMatch }) {
  const t = confidenceT(match.score);
  const scoreColor = lerpHexToRgb(MUTED_GRAY, match.l1_color, t);

  return (
    <Link
      href={`/trends/${match.recipe_id}/countries/${match.iso2}` as Route}
      className="qgi-bh-rail-card"
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
        width: `${CARD_WIDTH}px`,
        minWidth: `${CARD_WIDTH}px`,
        height: `${CARD_HEIGHT}px`,
        boxSizing: "border-box",
        flexShrink: 0,
        overflow: "hidden",
      }}
    >
      {/* Country + Recipe */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "6px",
          minWidth: 0,
        }}
      >
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
            {stripEmDash(match.country)}
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
            {stripEmDash(match.recipe_label)}
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

      {/* Zone label — fixed height, clips gracefully */}
      <div
        style={{
          fontSize: "11px",
          color: "var(--qgi-text-dim)",
          lineHeight: 1.4,
          overflow: "hidden",
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
          marginTop: "auto",
          opacity: match.zone_label ? 1 : 0.45,
          flexShrink: 0,
        }}
      >
        {match.zone_label
          ? stripEmDash(
              match.zone_label.replace(
                /\bcrisis(?=\s+profile\b)/i,
                match.recipe_label.toLowerCase()
              )
            )
          : "Trajectory data pending"}
      </div>
    </Link>
  );
}
