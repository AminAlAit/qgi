"use client";
/**
 * TrendRail — horizontal scrolling rail of ClosestMatch cards.
 * "use client" for scroll arrow nav.
 */
import { useRef } from "react";
import Link from "next/link";
import type { Route } from "next";
import type { ClosestMatch } from "@/lib/te-mock/dashboard-v4-1-data";
import { TrendRailCard } from "./TrendRailCard";

interface Props {
  matches: ClosestMatch[];
  inPlayCount: number;
}

export function TrendRail({ matches, inPlayCount }: Props) {
  const railRef = useRef<HTMLDivElement>(null);

  if (matches.length === 0) return null;

  function scrollBy(dir: -1 | 1) {
    if (!railRef.current) return;
    railRef.current.scrollBy({ left: dir * 240, behavior: "smooth" });
  }

  return (
    <section style={{ marginTop: "0" }}>
      <style>{`
        .qgi-trend-rail-card:hover {
          transform: translateY(-3px);
          box-shadow: 0 8px 24px rgba(0,0,0,0.35);
        }
        .qgi-trend-rail::-webkit-scrollbar { display: none; }
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
            On the radar right now
          </h2>
          <p
            style={{
              fontSize: "13px",
              color: "var(--qgi-text-muted)",
              margin: 0,
              lineHeight: 1.5,
            }}
          >
            Structural resemblance — not forecasts, precedents.
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
        {/* Right-edge fade — signals that the rail is horizontally scrollable */}
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
          className="qgi-trend-rail"
          style={{
            display: "flex",
            gap: "12px",
            overflowX: "auto",
            scrollbarWidth: "none",
            paddingBottom: "4px",
          }}
        >
          {matches.map((m, i) => (
            <TrendRailCard key={`${m.recipe_id}-${m.country}-${i}`} match={m} />
          ))}
        </div>

        {/* Right arrow — always rendered; sits above the fade mask */}
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
