/**
 * AnalogResults — the results panel: top-3 analog cards + recipe contribution
 * panel + library footer. Rendered for one CurrentCountryEntry at a time.
 *
 * Imported by the (client) CountryPicker, but itself uses no client hooks —
 * the components inside are all server-style (pure render from props). The
 * parent picker decides which entry to pass.
 */
import Link from "next/link";
import type { Route } from "next";
import { Layers, Hash, GitCompare } from "lucide-react";
import type { CurrentCountryEntry } from "@/lib/te-mock/nearest-analog-data";
import { AnalogCard } from "./AnalogCard";
import { RecipeContributionBar } from "./RecipeContributionBar";

export interface AnalogResultsProps {
  entry: CurrentCountryEntry;
}

export function AnalogResults({ entry }: AnalogResultsProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "28px" }}>
      {/* Section header */}
      <div>
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "8px",
            marginBottom: "8px",
          }}
        >
          <div>
            <div
              style={{
                fontSize: "9px",
                letterSpacing: "1.8px",
                color: "var(--qgi-accent)",
                fontFamily: "ui-monospace, monospace",
                fontWeight: 600,
                marginBottom: "4px",
              }}
            >
              TOP-3 HISTORICAL ANALOGUES · {entry.name.toUpperCase()} TODAY
            </div>
            <h2
              style={{
                fontSize: "22px",
                fontWeight: 600,
                margin: 0,
                color: "var(--qgi-text)",
                lineHeight: 1.2,
              }}
            >
              Whose pre-event shape does {entry.name} rhyme with most?
            </h2>
          </div>
          {/* 2026-05-30 founder ask: "k=3 · SHAP-weighted cosine ·
              self-excluded" methodology chip removed. The mechanics live
              in the methodology side panel and the "how to read this"
              popover; the headline doesn't need to shout them. */}
        </div>
        <p
          style={{
            fontSize: "13px",
            color: "var(--qgi-text-muted)",
            lineHeight: 1.55,
            margin: "8px 0 0",
            maxWidth: "780px",
          }}
        >
          The three historical cases whose pre-event indicator trajectories most resemble{" "}
          {entry.name}&apos;s recent movement. <strong>Similarity, not destiny:</strong>{" "}
          read the historical outcomes as fact about the analogue country, never as
          forecast for {entry.name}.
        </p>
      </div>

      {/* Top-3 grid */}
      <div
        data-tour="analog-results"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(min(320px, 100%), 1fr))",
          gap: "16px",
        }}
      >
        {entry.analogs.map((a, i) => (
          <AnalogCard
            key={`${a.country}-${a.year}`}
            rank={i + 1}
            analog={a}
            currentCountryName={entry.name}
            currentTrajectory={entry.indicator_trajectory}
            subjectIso2={entry.iso2}
            subjectRegion={entry.region}
          />
        ))}
      </div>

      {/* Recipe-contribution panel */}
      <section
        data-tour="recipe-contributions"
        style={{
          background: "var(--qgi-surface)",
          border: "1px solid var(--qgi-border)",
          borderRadius: "8px",
          padding: "20px",
        }}
      >
        <header
          style={{
            display: "flex",
            alignItems: "center",
            gap: "10px",
            marginBottom: "14px",
          }}
        >
          <Layers size={18} strokeWidth={1.6} color="var(--qgi-accent)" />
          {/* 2026-05-30: copy simplified to match the Risk Board pattern —
              kicker chip dropped, dense subtitle dropped, paragraph
              compressed to one sentence that says what the rows are. */}
          <h3
            style={{
              fontSize: "18px",
              fontWeight: 600,
              margin: 0,
              color: "var(--qgi-text)",
              lineHeight: 1.2,
            }}
          >
            Which trends pulled the match
          </h3>
        </header>
        <p
          style={{
            fontSize: "13px",
            color: "var(--qgi-text-muted)",
            lineHeight: 1.55,
            margin: "0 0 14px",
            maxWidth: "640px",
          }}
        >
          The trend shapes that drew {entry.name} toward its analogues, ranked by weighted
          contribution.
        </p>
        <RecipeContributionBar contributions={entry.contributions} />
      </section>

      {/* Library footer */}
      <section
        style={{
          background: "var(--qgi-surface)",
          border: "1px solid var(--qgi-border)",
          borderRadius: "8px",
          padding: "18px 20px",
          display: "flex",
          alignItems: "center",
          gap: "16px",
          flexWrap: "wrap",
        }}
      >
        <Hash
          size={20}
          strokeWidth={1.6}
          color="var(--qgi-text-muted)"
          style={{ flexShrink: 0 }}
        />
        <div style={{ flex: 1, minWidth: "240px" }}>
          <div
            style={{
              fontSize: "13px",
              fontWeight: 600,
              color: "var(--qgi-text)",
              marginBottom: "3px",
            }}
          >
            Search the whole library
          </div>
          <div
            style={{ fontSize: "12px", color: "var(--qgi-text-muted)", lineHeight: 1.5 }}
          >
            All 69 trends in the QGI catalog with mini-trajectories: browse every
            trajectory shape, queued or tested, that the analogue finder draws from.
          </div>
        </div>
        <Link
          href={"/trends" as Route}
          style={{
            fontSize: "12px",
            padding: "9px 14px",
            background: "var(--qgi-accent)",
            color: "var(--qgi-bg)",
            border: "1px solid var(--qgi-accent)",
            borderRadius: "5px",
            textDecoration: "none",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.5px",
            fontWeight: 600,
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            flexShrink: 0,
          }}
        >
          <GitCompare size={14} strokeWidth={2} />
          Browse all 69 trends
        </Link>
      </section>
    </div>
  );
}
