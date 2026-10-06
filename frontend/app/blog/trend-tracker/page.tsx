/**
 * /blog/trend-tracker — the live trend status board.
 *
 * 2026-06-05: renamed from /blog/recipe-tracker (founder direction: the
 * concept is called Trends everywhere users see it; "recipe" stays pipeline
 * vocabulary only). The old slug 308s here via next.config. Data refreshed
 * to the te-fleet-run-2 vintage.
 *
 * 2026-06-06 alignment with /trends (founder catch): "in play" is the
 * audience word for EVERY walked trend (all 44 this vintage — the /trends
 * gallery chips them all "in play" per the ratified two-bucket vocabulary,
 * and the dashboard surfaces scores from all 44). The tier ladder
 * (directional / experimental) grades confidence WITHIN the in-play set, it
 * does not gate visibility. Walked cards all render stats and link to their
 * /trends page; only the 27 not-yet-walked are inert ("Coming soon").
 */
import type { Metadata } from "next";
import type { Route } from "next";
import Link from "next/link";
import { Wordmark } from "@/components/brand/Wordmark";
import {
  loadRecipeTracker,
  groupByFamily,
  tierBadgeLabel,
  type Recipe,
  type RecipeFamily,
} from "@/lib/recipe-tracker";

export const metadata: Metadata = {
  title: "Trend Tracker · QG Intelligence",
  description:
    "Live status board for all 69 QGI trends. 42 in play on the dashboard (8 directional, 34 experimental on the confidence ladder), 27 coming soon. Every trend walks the same validation gates in held-out historical data.",
  alternates: { canonical: "https://qgintelligence.com/blog/trend-tracker" },
  openGraph: {
    title: "Trend Tracker · QG Intelligence",
    description:
      "Live status board for all 69 QGI trends: 42 in play, graded on a confidence ladder, and 27 coming soon.",
    url: "https://qgintelligence.com/blog/trend-tracker",
    siteName: "QG Intelligence",
    type: "website",
  },
  twitter: {
    card: "summary",
    title: "Trend Tracker · QG Intelligence",
    description:
      "69 QGI trends: 42 in play (8 directional, 34 experimental), 27 coming soon. Every score is gated on validation against held-out history.",
  },
};

// ---------------------------------------------------------------------------
// Sub-components (server — no client boundary needed)
// ---------------------------------------------------------------------------

function StatChip({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="flex flex-col items-center gap-0.5">
      <dt
        className="text-[9px] tracking-widest uppercase font-semibold"
        style={{ color: accent ? "var(--qgi-success)" : "var(--qgi-text-dim)" }}
      >
        {label}
      </dt>
      <dd
        className="font-data tabular-nums text-sm font-semibold"
        style={{ color: accent ? "var(--qgi-success)" : "var(--qgi-text)" }}
      >
        {value}
      </dd>
    </div>
  );
}

function TierBadge({ tier }: { tier: Recipe["tier"] }) {
  const label = tierBadgeLabel(tier);
  const color: string =
    tier === "validated" || tier === "directional"
      ? "var(--qgi-success)"
      : tier === "experimental"
        ? "var(--qgi-text-muted)"
        : "var(--qgi-text-dim)";
  return (
    <span
      className="text-[9px] tracking-widest uppercase font-semibold"
      style={{ color }}
    >
      {label}
    </span>
  );
}

/**
 * Any walked trend — in play on the dashboard, stats populated, card links
 * to its /trends page (mirroring the gallery, where all 44 are clickable).
 * Directional/validated trends carry the emphatic treatment (family glow,
 * accent score); experimental trends render the same anatomy, muted.
 */
function WalkedCard({ recipe }: { recipe: Recipe }) {
  const stats = recipe.stats ?? {};
  const l1Color = recipe.l1_color;
  const emphatic = recipe.tier === "directional" || recipe.tier === "validated";
  const href = `/trends/${recipe.recipe_id}` as Route;
  const ci =
    stats.ci95_lo !== undefined && stats.ci95_hi !== undefined
      ? `${stats.ci95_lo.toFixed(2)}–${stats.ci95_hi.toFixed(2)}`
      : null;

  return (
    // h-full: every card fills its grid cell so cards in a row share a height
    // regardless of title wrapping / sublabel presence; the stats band pins
    // to the bottom edge (mt-auto) so the row reads as one aligned band.
    <li className="h-full">
      <Link
        href={href}
        aria-label={`${recipe.label}: ${tierBadgeLabel(recipe.tier).toLowerCase()}, open the trend page`}
        className="block h-full rounded-lg overflow-hidden transition-transform hover:-translate-y-0.5"
        style={{
          backgroundColor: "var(--qgi-surface)",
          border: `1px solid ${l1Color}${emphatic ? "40" : "26"}`,
          borderLeft: `3px solid ${l1Color}${emphatic ? "" : "80"}`,
          boxShadow: emphatic
            ? `0 0 16px ${l1Color}22, 0 1px 4px rgba(0,0,0,0.3)`
            : "0 1px 4px rgba(0,0,0,0.3)",
        }}
      >
        <div className="p-4 h-full flex flex-col">
          {/* Header row */}
          <div className="flex items-start justify-between gap-2 mb-3">
            <div>
              <div className="mb-1">
                <TierBadge tier={recipe.tier} />
              </div>
              <h3
                className="text-base font-semibold leading-tight"
                style={{ color: emphatic ? "var(--qgi-text)" : "var(--qgi-text-muted)" }}
              >
                {recipe.label}
              </h3>
              {recipe.l2_label !== recipe.label && (
                <p
                  className="text-[11px] mt-0.5"
                  style={{ color: "var(--qgi-text-dim)" }}
                >
                  {recipe.l2_label}
                </p>
              )}
            </div>
            {/* Arrow affordance */}
            <span
              className="text-sm mt-0.5 flex-shrink-0"
              style={{ color: emphatic ? l1Color : "var(--qgi-text-dim)" }}
              aria-hidden="true"
            >
              &rarr;
            </span>
          </div>

          {/* Stats band — populated for every walked trend; bottom-pinned */}
          <dl
            className="flex flex-wrap gap-x-5 gap-y-2 pt-3 mt-auto"
            style={{ borderTop: `1px solid ${l1Color}${emphatic ? "30" : "1c"}` }}
          >
            {stats.loco_auc !== undefined && (
              <StatChip
                label="OOC score"
                value={stats.loco_auc.toFixed(2)}
                accent={emphatic}
              />
            )}
            {ci && <StatChip label="95% CI" value={ci} />}
            {stats.window_y !== undefined && (
              <StatChip label="Window" value={`${stats.window_y}y`} />
            )}
            {stats.n_indicators !== undefined && (
              <StatChip label="Signals" value={String(stats.n_indicators)} />
            )}
          </dl>
        </div>
      </Link>
    </li>
  );
}

/** A trend not yet walked — inert, dimmed, mirroring /trends "Coming soon". */
function ComingSoonCard({ recipe }: { recipe: Recipe }) {
  const l1Color = recipe.l1_color;

  return (
    // h-full so a coming-soon card sharing a row with walked cards (at a tier
    // boundary) stretches to the row height instead of floating shorter.
    <li className="h-full">
      <div
        role="article"
        aria-label={`${recipe.label}: coming soon, validation not yet started`}
        className="block h-full rounded-lg overflow-hidden"
        style={{
          backgroundColor: "var(--qgi-surface)",
          border: `1px solid ${l1Color}18`,
          borderLeft: `3px solid ${l1Color}30`,
          cursor: "default",
          opacity: 0.55,
        }}
      >
        <div className="p-4">
          <div className="mb-1">
            <TierBadge tier={recipe.tier} />
          </div>
          <h3
            className="text-sm font-medium leading-tight"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            {recipe.label}
          </h3>
          {recipe.l2_label !== recipe.label && (
            <p className="text-[11px] mt-0.5" style={{ color: "var(--qgi-text-dim)" }}>
              {recipe.l2_label}
            </p>
          )}
        </div>
      </div>
    </li>
  );
}

function TrendCard({ recipe }: { recipe: Recipe }) {
  if (recipe.tier === "queued") return <ComingSoonCard recipe={recipe} />;
  return <WalkedCard recipe={recipe} />;
}

const TIER_ORDER: Record<Recipe["tier"], number> = {
  validated: 0,
  directional: 1,
  experimental: 2,
  queued: 3,
};

function FamilySection({ family }: { family: RecipeFamily }) {
  const ordered = [...family.recipes].sort(
    (a, b) => TIER_ORDER[a.tier] - TIER_ORDER[b.tier] || a.label.localeCompare(b.label)
  );

  return (
    <section aria-labelledby={`family-${family.l1_id}`}>
      {/* Family header */}
      <div
        className="flex items-center gap-3 mb-5 pb-2"
        style={{ borderBottom: `1px solid ${family.l1_color}30` }}
      >
        <div
          className="w-2 h-6 rounded-sm flex-shrink-0"
          style={{ backgroundColor: family.l1_color }}
          aria-hidden="true"
        />
        <h2
          id={`family-${family.l1_id}`}
          className="text-base sm:text-sm font-semibold tracking-wider uppercase"
          style={{ color: family.l1_color }}
        >
          {family.l1_label}
        </h2>
        <span
          className="text-[11px] font-data tabular-nums ml-auto"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          {family.recipes.length}
        </span>
      </div>

      {/* Card grid */}
      <ul
        className="grid gap-3"
        style={{
          gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 220px), 1fr))",
        }}
      >
        {ordered.map((recipe) => (
          <TrendCard key={recipe.recipe_id} recipe={recipe} />
        ))}
      </ul>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default async function TrendTrackerPage() {
  const data = await loadRecipeTracker();
  const families = groupByFamily(data.recipes);

  const validatedCount = data.tier_counts.validated ?? 0;
  const directionalCount = data.tier_counts.directional ?? 0;
  const experimentalCount = data.tier_counts.experimental ?? 0;
  const comingSoonCount = data.tier_counts.queued ?? 0;
  // "In play" is the audience word for every walked trend — it matches the
  // /trends gallery chips and the dashboard, which scores all of them.
  const inPlayCount = validatedCount + directionalCount + experimentalCount;

  return (
    <div
      className="min-h-full"
      style={{ backgroundColor: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      {/* Sticky header */}
      <header
        className="sticky top-0 z-50 border-b backdrop-blur-md"
        style={{
          borderColor: "var(--qgi-border)",
          backgroundColor: "var(--qgi-bg-translucent)",
        }}
      >
        <div className="mx-auto max-w-5xl flex items-center justify-between px-6 py-4">
          <Wordmark variant="nav" href={"/" as Route} title="Home" />
          <Link
            href={"/blog" as Route}
            className="text-xs tracking-wider uppercase"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            &larr; All posts
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-16">
        {/* Page hero */}
        <div className="mb-12">
          {/* Eyebrow with LIVE badge */}
          <div className="flex items-center gap-2 mb-3">
            <span
              className="text-[10px] tracking-widest uppercase font-semibold"
              style={{ color: "var(--qgi-accent)" }}
            >
              Blog
            </span>
            <span
              className="text-[10px] tracking-widest uppercase"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              &middot;
            </span>
            {/* LIVE badge */}
            <span className="flex items-center gap-1.5">
              <span
                className="qgi-live-dot"
                aria-hidden="true"
                style={{
                  display: "inline-block",
                  width: "7px",
                  height: "7px",
                  borderRadius: "50%",
                  backgroundColor: "var(--qgi-success)",
                  animation: "qgi-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
                }}
              />
              <span
                className="text-[10px] tracking-widest uppercase font-semibold"
                style={{ color: "var(--qgi-success)" }}
              >
                Live
              </span>
            </span>
          </div>

          <h1 className="text-3xl font-semibold mb-4">Trend Tracker</h1>

          {/* Status summary chips. "In play" = every walked trend (matches the
              /trends gallery); the directional/experimental chips break the
              in-play set down by confidence tier. When the first trend reaches
              "validated", add its own chip here rather than letting the
              directional count silently absorb it. */}
          <div className="flex flex-wrap gap-3 mb-3">
            <div
              className="flex items-center gap-2 px-3 py-1.5 rounded text-xs"
              style={{
                backgroundColor: "rgba(52, 211, 153, 0.08)",
                border: "1px solid rgba(52, 211, 153, 0.2)",
              }}
            >
              <span
                className="font-data tabular-nums font-semibold"
                style={{ color: "var(--qgi-success)" }}
              >
                {inPlayCount}
              </span>
              <span style={{ color: "var(--qgi-text-muted)" }}>In play</span>
            </div>
            <div
              className="flex items-center gap-2 px-3 py-1.5 rounded text-xs"
              style={{
                backgroundColor: "rgba(52, 211, 153, 0.04)",
                border: "1px solid rgba(52, 211, 153, 0.12)",
              }}
            >
              <span
                className="font-data tabular-nums font-semibold"
                style={{ color: "var(--qgi-text-muted)" }}
              >
                {directionalCount}
              </span>
              <span style={{ color: "var(--qgi-text-muted)" }}>Directional</span>
            </div>
            <div
              className="flex items-center gap-2 px-3 py-1.5 rounded text-xs"
              style={{
                backgroundColor: "rgba(138, 166, 190, 0.08)",
                border: "1px solid rgba(138, 166, 190, 0.2)",
              }}
            >
              <span
                className="font-data tabular-nums font-semibold"
                style={{ color: "var(--qgi-text-muted)" }}
              >
                {experimentalCount}
              </span>
              <span style={{ color: "var(--qgi-text-muted)" }}>Experimental</span>
            </div>
            <div
              className="flex items-center gap-2 px-3 py-1.5 rounded text-xs"
              style={{
                backgroundColor: "rgba(138, 166, 190, 0.06)",
                border: "1px solid rgba(138, 166, 190, 0.15)",
              }}
            >
              <span
                className="font-data tabular-nums font-semibold"
                style={{ color: "var(--qgi-text-muted)" }}
              >
                {comingSoonCount}
              </span>
              <span style={{ color: "var(--qgi-text-dim)" }}>Coming soon</span>
            </div>
            <div
              className="flex items-center gap-2 px-3 py-1.5 rounded text-xs"
              style={{
                backgroundColor: "var(--qgi-surface)",
                border: "1px solid var(--qgi-border)",
              }}
            >
              <span
                className="font-data tabular-nums font-semibold"
                style={{ color: "var(--qgi-text)" }}
              >
                {data.n_recipes}
              </span>
              <span style={{ color: "var(--qgi-text-dim)" }}>Total</span>
            </div>
          </div>

          {/* One global reading note instead of one per card */}
          <p className="text-[12px] mb-8" style={{ color: "var(--qgi-text-muted)" }}>
            Scores are out-of-country similarity on held-out history, not calibrated
            probabilities.
          </p>

          {/* Intro paragraph */}
          <div
            className="rounded-lg p-6"
            style={{
              backgroundColor: "var(--qgi-surface)",
              borderLeft: "3px solid var(--qgi-accent)",
            }}
          >
            <p
              className="text-base leading-relaxed"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              QGI reads every country against {data.n_recipes} trends, named patterns of
              geopolitical change, and every trend earns its standing the same way: a walk
              through validation gates in held-out historical data. This board is the
              index of that program.{" "}
              <strong style={{ color: "var(--qgi-text)" }}>
                {inPlayCount} trends are in play
              </strong>
              : walked under the Trajectory Engine and live across the dashboard, each
              scored on how well it separates the years before an event from quiet years
              in countries the model never trained on. Within them, the confidence ladder
              grades the result:{" "}
              <strong style={{ color: "var(--qgi-text)" }}>
                {directionalCount} are directional
              </strong>
              , the strongest separations of this vintage, and{" "}
              <strong style={{ color: "var(--qgi-text)" }}>
                {experimentalCount} are experimental
              </strong>
              , weaker separations to read with more caution. The remaining{" "}
              <strong style={{ color: "var(--qgi-text)" }}>
                {comingSoonCount} are coming soon
              </strong>
              : not yet walked. The bar is set in held-out history, and most trends will
              not top the ladder on a given walk: that is the point of having one. The
              board updates with every fleet run.
            </p>
          </div>
        </div>

        {/* Inline keyframe for the LIVE dot — scoped to this page */}
        <style>{`
          @keyframes qgi-pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
          }
        `}</style>

        {/* Family sections */}
        <div className="space-y-14">
          {families.map((family) => (
            <FamilySection key={family.l1_id} family={family} />
          ))}
        </div>

        {/* Footer */}
        <footer
          className="mt-16 pt-8 border-t text-xs"
          style={{
            borderColor: "var(--qgi-border)",
            color: "var(--qgi-text-dim)",
          }}
        >
          <p>
            Updated {data.generated} &middot; vintage {data.vintage_current} &middot; QG
            Intelligence &middot; {data.n_recipes} trends across 8 families.
          </p>
          <p className="mt-2">
            <Link
              href={"/methodology" as Route}
              className="underline underline-offset-2 transition-colors"
              style={{ color: "var(--qgi-accent)" }}
            >
              Full methodology
            </Link>
            {" · "}
            <Link
              href={"/trends" as Route}
              className="underline underline-offset-2 transition-colors"
              style={{ color: "var(--qgi-accent)" }}
            >
              Browse the trend catalog
            </Link>
          </p>
        </footer>
      </main>
    </div>
  );
}
