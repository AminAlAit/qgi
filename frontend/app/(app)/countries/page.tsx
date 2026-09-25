/**
 * /countries — Countries atlas, V4.1 quality bar.
 *
 * Parallel to /countries-v4 (left untouched). Built to the V4.1 bar:
 *   - honest copy in plain user language (no "M8-R5" / "walk" / "gate" /
 *     "Majles" / failure narrative; no rendered persona credit)
 *   - flagcdn image flags (FlagImg), never emoji (Win10 has no flag glyphs)
 *   - color = L1 family only; magnitude = number + neutral bar + sort
 *   - no em-dashes in copy
 *
 * Server component. Region filter + sort are a small client surface.
 * Mockup only. Local-only.
 */
import type { Metadata } from "next";
import { HowToReadButton } from "@/components/te-v4-shared/HowToReadButton";
import {
  COUNTRIES_V4,
  REGION_ORDER,
  COUNTRY_OF_THE_WEEK_ISO,
  countriesByRegion,
  type CountryV4,
} from "@/lib/te-mock/countries-v4-data";
import { CountriesV41Hero } from "@/components/countries-v4-1/CountriesV41Hero";
import { CountriesV41Filters } from "@/components/countries-v4-1/CountriesV41Filters";
import { CountryCardV41 } from "@/components/countries-v4-1/CountryCardV41";

export const metadata: Metadata = {
  title: "Country Atlas · QG Intelligence",
  description:
    "Per-country atlas: the trends each country resembles, the indicators behind each score, momentum, and historical analogues.",
};

interface PageProps {
  searchParams: Promise<{ region?: string; sort?: string }>;
}

export default async function CountriesV41Page({ searchParams }: PageProps) {
  const sp = await searchParams;
  const regionFilter = (sp.region ?? "").trim();
  const sortKey = (sp.sort ?? "compound") as "compound" | "lit" | "name";

  const total = COUNTRIES_V4.length;
  const litAny = COUNTRIES_V4.filter((c) => c.recipes_lit_count >= 1).length;
  const compoundHigh = COUNTRIES_V4.filter((c) => c.recipes_lit_count >= 3).length;
  const cotw =
    COUNTRIES_V4.find((c) => c.iso === COUNTRY_OF_THE_WEEK_ISO) ?? COUNTRIES_V4[0];

  // Global max compound so the neutral magnitude bars are comparable across
  // regions and filter states.
  const maxCompound = Math.max(...COUNTRIES_V4.map((c) => c.compound_score), 1);

  const filtered =
    regionFilter && (REGION_ORDER as readonly string[]).includes(regionFilter)
      ? COUNTRIES_V4.filter((c) => c.region === regionFilter)
      : COUNTRIES_V4;

  const sorted = [...filtered].sort((a: CountryV4, b: CountryV4) => {
    if (sortKey === "lit") return b.recipes_lit_count - a.recipes_lit_count;
    if (sortKey === "name") return a.name.localeCompare(b.name);
    return b.compound_score - a.compound_score;
  });

  const grouped = countriesByRegion(sorted);

  return (
    <div
      style={{ minHeight: "100%", background: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      <div style={{ maxWidth: "1280px", margin: "0 auto", padding: "24px" }}>
        {/* V4.1 §2: no inline vintage stamp — one stamp lives under TAKE THE TOUR
            in the global header. The 4 top stat tiles dropped per task #34 so
            the country grid is the primary surface. */}
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            alignItems: "center",
            gap: "8px",
            marginBottom: "16px",
          }}
        >
          <HowToReadButton routeKey="countries-v4.1" />
        </div>

        <CountriesV41Hero
          total={total}
          litAny={litAny}
          compoundHigh={compoundHigh}
          countryOfTheWeek={cotw}
        />

        <div data-tour="atlas-filters">
          <CountriesV41Filters
            regions={REGION_ORDER}
            activeRegion={regionFilter}
            activeSort={sortKey}
            totalShown={sorted.length}
          />
        </div>

        <div data-tour="atlas-grid">
          {REGION_ORDER.map((region) => {
            const inRegion = grouped[region] ?? [];
            if (inRegion.length === 0) return null;
            return (
              <section key={region} style={{ marginTop: "32px" }}>
                <header
                  style={{
                    display: "flex",
                    alignItems: "baseline",
                    gap: "12px",
                    marginBottom: "14px",
                  }}
                >
                  <span
                    style={{
                      fontSize: "10px",
                      letterSpacing: "1.5px",
                      fontFamily: "ui-monospace, monospace",
                      color: "var(--qgi-text-dim)",
                    }}
                  >
                    REGION
                  </span>
                  <h2
                    style={{
                      fontSize: "18px",
                      fontWeight: 600,
                      margin: 0,
                      color: "var(--qgi-text)",
                      flex: 1,
                    }}
                  >
                    {region}
                  </h2>
                  <span
                    style={{
                      fontSize: "10.5px",
                      color: "var(--qgi-text-muted)",
                      fontFamily: "ui-monospace, monospace",
                      letterSpacing: "0.3px",
                    }}
                  >
                    {inRegion.length} countries
                  </span>
                </header>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fill, minmax(248px, 1fr))",
                    gap: "14px",
                  }}
                >
                  {inRegion.map((c) => (
                    <CountryCardV41 key={c.iso} country={c} maxCompound={maxCompound} />
                  ))}
                </div>
              </section>
            );
          })}
        </div>

        <footer
          style={{
            marginTop: "48px",
            paddingTop: "20px",
            borderTop: "1px solid var(--qgi-border)",
            fontSize: "11px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.3px",
          }}
        >
          {total} countries in the corpus · {litAny} match at least one trend ·{" "}
          {compoundHigh} match 3 or more
        </footer>
      </div>
    </div>
  );
}
