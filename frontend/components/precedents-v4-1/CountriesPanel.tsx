/**
 * CountriesPanel — V4.1, founder polish #158.
 *
 * Replaces TopCountriesPanel + BottomCountriesPanel: ONE panel showing
 * both ends of the recipe's score distribution at a glance, plus an
 * internal "Full list" expand toggle that swaps in a scrollable roster
 * of every scored country.
 *
 *
 * Layout
 * ──────
 *   ┌──────────────────────────────────────────┐
 *   │ Countries          [tooltip] [expand ▢] │   header
 *   │ Top and bottom of the distribution.      │   caption
 *   │ ──────────────────────────────────────── │
 *   │  TOP  · highest-scoring                  │
 *   │   1  🇮🇷  Iran                  98.1     │
 *   │   2  🇹🇲  Turkmenistan          97.0     │
 *   │   3  🇬🇶  Equatorial Guinea     96.9     │
 *   │   4  🇧🇾  Belarus               94.2     │
 *   │   5  🇹🇯  Tajikistan            88.5     │
 *   │                                          │
 *   │     ╌╌╌╌  ~157 countries between   ╌╌╌╌  │   structural gap row
 *   │                                          │
 *   │  BOTTOM · lowest-scoring                 │
 *   │  163  🇫🇮  Finland               8.3     │
 *   │  164  🇳🇿  New Zealand           7.1     │
 *   │  165  🇳🇴  Norway                6.4     │
 *   │  166  🇮🇸  Iceland               5.8     │
 *   │  167  🇨🇭  Switzerland           5.2     │
 *   └──────────────────────────────────────────┘
 *
 * Top is descending (highest first). Bottom is descending too so the
 * lowest-ranked country sits at the very bottom of the panel — the
 * eye reads the distribution as a continuous slope from peak (top of
 * panel) to floor (bottom of panel), with the missing middle marked
 * by a soft dashed divider showing how many countries are elided.
 *
 *
 * Expand-to-full-list
 * ───────────────────
 * The header button (matching ExpandableShell's accent) toggles between
 * the at-a-glance view (5+5) and a scrollable full roster of every
 * country in `countriesFull` (mock ≈80 entries for foreign_intervention).
 * The page does NOT wrap CountriesPanel in ExpandableShell; the panel
 * is its own expandable surface (founder's note (c)). This keeps the
 * expansion semantically "show MORE rows", not "grow the grid cell" —
 * which is what users actually want when they see "5 + 5".
 *
 *
 * Flag rendering — image-based (founder #163)
 * ───────────────────────────────────────────
 * Windows 10's Segoe UI Emoji ships flag sequences as plain 2-letter
 * regional-indicator pairs ("IR" instead of 🇮🇷). A font-stack override
 * doesn't fix this — Win10 simply has no flag glyphs available. The
 * cross-browser fix is to render flags as `<img>` from flagcdn.com via
 * the country's ISO 3166-1 alpha-2 code (resolved by `iso2For(name)`).
 *
 * Sizes: 16×12 — the natural aspect ratio for most flags, sits cleanly
 * beside 13px text without optical wobble. flagcdn provides 1× and 2×
 * raster sizes; we ask for 16×12 explicitly so the browser doesn't have
 * to upscale the 1× tile on Hi-DPI displays (16×12 is already the right
 * physical pixel count for our row height).
 *
 * On a missing ISO code (unmapped country name) we render a
 * fixed-footprint blank span so the row grid stays aligned — better
 * than a broken-image icon.
 */
"use client";

import { useState, useMemo } from "react";
import type { CSSProperties } from "react";
import Link from "next/link";
import type { Route } from "next";
import { PanelBase } from "./PanelBase";
import { iso2For } from "@/lib/te-mock/country-flags";
import type { CountryScore } from "@/lib/te-mock/recipe-v4-1-mock";
import { NEUTRAL_SLATE } from "@/lib/te-mock/l1-families";

interface Props {
  familyColor: string;
  /** Top-5 (highest scoring), descending. */
  countriesTop: CountryScore[];
  /** Bottom-5 (lowest scoring). Caller may pass ascending or descending;
   *  we sort descending internally so the panel reads peak → floor. */
  countriesBottom: CountryScore[];
  /** Full scored roster (~50-170 entries), descending by score. Used
   *  when the user clicks the in-panel expand button. */
  countriesFull: CountryScore[];
  showResults: boolean;
  /** Total scored — used for the "~N countries between" elided count.
   *  Defaults to countriesFull.length when omitted. */
  nScored?: number;
  /** When set, each country row links to /trends/{recipeId}/countries/{iso2}
   *  (the country-recipe match page). Rows whose name has no ISO stay inert. */
  recipeId?: string;
  /** When set, the matching row is outlined in the family color (used on the
   *  match page to show "you are here"). */
  highlightName?: string;
}

export function CountriesPanel({
  familyColor,
  countriesTop,
  countriesBottom,
  countriesFull,
  showResults,
  nScored,
  recipeId,
  highlightName,
}: Props) {
  const [expanded, setExpanded] = useState(false);

  const totalScored = nScored ?? countriesFull.length;
  const topSorted = [...countriesTop].sort((a, b) => b.score - a.score);
  // Force bottom into descending order (lowest-rank last) so the visual
  // slope is monotone from top of panel (peak) to bottom of panel (floor).
  const bottomSorted = [...countriesBottom].sort((a, b) => b.score - a.score);
  const elidedCount = Math.max(0, totalScored - topSorted.length - bottomSorted.length);

  return (
    <PanelBase
      title="Countries"
      familyColor={familyColor}
      dataTour="countries-panel"
      titleTooltip="Both ends of the distribution at a glance. The trend's positive (highest-scoring) and structural-negative (lowest-scoring) extremes. Rank, not probability; a country at 98 sits at the top of the distribution of countries whose movement shape resembles past precedents. Expand for the full roster."
      caption={
        showResults && countriesTop.length > 0
          ? expanded
            ? `Full roster: ${totalScored} countries, ranked by resemblance score (%), highest first.`
            : `Top ${topSorted.length} and bottom ${bottomSorted.length} of ${totalScored} scored countries · resemblance score (%).`
          : undefined
      }
      sectionPending={!showResults || countriesTop.length === 0 ? "discrimination" : null}
      id="cap-8"
      headerSlot={
        showResults && countriesTop.length > 0 ? (
          <ExpandToggle
            expanded={expanded}
            onClick={() => setExpanded((v) => !v)}
            familyColor={familyColor}
          />
        ) : undefined
      }
    >
      {expanded ? (
        <FullRoster
          countries={countriesFull}
          familyColor={familyColor}
          recipeId={recipeId}
          highlightName={highlightName}
        />
      ) : (
        <TopAndBottom
          top={topSorted}
          bottom={bottomSorted}
          totalScored={totalScored}
          elidedCount={elidedCount}
          familyColor={familyColor}
          recipeId={recipeId}
          highlightName={highlightName}
          countriesFull={countriesFull}
        />
      )}
    </PanelBase>
  );
}

/* ───────── Default view: top-5 + divider + bottom-5 ──────────────────── */

function TopAndBottom({
  top,
  bottom,
  totalScored,
  elidedCount,
  familyColor,
  recipeId,
  highlightName,
  countriesFull,
}: {
  top: CountryScore[];
  bottom: CountryScore[];
  totalScored: number;
  elidedCount: number;
  familyColor: string;
  recipeId?: string;
  highlightName?: string;
  countriesFull: CountryScore[];
}) {
  // Compute median score across all scored countries so each row can render
  // the "typical country" marker on the proportional bar.
  const medianScore = useMemo(() => {
    if (countriesFull.length === 0) return 50;
    const sorted = [...countriesFull].map((c) => c.score).sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
  }, [countriesFull]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
      <ZoneHeading label="Top" subLabel="highest-scoring" accent={familyColor} />
      <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {top.map((c, i) => (
          <CountryRow
            key={`top-${c.name}`}
            rank={i + 1}
            name={c.name}
            score={c.score}
            familyColor={familyColor}
            scoreColor={familyColor}
            scoreWeight={700}
            divider={i < top.length - 1}
            recipeId={recipeId}
            highlight={c.name === highlightName}
            medianScore={medianScore}
            showMedianLabel={i === 0}
          />
        ))}
      </ol>

      <ElidedDivider count={elidedCount} />

      <ZoneHeading
        label="Bottom"
        subLabel="lowest-scoring"
        accent="var(--qgi-text-dim)"
      />
      <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {bottom.map((c, i) => (
          <CountryRow
            key={`bot-${c.name}`}
            rank={totalScored - bottom.length + i + 1}
            name={c.name}
            score={c.score}
            familyColor={familyColor}
            scoreColor="var(--qgi-text-muted)"
            scoreWeight={600}
            divider={i < bottom.length - 1}
            recipeId={recipeId}
            highlight={c.name === highlightName}
            medianScore={medianScore}
          />
        ))}
      </ol>
    </div>
  );
}

function ZoneHeading({
  label,
  subLabel,
  accent,
}: {
  label: string;
  subLabel: string;
  accent: string;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "baseline",
        gap: "8px",
        paddingBottom: "4px",
        borderBottom: "1px solid var(--qgi-border)",
      }}
    >
      <span
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: "10px",
          letterSpacing: "1.1px",
          textTransform: "uppercase",
          color: accent,
          fontWeight: 700,
        }}
      >
        {label}
      </span>
      <span
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: "9.5px",
          letterSpacing: "0.5px",
          textTransform: "uppercase",
          color: "var(--qgi-text-dim)",
        }}
      >
        · {subLabel}
      </span>
    </div>
  );
}

function ElidedDivider({ count }: { count: number }) {
  if (count <= 0) {
    return <div style={{ height: "4px" }} />;
  }
  return (
    <div
      aria-hidden
      style={{
        display: "flex",
        alignItems: "center",
        gap: "10px",
        padding: "6px 0",
      }}
    >
      <span
        style={{
          flex: 1,
          borderTop: "1px dashed var(--qgi-border)",
          height: 0,
          opacity: 0.7,
        }}
      />
      <span
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: "10px",
          color: "var(--qgi-text-dim)",
          letterSpacing: "0.4px",
          whiteSpace: "nowrap",
        }}
      >
        ~{count} countries between
      </span>
      <span
        style={{
          flex: 1,
          borderTop: "1px dashed var(--qgi-border)",
          height: 0,
          opacity: 0.7,
        }}
      />
    </div>
  );
}

/* ───────── Expanded view: full scrollable roster ─────────────────────── */

function FullRoster({
  countries,
  familyColor,
  recipeId,
  highlightName,
}: {
  countries: CountryScore[];
  familyColor: string;
  recipeId?: string;
  highlightName?: string;
}) {
  const medianScore = useMemo(() => {
    if (countries.length === 0) return 50;
    const sorted = [...countries].map((c) => c.score).sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
  }, [countries]);

  return (
    <div
      style={{
        maxHeight: "440px",
        overflowY: "auto",
        margin: 0,
        padding: 0,
        border: "1px solid var(--qgi-border)",
        borderRadius: "4px",
        background: "var(--qgi-bg)",
      }}
    >
      <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {countries.map((c, i) => (
          <CountryRow
            key={`full-${i}-${c.name}`}
            rank={i + 1}
            name={c.name}
            score={c.score}
            familyColor={familyColor}
            scoreColor={scoreShade(c.score, familyColor)}
            scoreWeight={i < 10 ? 700 : 600}
            divider={i < countries.length - 1}
            dense
            recipeId={recipeId}
            highlight={c.name === highlightName}
            medianScore={medianScore}
            showMedianLabel={i === 0}
          />
        ))}
      </ol>
    </div>
  );
}

/**
 * Score → color: top of the distribution gets full family color;
 * mid stays text-muted; bottom gets text-dim. Gives the scroll a
 * subtle visual gradient even when the list is long.
 */
function scoreShade(score: number, familyColor: string): string {
  if (score >= 70) return familyColor;
  if (score >= 40) return "var(--qgi-text)";
  if (score >= 20) return "var(--qgi-text-muted)";
  return "var(--qgi-text-dim)";
}

/* ───────── Shared row component ──────────────────────────────────────── */

function CountryRow({
  rank,
  name,
  score,
  familyColor,
  scoreColor,
  scoreWeight,
  divider,
  dense = false,
  recipeId,
  highlight = false,
  medianScore,
  showMedianLabel = false,
}: {
  rank: number;
  name: string;
  score: number;
  familyColor: string;
  scoreColor: string;
  scoreWeight: number;
  divider: boolean;
  dense?: boolean;
  /** When set, the row links to the country-recipe match page. */
  recipeId?: string;
  /** When true, the row is outlined ("you are here"). */
  highlight?: boolean;
  /** Median score across all scored countries; drives the "typical country" marker. */
  medianScore?: number;
  /** When true, render the visible "typical" caption above the median marker (once per list). */
  showMedianLabel?: boolean;
}) {
  const padY = dense ? "6px" : "8px";
  const iso2 = iso2For(name);
  // Only link on a valid 2-letter ISO; some names resolve to an emoji or
  // null in the flag map, which would produce a malformed URL.
  const linkable = !!recipeId && !!iso2 && /^[a-z]{2}$/.test(iso2);

  const barHeight = dense ? "4px" : "5px";
  const fillColor = highlight || score >= 70 ? familyColor : NEUTRAL_SLATE;

  const rowStyle: CSSProperties = {
    display: "grid",
    gridTemplateColumns: "28px 20px minmax(0, 1fr) 80px auto",
    gap: "8px",
    alignItems: "center",
    padding: dense ? `${padY} 8px` : `${padY} 6px`,
    borderRadius: "4px",
    textDecoration: "none",
    color: "inherit",
    background: highlight ? `${familyColor}24` : "transparent",
    outline: highlight ? `1.5px solid ${familyColor}` : "none",
    outlineOffset: "-1.5px",
    cursor: linkable ? "pointer" : "default",
    transition: "background 120ms ease",
  };

  // Clamp score to [0, 100] for the fill width.
  const fillPct = Math.max(0, Math.min(100, score));

  const content = (
    <>
      <span
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: dense ? "10px" : "10.5px",
          color: "var(--qgi-text-dim)",
          textAlign: "right",
        }}
      >
        {rank}
      </span>
      {iso2 ? (
        <img
          src={`https://flagcdn.com/16x12/${iso2}.png`}
          alt={`${name} flag`}
          width={16}
          height={12}
          style={{ display: "inline-block", verticalAlign: "middle", flexShrink: 0 }}
        />
      ) : (
        <span style={{ width: 16, height: 12, display: "inline-block" }} aria-hidden />
      )}
      <span
        style={{
          fontSize: dense ? "12.5px" : "13px",
          color: "var(--qgi-text)",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          fontWeight: highlight ? 700 : 400,
        }}
      >
        {name}
      </span>
      {/* Proportional score bar — 80px column, with optional median marker.
          Outer wrapper is position:relative + overflow:visible so the median
          marker can poke slightly outside the bar track height.
          Inner track carries overflow:hidden to cleanly clip the fill. */}
      <div
        aria-hidden
        style={{
          position: "relative",
          height: barHeight,
          alignSelf: "center",
        }}
      >
        {/* Bar track + fill */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            borderRadius: "2px",
            background: "var(--qgi-border)",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: `${fillPct}%`,
              height: "100%",
              background: fillColor,
              opacity: 0.8,
            }}
          />
        </div>
        {/* Typical-country median marker — sits outside overflow:hidden so
            the dashed tick is not clipped by the bar track. Extends 3px
            above and below the track so it reads as a reference line. */}
        {medianScore !== undefined && (
          <>
            <div
              title="Typical country"
              style={{
                position: "absolute",
                top: "-3px",
                bottom: "-3px",
                left: `${Math.max(0, Math.min(100, medianScore))}%`,
                width: 0,
                borderLeft: "1px dashed var(--qgi-text-dim)",
                opacity: 0.5,
                pointerEvents: "none",
              }}
            />
            {showMedianLabel && (
              <span
                style={{
                  position: "absolute",
                  top: "-14px",
                  left: `${Math.max(0, Math.min(100, medianScore))}%`,
                  transform: "translateX(-50%)",
                  fontFamily: "ui-monospace, monospace",
                  fontSize: "8.5px",
                  whiteSpace: "nowrap",
                  color: "var(--qgi-text-dim)",
                  opacity: 0.75,
                  pointerEvents: "none",
                }}
              >
                typical
              </span>
            )}
          </>
        )}
      </div>
      <span
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: dense ? "12.5px" : "13px",
          color: scoreColor,
          fontWeight: scoreWeight,
        }}
      >
        {Math.round(score)}
      </span>
    </>
  );

  const liStyle: CSSProperties = {
    listStyle: "none",
    borderBottom: divider ? "1px solid var(--qgi-border)" : "none",
  };

  if (linkable) {
    return (
      <li style={liStyle}>
        <Link
          href={`/trends/${recipeId}/countries/${iso2}` as Route}
          style={rowStyle}
          onMouseEnter={(e) => {
            if (!highlight) e.currentTarget.style.background = "var(--qgi-bg)";
          }}
          onMouseLeave={(e) => {
            if (!highlight) e.currentTarget.style.background = "transparent";
          }}
        >
          {content}
        </Link>
      </li>
    );
  }

  return <li style={{ ...liStyle, ...rowStyle }}>{content}</li>;
}

/* ───────── Expand-toggle button (mirrors ExpandableShell's affordance) ─ */

function ExpandToggle({
  expanded,
  onClick,
  familyColor,
}: {
  expanded: boolean;
  onClick: () => void;
  familyColor: string;
}) {
  return (
    <button
      type="button"
      aria-label={expanded ? "Collapse to top + bottom" : "Expand to full roster"}
      aria-pressed={expanded}
      onClick={onClick}
      title={expanded ? "Collapse" : "Show full roster"}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "6px",
        padding: "3px 8px",
        background: "var(--qgi-bg)",
        border: `1px solid ${familyColor}`,
        borderRadius: "4px",
        color: familyColor,
        fontFamily: "ui-monospace, monospace",
        fontSize: "10.5px",
        letterSpacing: "0.4px",
        cursor: "pointer",
        opacity: 0.9,
        transition: "background 120ms ease, opacity 120ms ease",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.opacity = "1";
        e.currentTarget.style.background = `${familyColor}14`;
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.opacity = "0.9";
        e.currentTarget.style.background = "var(--qgi-bg)";
      }}
    >
      <ToggleGlyph expanded={expanded} />
      {expanded ? "Top + bottom" : "Full list"}
    </button>
  );
}

function ToggleGlyph({ expanded }: { expanded: boolean }) {
  // Inline SVG so we don't add a chart-library or icon-set dep beyond what's
  // already on the page; mirrors the visual rhythm of Maximize2/Minimize2.
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden>
      {expanded ? (
        <>
          <path
            d="M1 3 L5 1 L9 3"
            stroke="currentColor"
            strokeWidth="1.3"
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M1 7 L5 9 L9 7"
            stroke="currentColor"
            strokeWidth="1.3"
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </>
      ) : (
        <>
          <line
            x1="1.5"
            y1="2.5"
            x2="8.5"
            y2="2.5"
            stroke="currentColor"
            strokeWidth="1.3"
            strokeLinecap="round"
          />
          <line
            x1="1.5"
            y1="5"
            x2="8.5"
            y2="5"
            stroke="currentColor"
            strokeWidth="1.3"
            strokeLinecap="round"
          />
          <line
            x1="1.5"
            y1="7.5"
            x2="8.5"
            y2="7.5"
            stroke="currentColor"
            strokeWidth="1.3"
            strokeLinecap="round"
          />
        </>
      )}
    </svg>
  );
}
