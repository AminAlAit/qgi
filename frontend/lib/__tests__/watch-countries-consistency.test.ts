/**
 * #716 (2026-05-16) — CI guard against editor's-pick band drifting from
 * the canonical country-risks.json bake.
 *
 * Persona test 2026-05-15 (James / FT) surfaced: /countries panel showed
 * Germany as "INDICATIVE → MODERATE" while /countries/germany detail
 * showed plain INDICATIVE. Root cause: the WATCH_COUNTRIES hand-authored
 * mock array drifted from canonical data when the V1.9.1 bake landed.
 * Fix: flip the 3 stale tiers; this test prevents the drift from
 * recurring on the next bake.
 *
 * Assertion: every `current_tier` in WATCH_COUNTRIES must match
 * `country-risks.json::countries[X].overall_risk_tier` for the same
 * country (resolved by slug).
 *
 * Until a generator script produces this file from the bake (QA
 * investigation Option D, deferred), curators MUST run this test after
 * each weekly editorial refresh.
 */
import { describe, it, expect } from "vitest";
import { WATCH_COUNTRIES } from "@/components/countries/mockWatchCountries";
import { countrySlug } from "@/lib/slug";
import countryRisksJson from "@/data/country-risks.json";

interface CountryRisksCountry {
  name: string;
  alpha_2: string;
  overall_risk_tier: "HIGH" | "MODERATE" | "INDICATIVE";
}

interface CountryRisks {
  countries: Record<string, CountryRisksCountry>;
}

const data = countryRisksJson as unknown as CountryRisks;

describe("WATCH_COUNTRIES — editorial band consistency with canonical bake (#716)", () => {
  it("every watch entry resolves to a country in country-risks.json", () => {
    const allSlugs = new Set(
      Object.values(data.countries)
        .map((c) => countrySlug(c.name))
        .filter((s): s is string => Boolean(s))
    );
    for (const watch of WATCH_COUNTRIES) {
      expect(
        allSlugs.has(watch.slug),
        `WATCH_COUNTRIES slug "${watch.slug}" does not resolve in country-risks.json. ` +
          `Either fix the slug or remove this entry.`
      ).toBe(true);
    }
  });

  it("every watch entry's current_tier matches canonical overall_risk_tier", () => {
    // Build a slug → canonical-tier index from the bake.
    const slugToTier = new Map<string, string>();
    for (const c of Object.values(data.countries)) {
      const slug = countrySlug(c.name);
      if (slug) slugToTier.set(slug, c.overall_risk_tier);
    }

    const drifts: string[] = [];
    for (const watch of WATCH_COUNTRIES) {
      const canonical = slugToTier.get(watch.slug);
      if (canonical !== watch.current_tier) {
        drifts.push(
          `  - ${watch.display_name} (${watch.slug}): WATCH_COUNTRIES says ` +
            `${watch.current_tier}, canonical says ${canonical}`
        );
      }
    }
    expect(
      drifts.length,
      `WATCH_COUNTRIES tier drift detected (#716 regression):\n${drifts.join("\n")}\n` +
        `Fix: update components/countries/mockWatchCountries.ts to match ` +
        `data/country-risks.json::countries[X].overall_risk_tier.`
    ).toBe(0);
  });

  it("watch entry alpha_2 matches canonical alpha_2", () => {
    const slugToAlpha = new Map<string, string>();
    for (const c of Object.values(data.countries)) {
      const slug = countrySlug(c.name);
      if (slug) slugToAlpha.set(slug, c.alpha_2);
    }
    for (const watch of WATCH_COUNTRIES) {
      const canonical = slugToAlpha.get(watch.slug);
      expect(
        canonical,
        `WATCH_COUNTRIES alpha_2 for ${watch.display_name}: ${watch.alpha_2} should match canonical ${canonical}`
      ).toBe(watch.alpha_2);
    }
  });

  it("movement prose does not make tier-history claims", () => {
    // #716 (2026-05-16) — tier-history claims ("moved from X to Y",
    // "X → Y", "shifted up to") were unverifiable. The bake does NOT
    // carry tier history, so the prose can't fact-check them. Banned
    // until a tier-history field ships.
    const tierHistoryPhrases = [
      /\bmoved from \w+ to \w+/i,
      /(HIGH|MODERATE|INDICATIVE)\s*→\s*(HIGH|MODERATE|INDICATIVE)/,
      /\bshifted (?:up|down) to\b/i,
      /\bjumped from\b/i,
      /\bescalated from\b/i,
    ];
    for (const watch of WATCH_COUNTRIES) {
      for (const pat of tierHistoryPhrases) {
        expect(
          pat.test(watch.movement),
          `WATCH_COUNTRIES[${watch.display_name}].movement contains a ` +
            `tier-history claim matching ${pat.source}: "${watch.movement}". ` +
            `Rewrite to describe current drivers/signals only.`
        ).toBe(false);
      }
    }
  });
});
