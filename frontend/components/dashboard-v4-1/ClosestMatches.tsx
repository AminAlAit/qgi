/**
 * ClosestMatches — the Briefing centerpiece.
 *
 * "How countries are following recipes," as a left-to-right row of rich cards.
 * Real fleet data (the strong 95%er band, one story per country), each card
 * opens the country×recipe match page. This is the front door's answer to
 * "what does QGI see right now?" — confidence-first, not catalogue trivia.
 *
 * Server component: static SVG sparks, a scoped <style> for the hover lift.
 */
import Link from "next/link";
import type { Route } from "next";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { MiniSparkline } from "@/components/countries-v4-1/MiniSparkline";
import { RecipeIcon } from "@/components/te-v4-shared/RecipeIcon";
import { flagFor } from "@/lib/te-mock/country-flags";
import { MUTED_GRAY, confidenceT, lerpHexToRgb } from "@/lib/color-lerp";
import type { ClosestMatch } from "@/lib/te-mock/dashboard-v4-1-data";

/**
 * The fleet zone_label is generic ("partial alignment with crisis profile",
 * "trajectory aligns with crisis profile"). Name the actual event instead of
 * the placeholder "crisis", using the card's own recipe label.
 */
function nameTheEvent(zoneLabel: string, eventLabel: string): string {
  return zoneLabel.replace(/\bcrisis(?=\s+profile\b)/i, eventLabel.toLowerCase());
}

export function ClosestMatches({ matches }: { matches: ClosestMatch[] }) {
  if (matches.length === 0) return null;
  return (
    <section data-tour="closest-matches" style={{ marginTop: "8px" }}>
      <style>{`
        .qgi-cm-card { transition: transform 140ms ease, border-color 140ms ease, box-shadow 140ms ease; }
        .qgi-cm-card:hover { transform: translateY(-3px); box-shadow: 0 8px 24px rgba(0,0,0,0.35); }
      `}</style>
      <header style={{ marginBottom: "14px" }}>
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
            fontSize: "13.5px",
            color: "var(--qgi-text-muted)",
            margin: 0,
            lineHeight: 1.5,
            maxWidth: "760px",
          }}
        >
          Countries whose recent signals are tracing an event trend especially closely
          this release. Open any card to see how that country is following the trend,
          signal by signal. A measure of resemblance, not a forecast.
        </p>
      </header>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(244px, 1fr))",
          gap: "14px",
        }}
      >
        {matches.map((m) => (
          <MatchCard key={`${m.recipe_id}-${m.iso2}`} m={m} />
        ))}
      </div>
    </section>
  );
}

function MatchCard({ m }: { m: ClosestMatch }) {
  const cT = confidenceT(m.score);
  const scoreColor = lerpHexToRgb(MUTED_GRAY, m.l1_color, cT);
  const sparkMin = m.composite.length
    ? -Math.max(...m.composite.map((v) => Math.abs(v)), 1) - 0.3
    : 0;
  const sparkMax = m.composite.length
    ? Math.max(...m.composite.map((v) => Math.abs(v)), 1) + 0.3
    : 1;

  return (
    <Link
      href={`/trends/${m.recipe_id}/countries/${m.iso2}` as Route}
      className="qgi-cm-card"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "10px",
        textDecoration: "none",
        color: "inherit",
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderLeft: `3px solid ${m.l1_color}`,
        borderRadius: "8px",
        padding: "14px 14px 12px",
        minWidth: 0,
      }}
    >
      {/* Country */}
      <div style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: 0 }}>
        <FlagImg emoji={flagFor(m.country)} name={m.country} width={20} radius={3} />
        <span
          style={{
            fontSize: "14px",
            fontWeight: 600,
            color: "var(--qgi-text)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {m.country}
        </span>
      </div>

      {/* Recipe */}
      <div style={{ display: "flex", alignItems: "center", gap: "7px", minWidth: 0 }}>
        <span style={{ color: m.l1_color, display: "inline-flex", flexShrink: 0 }}>
          <RecipeIcon recipeId={m.recipe_id} size={14} strokeWidth={1.8} />
        </span>
        <span
          style={{
            fontSize: "12.5px",
            color: "var(--qgi-text-muted)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {m.recipe_label}
        </span>
      </div>

      {/* Score + spark */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "space-between",
          gap: "8px",
          marginTop: "2px",
        }}
      >
        <div style={{ display: "flex", alignItems: "baseline", gap: "5px" }}>
          <span
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: "30px",
              fontWeight: 700,
              color: scoreColor,
              letterSpacing: "-1px",
              lineHeight: 1,
            }}
          >
            {Math.round(m.score)}
          </span>
          <span
            style={{
              fontSize: "9px",
              letterSpacing: "0.6px",
              textTransform: "uppercase",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            match
          </span>
        </div>
        {m.composite.length > 1 && (
          <MiniSparkline
            values={m.composite}
            color={m.l1_color}
            width={88}
            height={26}
            min={sparkMin}
            max={sparkMax}
          />
        )}
      </div>

      {/* Zone label */}
      {m.zone_label && (
        <div
          style={{
            fontSize: "11px",
            color: "var(--qgi-text-dim)",
            lineHeight: 1.4,
            borderTop: "1px solid var(--qgi-border)",
            paddingTop: "8px",
          }}
        >
          {nameTheEvent(m.zone_label, m.recipe_label)}
        </div>
      )}
    </Link>
  );
}
