"use client";

/**
 * PairTodayPanel -- §6 Both countries today.
 *
 * Two side-by-side cards. Each card:
 *   - Country flag + name
 *   - Link to /countries/{iso}
 *   - One summary sentence: "Currently {Country}'s strongest recipe match
 *     is {recipe}, rank #{n} in the catalogue."
 *
 * HARD constraints (Marcus, binding):
 *   - No sparkline.
 *   - No comparison between the two cards.
 *   - No cross-reading. No "A is where B was."
 *   - Cards do NOT link to each other; only outbound to country profiles.
 */
import Link from "next/link";
import type { Route } from "next";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import type { TodaySummary } from "@/lib/te-mock/patterns-v4-pair-detail-mock";
import { pairDetailFlagFor } from "@/lib/te-mock/patterns-v4-pair-detail-mock";

interface PairTodayPanelProps {
  todayA: TodaySummary;
  todayB: TodaySummary;
}

export function PairTodayPanel({ todayA, todayB }: PairTodayPanelProps) {
  return (
    <div
      data-tour="pair-today"
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "10px",
        padding: "20px 22px",
        marginBottom: "20px",
      }}
    >
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
        BOTH COUNTRIES TODAY
      </div>
      <h2
        style={{
          fontSize: "15px",
          fontWeight: 700,
          margin: "0 0 14px",
          color: "var(--qgi-text)",
        }}
      >
        Where each country stands now
      </h2>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: "16px",
        }}
      >
        <TodayCard summary={todayA} />
        <TodayCard summary={todayB} />
      </div>

      <p
        style={{
          fontSize: "11px",
          color: "var(--qgi-text-dim)",
          margin: "12px 0 0",
          fontStyle: "italic",
          lineHeight: 1.5,
        }}
      >
        Each card links to its country profile. The pair page does not synthesize a
        present-day claim from the historical resemblance.
      </p>
    </div>
  );
}

function TodayCard({ summary }: { summary: TodaySummary }) {
  return (
    <Link
      href={`/countries/${summary.iso}` as Route}
      style={{ textDecoration: "none", color: "inherit" }}
    >
      <div
        style={{
          background: "var(--qgi-bg)",
          border: "1px solid var(--qgi-border)",
          borderRadius: "8px",
          padding: "16px",
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
        {/* Flag + country name */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            marginBottom: "10px",
          }}
        >
          <FlagImg
            emoji={pairDetailFlagFor(summary.countryName)}
            name={summary.countryName}
            width={20}
            radius={2}
          />
          <span style={{ fontSize: "14px", fontWeight: 700, color: "var(--qgi-text)" }}>
            {summary.countryName}
          </span>
        </div>

        {/* Summary sentence */}
        <p
          style={{
            fontSize: "12px",
            color: "var(--qgi-text-muted)",
            margin: "0 0 10px",
            lineHeight: 1.6,
          }}
        >
          Currently {summary.countryName}&apos;s strongest recipe match is{" "}
          <span
            style={{
              fontFamily: "ui-monospace, monospace",
              color: "var(--qgi-text)",
              fontSize: "11px",
            }}
          >
            {summary.topRecipeLabel}
          </span>
          , rank #{summary.catalogueRank} in the catalogue.
        </p>

        {/* Profile link hint */}
        <span
          style={{
            fontSize: "10px",
            color: "var(--qgi-accent)",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.3px",
          }}
        >
          Open country profile &rarr;
        </span>
      </div>
    </Link>
  );
}
