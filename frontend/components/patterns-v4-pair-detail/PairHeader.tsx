/**
 * PairHeader -- §1 header band for /patterns/[slug].
 *
 * Symmetric: no leader/follower framing, no status chip, no arrow between
 * country names. Both countries treated identically.
 * Uses ↔ as the only relation symbol between country names.
 */
import type { ReactNode } from "react";
import Link from "next/link";
import type { Route } from "next";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
// Use the canonical flag lookup directly — no dependency on any -mock module
// (the pattern detail route is zero-mock). flagFor is the same lookup the
// former pairDetailFlagFor wrapper delegated to.
import { flagFor } from "@/lib/te-mock/country-flags";

interface PairHeaderProps {
  countryA: string;
  countryB: string;
  iso2A: string;
  iso2B: string;
  startYear: number;
  endYear: number;
  windowLength: number;
  sharedIndicatorCount: number;
  /** Slot for HowToReadButton placed far-right in the breadcrumb row. */
  headerRightSlot?: ReactNode;
}

export function PairHeader({
  countryA,
  countryB,
  iso2A,
  iso2B,
  startYear,
  endYear,
  windowLength,
  sharedIndicatorCount,
  headerRightSlot,
}: PairHeaderProps) {
  return (
    <div
      data-tour="pair-header"
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "10px",
        padding: "20px 24px 24px",
        marginBottom: "20px",
      }}
    >
      {/* Breadcrumb row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "16px",
          flexWrap: "wrap",
          gap: "8px",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            fontSize: "11px",
            color: "var(--qgi-text-muted)",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          <Link
            href={"/patterns" as Route}
            style={{ color: "var(--qgi-accent)", textDecoration: "none" }}
          >
            Patterns
          </Link>
          <span style={{ color: "var(--qgi-text-dim)" }}>/</span>
          <span style={{ color: "var(--qgi-text-dim)" }}>Pair</span>
          <span style={{ color: "var(--qgi-text-dim)" }}>/</span>
          <span style={{ color: "var(--qgi-text)" }}>
            {countryA} ↔ {countryB}
          </span>
        </div>
        {headerRightSlot && <div>{headerRightSlot}</div>}
      </div>

      {/* Dual-flag icon row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          marginBottom: "14px",
        }}
      >
        {/* Overlapping flag pair */}
        <div
          style={{
            position: "relative",
            width: "88px",
            height: "66px",
            flexShrink: 0,
          }}
        >
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              width: "60px",
              height: "45px",
              border: "2px solid #7A8FA0",
              borderRadius: "4px",
              overflow: "hidden",
              zIndex: 2,
            }}
          >
            <FlagImg emoji={flagFor(countryA)} name={countryA} width={60} radius={2} />
          </div>
          <div
            style={{
              position: "absolute",
              bottom: 0,
              right: 0,
              width: "60px",
              height: "45px",
              border: "2px solid #7A8FA0",
              borderRadius: "4px",
              overflow: "hidden",
              zIndex: 1,
            }}
          >
            <FlagImg emoji={flagFor(countryB)} name={countryB} width={60} radius={2} />
          </div>
        </div>

        {/* Title block */}
        <div style={{ flex: 1 }}>
          {/* Flag + name row */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              flexWrap: "wrap",
              marginBottom: "6px",
            }}
          >
            <FlagImg emoji={flagFor(countryA)} name={countryA} width={20} radius={2} />
            <span
              style={{
                fontSize: "14px",
                fontWeight: 600,
                color: "var(--qgi-text-muted)",
              }}
            >
              {countryA}
            </span>
            <span
              style={{
                fontSize: "15px",
                color: "var(--qgi-text-dim)",
                fontFamily: "ui-monospace, monospace",
                userSelect: "none",
              }}
            >
              ↔
            </span>
            <FlagImg emoji={flagFor(countryB)} name={countryB} width={20} radius={2} />
            <span
              style={{
                fontSize: "14px",
                fontWeight: 600,
                color: "var(--qgi-text-muted)",
              }}
            >
              {countryB}
            </span>
          </div>

          {/* H1 */}
          <h1
            style={{
              fontSize: "clamp(20px, 3.5vw, 30px)",
              fontWeight: 800,
              margin: "0 0 6px",
              color: "var(--qgi-text)",
              lineHeight: 1.15,
            }}
          >
            {countryA} ↔ {countryB}, {startYear}
            {"–"}
            {endYear}
          </h1>

          {/* Subtitle */}
          <p
            style={{
              fontSize: "15px",
              color: "var(--qgi-text-muted)",
              margin: "0 0 8px",
            }}
          >
            A shared {windowLength}-year trajectory across {sharedIndicatorCount}{" "}
            indicators.
          </p>
        </div>
      </div>

      {/* Lede */}
      <p
        style={{
          fontSize: "15px",
          color: "var(--qgi-text)",
          maxWidth: "720px",
          lineHeight: 1.65,
          margin: 0,
          paddingLeft: "2px",
        }}
      >
        These two countries&apos; indicator trajectories ran in close parallel from{" "}
        {startYear} to {endYear}. What follows is the resemblance and what each country
        looks like today. The page does not say which country is leading which.
      </p>
    </div>
  );
}
