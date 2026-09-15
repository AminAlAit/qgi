import Link from "next/link";
import type { Route } from "next";
import { CountryFlag } from "@/components/design/CountryFlag";
import { countrySlug } from "@/lib/slug";

/**
 * #729 Step 2 (precedents side) — Top countries by Precedent Match for
 * this recipe.
 *
 * Per the 2026-05-16 per-recipe Majles (Elif + Sunita's mandate):
 *  - Reciprocal of the per-recipe strip on /countries/[iso]
 *  - Top-10 countries by Precedent Match score on THIS recipe
 *  - Country flag + name + score + CI per row
 *  - Click-through → /signals/[country]/[slug] (country-anchored, per Elif)
 *  - Renders above the historical analogue panel per Elif's placement
 *
 * Server Component. Graceful degradation: returns null if the recipe
 * isn't in the per-recipe bake (pre-#728), or fewer than 3 countries
 * have valid scores (below MIN_LEADERBOARD_COUNT).
 *
 * NAMING: Uses "Precedent Match" (Ingrid's veto on inheriting "Risk
 * Score" — see PrecedentMatchStrip on /countries/[iso] for parity).
 */

const MIN_LEADERBOARD_COUNT = 3;
const TOP_N = 10;

export interface LeaderboardEntry {
  countryId: string;
  countryName: string;
  alpha_2: string;
  score: number;
  ci_low: number;
  ci_high: number;
}

export function PrecedentMatchLeaderboard({
  recipeId,
  recipeDisplayName,
  entries,
  cohortN,
}: {
  recipeId: string;
  recipeDisplayName: string;
  entries: ReadonlyArray<LeaderboardEntry>;
  cohortN?: number;
}) {
  if (entries.length < MIN_LEADERBOARD_COUNT) return null;
  const top = entries.slice(0, TOP_N);

  return (
    <section
      aria-labelledby={`leaderboard-heading-${recipeId}`}
      className="max-w-3xl mx-auto px-6 lg:px-8 mt-8 mb-6"
    >
      <div className="mb-3 flex items-baseline justify-between flex-wrap gap-2">
        <h2
          id={`leaderboard-heading-${recipeId}`}
          className="text-[11px] tracking-widest uppercase font-semibold"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          Top countries by Precedent Match
          {cohortN !== undefined && (
            <span
              className="ml-2 font-data tabular-nums normal-case tracking-normal"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              · cohort N={cohortN}
            </span>
          )}
        </h2>
        <span
          className="text-[10px]"
          style={{ color: "var(--qgi-text-dim)" }}
          title="Percentile rank of each country's salience for this recipe within the recipe's cohort. NOT a probability the event will occur."
        >
          [Verified data] live from current bake
        </span>
      </div>

      <div
        className="rounded-lg border overflow-hidden"
        style={{
          backgroundColor: "var(--qgi-surface)",
          borderColor: "var(--qgi-border)",
        }}
      >
        <ol className="divide-y" style={{ borderColor: "var(--qgi-border)" }}>
          {top.map((row, idx) => {
            const cslug = countrySlug(row.countryName) ?? row.alpha_2.toLowerCase();
            // Click-through anchored to country/recipe leaf per Elif's mandate.
            const href = `/signals/${cslug}/${recipeId}` as Route;
            const fillPct = Math.max(0, Math.min(100, row.score));
            const opacity = 0.25 + 0.75 * (fillPct / 100);
            return (
              <li key={row.countryId}>
                <Link
                  href={href}
                  className="block px-4 py-2.5 transition-colors hover:bg-[var(--qgi-surface-2)]"
                  title={`${row.countryName}: Precedent Match ${row.score}/100 on ${recipeDisplayName}. Percentile rank within the recipe's cohort. NOT a probability.`}
                >
                  <div
                    className="grid items-center gap-3"
                    style={{
                      gridTemplateColumns: "32px minmax(0, 1.4fr) minmax(0, 2fr) 90px",
                    }}
                  >
                    <span
                      className="font-data tabular-nums text-[11px]"
                      style={{ color: "var(--qgi-text-dim)" }}
                    >
                      #{idx + 1}
                    </span>
                    <div className="flex items-center gap-2 min-w-0">
                      <CountryFlag
                        alpha2={row.alpha_2}
                        size={14}
                        countryName={row.countryName}
                      />
                      {/* #846 — country name links to country profile (structural peers live there).
                          Note: outer <Link> goes to the signal leaf; this inner <Link> goes to the
                          country profile. The outer block link still captures full-row click. */}
                      <Link
                        href={`/countries/${cslug}` as Route}
                        className="text-sm font-medium truncate hover:underline hover:text-[var(--qgi-accent)]"
                        style={{ color: "var(--qgi-text)" }}
                        title={`Go to ${row.countryName} country profile`}
                      >
                        {row.countryName}
                      </Link>
                    </div>
                    <div
                      className="relative h-2 rounded"
                      style={{ backgroundColor: "var(--qgi-surface-2)" }}
                    >
                      <div
                        className="absolute inset-y-0 left-0 rounded"
                        style={{
                          width: `${fillPct}%`,
                          backgroundColor: "var(--qgi-text)",
                          opacity,
                        }}
                        aria-label={`Precedent Match score: ${row.score} of 100`}
                      />
                    </div>
                    <div className="text-right">
                      <div
                        className="font-data tabular-nums text-sm font-semibold"
                        style={{ color: "var(--qgi-text)" }}
                      >
                        {row.score}
                      </div>
                      <div
                        className="text-[9px] font-data tabular-nums mt-0.5"
                        style={{ color: "var(--qgi-text-dim)" }}
                      >
                        [{row.ci_low}–{row.ci_high}]
                      </div>
                    </div>
                  </div>
                </Link>
              </li>
            );
          })}
        </ol>
      </div>

      <p className="text-[10px] mt-2" style={{ color: "var(--qgi-text-dim)" }}>
        Each row: percentile rank of the country&apos;s salience for this recipe within
        the cohort of countries firing on it. Higher = stronger pattern resemblance, not a
        probability the event will occur. Click any country to see the per-country,
        per-recipe signal leaf.
      </p>
    </section>
  );
}
