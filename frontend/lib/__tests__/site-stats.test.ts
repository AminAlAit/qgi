/**
 * Site stats consistency check (#431).
 *
 * Locks the marketing/methodology numbers in `lib/site-stats.ts` to the
 * actual baked data. If a future pipeline run changes the country count,
 * indicator catalog size, or scoring version, this test fails — forcing
 * the constant to be updated in lock-step rather than drifting silently.
 *
 * Was filed because a 2026-04-24 QA sweep found 5 different country
 * counts across 6 surfaces of qgintelligence.com.
 */
import { describe, expect, it } from "vitest";
import countryRisks from "@/data/country-risks.json";
import indexes from "@/data/indexes.json";
import catalog from "@/data/indicator-catalog.json";
import methodologyStats from "@/data/methodology-stats.json";
import {
  CANONICAL_SCOPE_SENTENCE,
  SCORING_VERSION,
  TOTAL_COUNTRIES,
  TOTAL_INDICATORS,
  TOTAL_INDICATOR_CATALOG,
  TOTAL_INDICATOR_PROVIDERS,
  UN_STATES,
  getScoredThisCycle,
} from "@/lib/site-stats";

const CATALOG_ROWS = (
  catalog as { indicators: { code: string; name: string; provider: string }[] }
).indicators;

describe("site-stats", () => {
  it("UN_STATES is the standard 197 (constant scope descriptor)", () => {
    expect(UN_STATES).toBe(197);
  });

  it("TOTAL_COUNTRIES is at least the cycle-scored count", () => {
    // Pipeline scope (TOTAL_COUNTRIES) is a superset of currently-scored
    // countries — should always be >= the scored count for the active
    // cycle. If the scored count exceeds 214 something is very wrong.
    const scored = Object.keys(countryRisks.countries).length;
    expect(TOTAL_COUNTRIES).toBeGreaterThanOrEqual(scored);
    expect(scored).toBeLessThan(300); // sanity ceiling
  });

  it("SCORING_VERSION matches the live country-risks payload", () => {
    expect(SCORING_VERSION).toBe(countryRisks.version);
  });

  it("indicator catalog count is plausibly aligned with indexes.json", () => {
    // indexes.json is the scoring-side numeric-id catalog (259 curated entries,
    // a superset that includes draft/mock ids). TOTAL_INDICATOR_CATALOG (250)
    // is the active display panel — 109 originally ingested + 136 activated from
    // the 250-run bench + 5 vetted top-ups, across 8 providers. We assert the
    // public claim is <=
    // the indexes.json size so a future shrink can't silently leave the constant
    // overstating it, and that the scored/panel count never exceeds the catalog.
    expect(TOTAL_INDICATOR_CATALOG).toBeLessThanOrEqual(indexes.length);
    expect(TOTAL_INDICATORS).toBeLessThanOrEqual(TOTAL_INDICATOR_CATALOG);
  });

  it("indicator-catalog.json is internally consistent (no dup codes/names)", () => {
    // Locks the display catalog so a future bake can't reintroduce the
    // duplicate-indicator drift the 250-run activation nearly shipped
    // (FB.BNK.NPLS.ZS ↔ FB.AST.NPER.ZS). Every published surface counts this
    // file, so its size IS the headline.
    expect(CATALOG_ROWS.length).toBe(TOTAL_INDICATOR_CATALOG);
    expect(CATALOG_ROWS.length).toBe(methodologyStats.indicator_count);

    const codes = CATALOG_ROWS.map((r) => r.code);
    expect(new Set(codes).size).toBe(codes.length); // no duplicate codes

    // No duplicate *names* either — the near-dup class that slipped past
    // exact-code dedup (same real indicator under a different code).
    const names = CATALOG_ROWS.map((r) => r.name.trim().toLowerCase());
    expect(new Set(names).size).toBe(names.length);

    // No blank names (they render as empty rows in the taxonomy/table).
    expect(CATALOG_ROWS.every((r) => r.name.trim().length > 0)).toBe(true);
  });

  it("catalog provider tally equals the published breakdown", () => {
    const tally: Record<string, number> = {};
    for (const r of CATALOG_ROWS) tally[r.provider] = (tally[r.provider] || 0) + 1;
    expect(tally).toEqual(methodologyStats.indicator_breakdown);

    // Provider-count constant is locked to both the breakdown and the catalog,
    // so the "N providers" copy can't drift from the data.
    const nProviders = Object.keys(methodologyStats.indicator_breakdown).length;
    expect(TOTAL_INDICATOR_PROVIDERS).toBe(nProviders);
    expect(new Set(CATALOG_ROWS.map((r) => r.provider)).size).toBe(nProviders);
  });

  it("CANONICAL_SCOPE_SENTENCE references the canonical numbers", () => {
    expect(CANONICAL_SCOPE_SENTENCE).toContain(String(TOTAL_COUNTRIES));
    expect(CANONICAL_SCOPE_SENTENCE).toContain(String(TOTAL_INDICATORS));
  });

  it("getScoredThisCycle reads from country-risks at runtime", () => {
    // The dynamic helper is what dashboard headers should call so we don't
    // hardcode the cycle-specific number anywhere in the surface code.
    const n = getScoredThisCycle(
      countryRisks as unknown as Parameters<typeof getScoredThisCycle>[0]
    );
    expect(n).toBeGreaterThan(0);
    expect(n).toBe(
      Object.values(countryRisks.countries).filter((c) => c.overall_risk_tier).length
    );
  });
});
