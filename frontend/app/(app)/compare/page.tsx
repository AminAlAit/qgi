/**
 * /compare — V4.1 round-3.3 lockdown (2026-05-29).
 *
 * The page is "Coming soon". The body renders a fresh hand-authored
 * USA-vs-CHINA mock-comparison dashboard (big flags, big numbers, vivid
 * family-color bars, recipe-by-recipe comparison strips, indicator
 * face-offs) styled to look like a professional comparative-analytics
 * surface even at 8px blur. A centered overlay sits on top with the
 * founder-authored "Coming soon" message and a deflection link to the
 * Analogues page.
 *
 * The whole surface is height-constrained to 100% of the main column
 * with overflow:hidden so neither the user nor the visible message ever
 * scrolls — the overlay is always on screen, the blurred backdrop is
 * always behind it, and there is no awkward second-fold reveal.
 */
import type { Metadata } from "next";
import Link from "next/link";
import type { Route } from "next";
import {
  ComingSoonGlass,
  ComingSoonCard,
} from "@/components/coming-soon/ComingSoonGlass";

export const metadata: Metadata = {
  title: "Compare · QG Intelligence",
  description:
    "Compare two countries on the same set of trends side by side. Read across for one country, down for one trend.",
  robots: { index: false, follow: false },
};

// Family-palette colors lifted from lib/te-mock/l1-families.ts. We hardcode
// the few we need here because the backdrop is purely decorative — no point
// pulling the whole familyColor() machinery in for what is, post-blur, just
// "warm" and "cool" colored ink on slate panels.
const USA = "#3FA9F5"; // Economic Stress blue — fast, confident
const CHN = "#E64545"; // Conflict & Violence red — urgent, vivid
const AMBER = "#E68F29";
const GREEN = "#3FBF8F";
const PURPLE = "#7B5EE6";
const SLATE = "#5B7E99";
const NEUTRAL = "#7A8FA0";

interface MatchupRow {
  recipe: string;
  usa: number; // 0-100 score
  chn: number;
  accent: string;
}
const MATCHUP: MatchupRow[] = [
  { recipe: "Banking & Financial Crisis", usa: 38, chn: 71, accent: USA },
  { recipe: "Foreign Intervention", usa: 84, chn: 92, accent: CHN },
  { recipe: "Diplomatic Rupture", usa: 47, chn: 78, accent: PURPLE },
  { recipe: "Trade Dispute", usa: 91, chn: 88, accent: AMBER },
  { recipe: "Cyberattack", usa: 67, chn: 81, accent: SLATE },
  { recipe: "Migration & Refugees", usa: 72, chn: 41, accent: GREEN },
];

interface IndicatorRow {
  name: string;
  usa: number;
  chn: number;
}
const INDICATORS: IndicatorRow[] = [
  { name: "Regulatory Quality", usa: 91, chn: 47 },
  { name: "Government Effectiveness", usa: 88, chn: 73 },
  { name: "Political Stability", usa: 62, chn: 51 },
  { name: "Trade Openness", usa: 81, chn: 67 },
  { name: "Military Expenditure / GDP", usa: 78, chn: 89 },
];

export default async function ComparePage() {
  return (
    <ComingSoonGlass
      backdrop={
        <div style={{ display: "flex", flexDirection: "column", gap: "22px" }}>
          {/* §1 — Hero band: huge flags + big country names + compound score */}
          <section
            style={{
              display: "grid",
              gridTemplateColumns: "1fr auto 1fr",
              gap: "32px",
              alignItems: "center",
              background: "var(--qgi-surface)",
              border: "1px solid var(--qgi-border)",
              borderRadius: "10px",
              padding: "28px 40px",
              minHeight: "180px",
            }}
          >
            <CountryHero
              name="UNITED STATES"
              iso="USA"
              iso2="us"
              compound={47}
              litCount={12}
              accent={USA}
              align="left"
            />
            <div
              style={{
                fontSize: "44px",
                fontWeight: 800,
                letterSpacing: "4px",
                color: "var(--qgi-text-dim)",
                fontFamily: "ui-monospace, monospace",
              }}
            >
              VS
            </div>
            <CountryHero
              name="CHINA"
              iso="CHN"
              iso2="cn"
              compound={73}
              litCount={18}
              accent={CHN}
              align="right"
            />
          </section>

          {/* §2 — Recipe matchup bars (full-width strip) */}
          <section
            style={{
              background: "var(--qgi-surface)",
              border: "1px solid var(--qgi-border)",
              borderRadius: "10px",
              padding: "24px 32px",
              display: "flex",
              flexDirection: "column",
              gap: "14px",
              flex: 1,
              minHeight: 0,
            }}
          >
            <PanelHeader
              eyebrow="§01 · Shared trend matchup"
              title="Where the two countries diverge most"
            />
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "10px",
                flex: 1,
                minHeight: 0,
              }}
            >
              {MATCHUP.map((m) => (
                <RecipeMatchupRow key={m.recipe} row={m} />
              ))}
            </div>
          </section>

          {/* §3 — Bottom strip: indicator face-off + 3 stat tiles */}
          <section
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(0, 1.5fr) minmax(0, 1fr)",
              gap: "20px",
            }}
          >
            {/* Left: indicator face-off panel */}
            <div
              style={{
                background: "var(--qgi-surface)",
                border: "1px solid var(--qgi-border)",
                borderRadius: "10px",
                padding: "20px 28px 22px",
                display: "flex",
                flexDirection: "column",
                gap: "12px",
              }}
            >
              <PanelHeader
                eyebrow="§02 · Indicator face-off"
                title="Drivers behind the gap"
              />
              <div style={{ display: "flex", flexDirection: "column", gap: "9px" }}>
                {INDICATORS.map((ind) => (
                  <IndicatorFaceOffRow key={ind.name} row={ind} />
                ))}
              </div>
            </div>

            {/* Right: 3 stat tiles stacked */}
            <div
              style={{
                display: "grid",
                gridTemplateRows: "1fr 1fr 1fr",
                gap: "12px",
              }}
            >
              <StatTile
                label="Trends both match"
                big="9"
                caption="shared catalog entries lit"
                accent={GREEN}
              />
              <StatTile
                label="Compound risk gap"
                big="+26"
                caption="China leads on a bounded 0-100 scale"
                accent={CHN}
              />
              <StatTile
                label="Historical analogue overlap"
                big="4 / 7"
                caption="four shared historical pre-event matches"
                accent={PURPLE}
              />
            </div>
          </section>
        </div>
      }
    >
      <ComingSoonCard title="Side-by-side country comparison">
        <p style={{ margin: 0 }}>
          We&apos;re currently working on making it possible for you to compare countries
          to one another. Same trends, same metrics, side by side. Until then, you can
          compare any country to its closest historical analogue via{" "}
          <Link
            href={"/analogues" as Route}
            style={{ color: "var(--qgi-accent)", textDecoration: "none" }}
          >
            Analogues
          </Link>
          .
        </p>
      </ComingSoonCard>
    </ComingSoonGlass>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
 * Backdrop sub-components — purely decorative, post-blur they read as a
 * professional comparative-analytics dashboard.
 * ────────────────────────────────────────────────────────────────────────── */

function CountryHero({
  name,
  iso,
  iso2,
  compound,
  litCount,
  accent,
  align,
}: {
  name: string;
  iso: string;
  iso2: string;
  compound: number;
  litCount: number;
  accent: string;
  align: "left" | "right";
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: align === "right" ? "row-reverse" : "row",
        alignItems: "center",
        gap: "20px",
      }}
    >
      {/* Big flag — flagcdn at w160 for crispness even at 200×128 display */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={`https://flagcdn.com/w160/${iso2}.png`}
        alt={`${name} flag`}
        width={140}
        height={94}
        style={{
          display: "block",
          objectFit: "cover",
          borderRadius: "4px",
          border: `1px solid ${accent}`,
          boxShadow: `0 0 30px ${accent}33`,
          flexShrink: 0,
        }}
      />
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "6px",
          textAlign: align,
        }}
      >
        <div
          style={{
            fontSize: "10px",
            letterSpacing: "2.5px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          ISO {iso}
        </div>
        <div
          style={{
            fontSize: "26px",
            fontWeight: 700,
            letterSpacing: "1.5px",
            color: accent,
            lineHeight: 1,
          }}
        >
          {name}
        </div>
        <div
          style={{
            display: "flex",
            gap: "14px",
            marginTop: "8px",
            justifyContent: align === "right" ? "flex-end" : "flex-start",
          }}
        >
          <BigStat label="Compound risk" value={compound} accent={accent} />
          <BigStat label="Trends lit" value={litCount} accent={NEUTRAL} />
        </div>
      </div>
    </div>
  );
}

function BigStat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent: string;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
      <div
        style={{
          fontSize: "34px",
          fontWeight: 700,
          fontFamily: "ui-monospace, monospace",
          color: accent,
          letterSpacing: "-1px",
          lineHeight: 1,
        }}
      >
        {value}
      </div>
      <div
        style={{
          fontSize: "9px",
          letterSpacing: "1.5px",
          textTransform: "uppercase",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
        }}
      >
        {label}
      </div>
    </div>
  );
}

function PanelHeader({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <header style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
      <div
        style={{
          fontSize: "9.5px",
          letterSpacing: "2.5px",
          textTransform: "uppercase",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
        }}
      >
        {eyebrow}
      </div>
      <h2
        style={{
          fontSize: "15px",
          fontWeight: 600,
          margin: 0,
          color: "var(--qgi-text)",
        }}
      >
        {title}
      </h2>
    </header>
  );
}

function RecipeMatchupRow({ row }: { row: MatchupRow }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 1fr) 50px minmax(0, 1fr)",
        gap: "10px",
        alignItems: "center",
      }}
    >
      {/* USA bar — fills from the right toward the center */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          justifyContent: "flex-end",
        }}
      >
        <span
          style={{
            fontSize: "12px",
            fontWeight: 700,
            color: USA,
            fontFamily: "ui-monospace, monospace",
            width: "28px",
            textAlign: "right",
          }}
        >
          {row.usa}
        </span>
        <div
          style={{
            flex: 1,
            height: "8px",
            background: "rgba(255,255,255,0.04)",
            border: "1px solid var(--qgi-border)",
            borderRadius: "2px",
            overflow: "hidden",
            position: "relative",
          }}
        >
          <div
            style={{
              position: "absolute",
              right: 0,
              top: 0,
              bottom: 0,
              width: `${row.usa}%`,
              background: `linear-gradient(90deg, ${USA}00 0%, ${USA}cc 100%)`,
            }}
          />
        </div>
      </div>
      {/* Recipe label in the center */}
      <div
        style={{
          fontSize: "10px",
          color: "var(--qgi-text-muted)",
          fontFamily: "ui-monospace, monospace",
          textAlign: "center",
          padding: "0 4px",
          letterSpacing: "0.3px",
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
        title={row.recipe}
      >
        ●
      </div>
      {/* CHN bar — fills from the left */}
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <div
          style={{
            flex: 1,
            height: "8px",
            background: "rgba(255,255,255,0.04)",
            border: "1px solid var(--qgi-border)",
            borderRadius: "2px",
            overflow: "hidden",
            position: "relative",
          }}
        >
          <div
            style={{
              position: "absolute",
              left: 0,
              top: 0,
              bottom: 0,
              width: `${row.chn}%`,
              background: `linear-gradient(90deg, ${CHN}cc 0%, ${CHN}00 100%)`,
            }}
          />
        </div>
        <span
          style={{
            fontSize: "12px",
            fontWeight: 700,
            color: CHN,
            fontFamily: "ui-monospace, monospace",
            width: "28px",
          }}
        >
          {row.chn}
        </span>
      </div>
    </div>
  );
}

function IndicatorFaceOffRow({ row }: { row: IndicatorRow }) {
  const gap = Math.abs(row.usa - row.chn);
  const leader = row.usa >= row.chn ? USA : CHN;
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 1.5fr) 60px minmax(0, 1.5fr)",
        gap: "8px",
        alignItems: "center",
      }}
    >
      <div
        style={{
          fontSize: "10.5px",
          color: "var(--qgi-text-muted)",
          fontFamily: "ui-monospace, monospace",
          textAlign: "right",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {row.name}
      </div>
      <div
        style={{
          fontSize: "13px",
          fontWeight: 700,
          fontFamily: "ui-monospace, monospace",
          color: leader,
          textAlign: "center",
          letterSpacing: "-0.5px",
        }}
      >
        Δ {gap}
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "4px",
          height: "10px",
        }}
      >
        <div
          style={{
            width: `${row.usa}%`,
            height: "100%",
            background: USA,
            opacity: 0.78,
            borderRadius: "1px",
          }}
        />
        <div
          style={{
            width: `${row.chn}%`,
            height: "100%",
            background: CHN,
            opacity: 0.78,
            borderRadius: "1px",
          }}
        />
      </div>
    </div>
  );
}

function StatTile({
  label,
  big,
  caption,
  accent,
}: {
  label: string;
  big: string;
  caption: string;
  accent: string;
}) {
  return (
    <div
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderLeft: `3px solid ${accent}`,
        borderRadius: "8px",
        padding: "10px 16px",
        display: "flex",
        flexDirection: "column",
        gap: "3px",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          fontSize: "9.5px",
          letterSpacing: "1.8px",
          textTransform: "uppercase",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: "28px",
          fontWeight: 700,
          color: accent,
          fontFamily: "ui-monospace, monospace",
          letterSpacing: "-1px",
          lineHeight: 1,
        }}
      >
        {big}
      </div>
      <div
        style={{
          fontSize: "10.5px",
          color: "var(--qgi-text-muted)",
          lineHeight: 1.3,
        }}
      >
        {caption}
      </div>
    </div>
  );
}
