/**
 * /trends/[slug]/countries/[iso] — "how is this country following this
 * recipe" intersection page.
 *
 * Reached from three entry points (never the left nav):
 *   - a Risk Board cell (this country, this recipe's row)
 *   - a country profile's "Active recipes" panel row
 *   - a recipe profile's "Countries" panel row
 *
 * Look and feel mirror the country profile (header band + 1080px vertical
 * panel arc). Sourced from the real fleet-run-1 per-country scores: the
 * country's composite signal path overlaid on the historical cases it
 * resembles, signal-by-signal movement, the resemblance score's year-over-
 * year climb, peer context, and analogues. Honest "coming soon" for any
 * recipe not in the scored fleet.
 *
 * Server component; params is Promise per Next.js 16.
 */
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import type { Route } from "next";

import { getRecipe, getMock } from "@/lib/te-mock/recipes";
import {
  getCountryRecipeMatch,
  getMatchStaticParams,
  type MatchAnalogue,
} from "@/lib/te-mock/country-recipe-match";
import {
  getRecipeV4Extras,
  getFallbackExtras,
  getCountriesFull,
} from "@/lib/te-mock/recipe-v4-1-mock";
import { getRecipeFullScoreMap } from "@/lib/te-mock/risk-board-data";
import { familyColor as familyColorFn } from "@/lib/te-mock/l1-families";
import { flagFor, iso2For } from "@/lib/te-mock/country-flags";
import { analogueHref } from "@/lib/te-mock/analogue-href";
import { MUTED_GRAY, confidenceT, lerpHexToRgb, confidenceGlow } from "@/lib/color-lerp";

import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { PanelShell } from "@/components/countries-v4-1/PanelShell";
import { MiniSparkline } from "@/components/countries-v4-1/MiniSparkline";
import { RecipeIcon } from "@/components/te-v4-shared/RecipeIcon";
import { HowToReadButton } from "@/components/te-v4-shared/HowToReadButton";
import {
  MatchAlignmentPanel,
  CompositeOverlayPanel,
} from "@/components/recipe-country/MatchAlignmentPanel";
import { CountriesPanel } from "@/components/precedents-v4-1/CountriesPanel";
import { TrendConfirmRejectPanel } from "@/components/precedents-v4-1/TrendConfirmRejectPanel";
import { getTrendNewsSignal } from "@/lib/hf/trend-signal";

interface Params {
  params: Promise<{ slug: string; iso: string }>;
}

export async function generateStaticParams() {
  return getMatchStaticParams();
}

/** Resolve a country display-name from an iso2 via the recipe's board score
 *  map (used on the degraded path for recipes outside the scored fleet). */
function resolveName(
  slug: string,
  iso2: string
): { name: string; score?: number } | null {
  const target = iso2.toLowerCase();
  const map = getRecipeFullScoreMap(slug);
  for (const name of Object.keys(map)) {
    if ((iso2For(name) ?? "").toLowerCase() === target) {
      return { name, score: map[name] };
    }
  }
  return null;
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug, iso } = await params;
  const recipe = getRecipe(slug);
  if (!recipe) return { title: "Match not found · QG Intelligence" };
  const match = getCountryRecipeMatch(slug, iso);
  const name = match?.countryName ?? resolveName(slug, iso)?.name ?? iso.toUpperCase();
  return {
    title: `${name} · ${recipe.label} · QG Intelligence`,
    description: `How ${name}'s recent signals are following the ${recipe.label} trend, signal by signal.`,
    robots: { index: false, follow: false },
  };
}

export default async function CountryRecipeMatchPage({ params }: Params) {
  const { slug, iso } = await params;
  const recipe = getRecipe(slug);
  if (!recipe) notFound();

  const familyColor = familyColorFn(recipe.l1_id, recipe.l1_color);
  const match = getCountryRecipeMatch(slug, iso);

  const degraded = match ? null : resolveName(slug, iso);
  const countryName = match?.countryName ?? degraded?.name ?? null;
  if (!countryName) notFound();

  const score = match?.score ?? degraded?.score;

  // News layer (HF merge step 3): the confirm/reject quadrant for this
  // country x trend. Renders only when the trend has a feeding theme AND
  // the country is in today's covered set.
  const newsSignal = getTrendNewsSignal(slug);
  const hasNewsRow = Boolean(
    newsSignal && countryName && newsSignal.rows.some((r) => r.name === countryName)
  );
  const lc = recipe.label.toLowerCase();
  const mock = getMock(recipe);
  const windowYears =
    match?.windowYears ?? Math.max(1, Math.round((mock.window ?? 12) / 4));

  return (
    <div
      style={{ minHeight: "100%", background: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      {/* ── Header band ── */}
      <div
        style={{
          borderBottom: "1px solid var(--qgi-border)",
          background: "var(--qgi-surface)",
        }}
      >
        <div style={{ maxWidth: "1080px", margin: "0 auto", padding: "20px 24px 24px" }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "16px",
              gap: "12px",
              flexWrap: "wrap",
            }}
          >
            <nav
              aria-label="Breadcrumb"
              style={{
                fontSize: "11px",
                letterSpacing: "0.3px",
                color: "var(--qgi-text-dim)",
                fontFamily: "ui-monospace, monospace",
              }}
            >
              <Link
                href={`/trends/${slug}` as Route}
                style={{ color: "var(--qgi-text-muted)", textDecoration: "none" }}
              >
                &larr; {recipe.label}
              </Link>
              <span style={{ margin: "0 8px", opacity: 0.5 }}>/</span>
              <span style={{ color: familyColor }}>{recipe.l1_label}</span>
              <span style={{ margin: "0 8px", opacity: 0.5 }}>/</span>
              <span>{countryName}</span>
            </nav>
            <HowToReadButton routeKey="recipe-country-match" />
          </div>

          <div
            style={{
              display: "flex",
              gap: "20px",
              alignItems: "flex-start",
              flexWrap: "wrap",
            }}
          >
            <div
              style={{
                width: "88px",
                height: "88px",
                background: "var(--qgi-bg)",
                border: `1px solid ${familyColor}`,
                borderRadius: "10px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
                overflow: "hidden",
              }}
            >
              <FlagImg
                emoji={flagFor(countryName)}
                name={countryName}
                width={64}
                radius={4}
              />
            </div>

            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  marginBottom: "10px",
                  flexWrap: "wrap",
                }}
              >
                <Link
                  href={`/trends/${slug}` as Route}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                    fontSize: "11px",
                    padding: "3px 9px",
                    border: "1px solid var(--qgi-border)",
                    color: "var(--qgi-text-muted)",
                    borderRadius: "4px",
                    letterSpacing: "0.3px",
                    fontFamily: "ui-monospace, monospace",
                    textDecoration: "none",
                  }}
                  title={`Open the full ${recipe.label} trend`}
                >
                  <span style={{ color: familyColor, display: "inline-flex" }}>
                    <RecipeIcon recipeId={recipe.recipe_id} size={13} strokeWidth={1.8} />
                  </span>
                  {recipe.label}
                </Link>
              </div>

              <h1
                style={{
                  fontSize: "30px",
                  fontWeight: 600,
                  lineHeight: 1.15,
                  margin: "0 0 6px",
                }}
              >
                {countryName} is following the {lc} trend
              </h1>
              <p
                style={{
                  color: "var(--qgi-text-muted)",
                  fontSize: "13px",
                  margin: "0 0 16px",
                  fontFamily: "ui-monospace, monospace",
                  letterSpacing: "0.3px",
                }}
              >
                {recipe.l1_label} · {windowYears}-year window
                {match ? ` · ${match.nScored} countries scored` : ""}
              </p>

              {typeof score === "number" ? (
                <ConfidenceFigure
                  score={score}
                  familyColor={familyColor}
                  rank={match?.rank}
                  nScored={match?.nScored}
                />
              ) : null}

              <p
                style={{
                  maxWidth: "720px",
                  fontSize: "15px",
                  lineHeight: 1.65,
                  color: "var(--qgi-text)",
                  margin: "16px 0 0",
                }}
              >
                {match && typeof score === "number"
                  ? `A score of ${Math.round(score)} means ${countryName}'s recent signals have been moving the way they moved before ${lc} in the cases on record. It is a measure of resemblance, not a forecast, and it does not mean a ${Math.round(score)}% chance of anything.`
                  : `This page shows how closely ${countryName}'s recent signals are following the ${lc} trend. The signal-by-signal view fills in once this trend enters scoring.`}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* ── Body ── */}
      <div style={{ maxWidth: "1080px", margin: "0 auto", padding: "24px 24px 64px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          {hasNewsRow &&
            newsSignal &&
            newsSignal.status === "live" &&
            !newsSignal.pulseOnly &&
            countryName && (
              <TrendConfirmRejectPanel
                key={`cr-${slug}-${iso}`}
                slug={slug}
                trendLabel={recipe.label}
                countryName={countryName}
                signal={newsSignal}
              />
            )}
          {match ? (
            <>
              <MatchAlignmentPanel
                familyColor={familyColor}
                countryName={countryName}
                evalYear={match.evalYear}
                zone={match.zone}
                zoneLabel={match.zoneLabel}
                indicators={match.indicators}
              />

              {match.composite.length > 1 && (
                <CompositeOverlayPanel
                  familyColor={familyColor}
                  countryName={countryName}
                  windowYears={match.windowYears}
                  evalYear={match.evalYear}
                  composite={match.composite}
                  analogues={match.analogues}
                />
              )}

              {match.momentumByYear.length > 1 && (
                <MomentumPanel
                  familyColor={familyColor}
                  countryName={countryName}
                  momentumByYear={match.momentumByYear}
                  momentumLabel={match.momentumLabel}
                />
              )}

              <PeerContext
                slug={slug}
                familyColor={familyColor}
                highlightName={countryName}
              />

              {match.analogues.length > 0 && (
                <AnaloguesPanel
                  familyColor={familyColor}
                  countryName={countryName}
                  subjectIso2={iso.toLowerCase()}
                  analogues={match.analogues}
                />
              )}
            </>
          ) : (
            <PanelShell
              title={`How ${countryName} is following this trend`}
              accent={familyColor}
            >
              <p
                style={{
                  fontSize: "13px",
                  lineHeight: 1.6,
                  color: "var(--qgi-text-muted)",
                  margin: 0,
                }}
              >
                {countryName}&apos;s signal-by-signal match on this trend is being
                computed for this release. It will show how {countryName}&apos;s own path
                moves against the historical cases it most resembles, as soon as the trend
                enters scoring.
              </p>
            </PanelShell>
          )}

          <ProvenancePanel
            slug={slug}
            familyColor={familyColor}
            countryName={countryName}
            recipeLabel={recipe.label}
            vintage={match?.vintage}
          />
        </div>
      </div>
    </div>
  );
}

/* ── Hero confidence figure ── */
function ConfidenceFigure({
  score,
  familyColor,
  rank,
  nScored,
}: {
  score: number;
  familyColor: string;
  rank?: number;
  nScored?: number;
}) {
  const cT = confidenceT(score);
  const color = lerpHexToRgb(MUTED_GRAY, familyColor, cT);
  const glow = confidenceGlow(familyColor, cT);
  return (
    <div
      style={{ display: "flex", alignItems: "flex-end", gap: "16px", flexWrap: "wrap" }}
    >
      <div style={{ display: "flex", alignItems: "flex-end", gap: "10px" }}>
        <span
          style={{
            fontSize: "56px",
            fontWeight: 700,
            color,
            fontFamily: "ui-monospace, monospace",
            lineHeight: 0.95,
            letterSpacing: "-2px",
            textShadow: glow || undefined,
          }}
        >
          {Math.round(score)}
        </span>
        <span
          style={{
            fontSize: "11px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.6px",
            paddingBottom: "10px",
            textTransform: "uppercase",
            maxWidth: "180px",
            lineHeight: 1.3,
          }}
        >
          Resemblance to the trend
        </span>
      </div>
      {typeof rank === "number" && typeof nScored === "number" && (
        <span
          style={{
            fontSize: "11px",
            padding: "4px 10px",
            border: "1px solid var(--qgi-border)",
            background: "var(--qgi-surface)",
            color: "var(--qgi-text-muted)",
            borderRadius: "4px",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.3px",
            marginBottom: "10px",
          }}
        >
          #{rank} of {nScored} countries scored
        </span>
      )}
    </div>
  );
}

/* ── Momentum: score across recent years ── */
function MomentumPanel({
  familyColor,
  countryName,
  momentumByYear,
  momentumLabel,
}: {
  familyColor: string;
  countryName: string;
  momentumByYear: Array<{ year: string; score: number }>;
  momentumLabel: string | null;
}) {
  const first = momentumByYear[0].score;
  const last = momentumByYear[momentumByYear.length - 1].score;
  const delta = last - first;
  const trend =
    momentumLabel ??
    (delta > 1.5 ? "rising" : delta < -1.5 ? "easing" : "holding steady");
  const values = momentumByYear.map((m) => m.score);

  return (
    <PanelShell
      title="How the resemblance has moved"
      accent={familyColor}
      caption={`${countryName}'s score on this trend across recent years. The line stops at today and is not drawn forward.`}
    >
      <div
        style={{ display: "flex", alignItems: "center", gap: "20px", flexWrap: "wrap" }}
      >
        <div style={{ display: "flex", alignItems: "baseline", gap: "10px" }}>
          <span
            style={{
              fontSize: "13px",
              color: familyColor,
              fontWeight: 600,
              textTransform: "capitalize",
            }}
          >
            {trend}
          </span>
          <span
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: "11px",
              color: "var(--qgi-text-dim)",
            }}
          >
            {momentumByYear[0].year} &rarr;{" "}
            {momentumByYear[momentumByYear.length - 1].year}
          </span>
        </div>
        <MiniSparkline
          values={values}
          color={familyColor}
          width={220}
          height={36}
          min={0}
          max={100}
        />
        <span
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "20px",
            fontWeight: 700,
            color: "var(--qgi-text)",
          }}
        >
          {Math.round(last)}
        </span>
      </div>
    </PanelShell>
  );
}

/* ── Peer context (reuses the recipe page's Countries panel) ── */
function PeerContext({
  slug,
  familyColor,
  highlightName,
}: {
  slug: string;
  familyColor: string;
  highlightName: string;
}) {
  const extras = getRecipeV4Extras(slug) ?? getFallbackExtras(slug);
  const mock = getMock(getRecipe(slug)!);
  const countriesFull = getCountriesFull(slug);
  if ((mock.countriesTop?.length ?? 0) === 0) return null;
  return (
    <CountriesPanel
      familyColor={familyColor}
      countriesTop={mock.countriesTop}
      countriesBottom={extras.countriesBottom}
      countriesFull={countriesFull}
      showResults
      recipeId={slug}
      highlightName={highlightName}
    />
  );
}

/* ── Historical analogues ── */
function AnaloguesPanel({
  familyColor,
  countryName,
  subjectIso2,
  analogues,
}: {
  familyColor: string;
  countryName: string;
  subjectIso2: string;
  analogues: MatchAnalogue[];
}) {
  const anyOutcome = analogues.some((a) => a.event || a.whatHappenedNext);
  return (
    <PanelShell
      title="Closest historical analogues"
      accent="#B6924A"
      caption={`Past situations whose pre-event path most resembles ${countryName} on this trend right now, and the real event each one was running up to. Similarity is not prediction; every case is its own history.`}
    >
      <ul
        style={{
          listStyle: "none",
          padding: 0,
          margin: 0,
          display: "flex",
          flexDirection: "column",
          gap: "2px",
        }}
      >
        {analogues.map((a) => {
          // Per-row "compare" link. The row itself is NOT wrapped in a Link
          // because it can contain an event-source <a> — a nested <a> is
          // invalid HTML and breaks hydration. So only "compare →" is the link.
          const href = analogueHref(subjectIso2, a.iso2, a.year);
          return (
            <li
              key={`${a.country}-${a.year}`}
              style={{
                display: "grid",
                gridTemplateColumns: "20px minmax(0, 1fr) auto",
                gap: "10px",
                alignItems: "center",
                padding: "9px 4px",
                borderBottom: "1px solid var(--qgi-border)",
              }}
            >
              <FlagImg
                emoji={flagFor(a.country)}
                name={a.country}
                width={16}
                radius={2}
              />
              <span style={{ fontSize: "13px", color: "var(--qgi-text)" }}>
                {a.country}, {a.year}
                {a.weak && (
                  <span
                    style={{
                      fontSize: "10px",
                      color: "var(--qgi-text-dim)",
                      fontFamily: "ui-monospace, monospace",
                      marginLeft: "8px",
                    }}
                    title="A weaker match; read with care."
                  >
                    weaker match
                  </span>
                )}
                {a.event ? (
                  <span
                    style={{
                      display: "block",
                      fontSize: "12px",
                      color: "var(--qgi-text-muted)",
                      lineHeight: 1.5,
                      marginTop: "3px",
                    }}
                  >
                    {a.event.title}
                    {a.event.source ? (
                      <>
                        {" "}
                        <a
                          href={a.event.source}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{
                            color: "var(--qgi-text-dim)",
                            fontFamily: "ui-monospace, monospace",
                            fontSize: "10px",
                            textDecoration: "none",
                            borderBottom: "1px dotted var(--qgi-border)",
                            whiteSpace: "nowrap",
                          }}
                          title={`Source: ${a.event.sourceDomain ?? a.event.source}`}
                        >
                          {a.event.sourceDomain ?? "source"} ↗
                        </a>
                      </>
                    ) : null}
                  </span>
                ) : a.whatHappenedNext ? (
                  <span
                    style={{
                      display: "block",
                      fontSize: "12px",
                      color: "var(--qgi-text-muted)",
                      lineHeight: 1.5,
                      marginTop: "3px",
                    }}
                  >
                    {a.whatHappenedNext}
                  </span>
                ) : null}
              </span>
              <span
                style={{
                  fontFamily: "ui-monospace, monospace",
                  fontSize: "13px",
                  fontWeight: 700,
                  color: familyColor,
                  alignSelf: "start",
                  textAlign: "right",
                }}
              >
                {a.matchPct}% match
                {href && (
                  <Link
                    href={href as Route}
                    aria-label={`Compare ${countryName} with ${a.country} ${a.year}`}
                    style={{
                      display: "block",
                      fontSize: "9.5px",
                      fontWeight: 600,
                      color: familyColor,
                      letterSpacing: "0.3px",
                      marginTop: "2px",
                      textDecoration: "none",
                    }}
                  >
                    compare &rarr;
                  </Link>
                )}
              </span>
            </li>
          );
        })}
      </ul>
      {!anyOutcome && (
        <p
          style={{
            margin: "12px 0 0",
            fontSize: "11px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            fontStyle: "italic",
            letterSpacing: "0.2px",
          }}
        >
          No verified event of this kind sits close to these analogue years in our records
          yet.
        </p>
      )}
    </PanelShell>
  );
}

/* ── Provenance + honesty + cross-links ── */
function ProvenancePanel({
  slug,
  familyColor,
  countryName,
  recipeLabel,
  vintage,
}: {
  slug: string;
  familyColor: string;
  countryName: string;
  recipeLabel: string;
  vintage?: string;
}) {
  return (
    <PanelShell title="How to read this, and where it comes from" accent="#5B7E99">
      <p
        style={{
          fontSize: "13px",
          lineHeight: 1.6,
          color: "var(--qgi-text-muted)",
          margin: "0 0 12px",
        }}
      >
        The score is a resemblance rank, not a probability. The white line shows{" "}
        {countryName}&apos;s recent movement and stops at today; it is never drawn
        forward. The faint lines are real historical cases, shown for comparison. Nothing
        here is a forecast.
      </p>
      <div
        style={{ display: "flex", gap: "16px", flexWrap: "wrap", alignItems: "center" }}
      >
        <Link
          href={`/trends/${slug}` as Route}
          style={{
            fontSize: "12px",
            color: familyColor,
            textDecoration: "none",
            fontFamily: "ui-monospace, monospace",
            border: `1px solid ${familyColor}`,
            background: `${familyColor}14`,
            padding: "5px 11px",
            borderRadius: "4px",
            letterSpacing: "0.3px",
          }}
        >
          See the full {recipeLabel} trend &rarr;
        </Link>
        {vintage && (
          <span
            style={{
              fontSize: "11px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
              letterSpacing: "0.3px",
            }}
          >
            Release {vintage.slice(0, 10)} · scores refresh each quarter
          </span>
        )}
      </div>
    </PanelShell>
  );
}
