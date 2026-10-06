import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CountriesMergedListClient } from "./CountriesMergedListClient";
import type { CountryRisk, RiskTier } from "@/lib/country-risks.schema";

/**
 * Regression test for #780 — typing "Turkey" in the /countries search
 * field returned zero results because the canonical bake spelling is
 * "Turkiye", and the predicate did a raw substring check. Persona-test
 * Round 4 2026-05-17 (Karl Henriksen / Eurasia Group) hit this — he
 * concluded the country was missing from the index when in fact only
 * the search filter was missing the alias.
 *
 * Same defect class also covers USA → United States, Burma → Myanmar,
 * UK → United Kingdom, DRC → The Democratic Republic of the Congo, etc.
 * The COMMON_NAME_ALIASES map (already the single source of truth for
 * route-level slug resolution per #715/#759) is now consulted by the
 * search predicate.
 */

function makeCountry(name: string, alpha2: string): { id: string } & CountryRisk {
  return {
    id: alpha2,
    name,
    alpha_2: alpha2,
    curated: true,
    overall_risk_tier: "MODERATE" as RiskTier,
    tiers: {},
  };
}

const tierCounts: Record<RiskTier, number> = { HIGH: 0, MODERATE: 0, INDICATIVE: 0 };

describe("CountriesMergedListClient — #780 search-alias", () => {
  it("typing 'Turkey' surfaces 'Turkiye' (alias-aware search)", async () => {
    const user = userEvent.setup();
    render(
      <CountriesMergedListClient
        countries={[makeCountry("Turkiye", "TR"), makeCountry("Mexico", "MX")]}
        tierCounts={tierCounts}
      />
    );

    const searchBox = screen.getByPlaceholderText(/Search/i);
    await user.type(searchBox, "Turkey");

    // The row text contains the canonical name "Turkiye". A real text-match
    // is the proof the alias mapping kicked in.
    expect(screen.getByRole("link", { name: /Turkiye/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Mexico/ })).not.toBeInTheDocument();
  });

  it("typing 'USA' surfaces 'United States'", async () => {
    const user = userEvent.setup();
    render(
      <CountriesMergedListClient
        countries={[makeCountry("United States", "US"), makeCountry("Mexico", "MX")]}
        tierCounts={tierCounts}
      />
    );

    const searchBox = screen.getByPlaceholderText(/Search/i);
    await user.type(searchBox, "USA");

    expect(screen.getByRole("link", { name: /United States/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Mexico/ })).not.toBeInTheDocument();
  });

  it("typing 'Burma' surfaces 'Myanmar'", async () => {
    const user = userEvent.setup();
    render(
      <CountriesMergedListClient
        countries={[makeCountry("Myanmar", "MM"), makeCountry("Mexico", "MX")]}
        tierCounts={tierCounts}
      />
    );

    const searchBox = screen.getByPlaceholderText(/Search/i);
    await user.type(searchBox, "Burma");

    expect(screen.getByRole("link", { name: /Myanmar/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Mexico/ })).not.toBeInTheDocument();
  });

  it("typing 'East Timor' surfaces 'Timor-Leste' (hyphenated canonical, QA-v4 review catch on PR #102)", async () => {
    const user = userEvent.setup();
    render(
      <CountriesMergedListClient
        countries={[makeCountry("Timor-Leste", "TL"), makeCountry("Mexico", "MX")]}
        tierCounts={tierCounts}
      />
    );

    const searchBox = screen.getByPlaceholderText(/Search/i);
    await user.type(searchBox, "East Timor");

    expect(screen.getByRole("link", { name: /Timor-Leste/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Mexico/ })).not.toBeInTheDocument();
  });

  it("typing 'brasil' (Portuguese endonym) surfaces 'Brazil' (#787 R5 Helena)", async () => {
    const user = userEvent.setup();
    render(
      <CountriesMergedListClient
        countries={[makeCountry("Brazil", "BR"), makeCountry("Mexico", "MX")]}
        tierCounts={tierCounts}
      />
    );

    const searchBox = screen.getByPlaceholderText(/Search/i);
    await user.type(searchBox, "brasil");

    expect(screen.getByRole("link", { name: /Brazil/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Mexico/ })).not.toBeInTheDocument();
  });

  it("typing 'brasile' (Italian endonym) surfaces 'Brazil' (#787 R5 Roberto)", async () => {
    const user = userEvent.setup();
    render(
      <CountriesMergedListClient
        countries={[makeCountry("Brazil", "BR"), makeCountry("Mexico", "MX")]}
        tierCounts={tierCounts}
      />
    );

    const searchBox = screen.getByPlaceholderText(/Search/i);
    await user.type(searchBox, "brasile");

    expect(screen.getByRole("link", { name: /Brazil/ })).toBeInTheDocument();
  });

  it("typing 'Brésil' (French endonym with diacritic) surfaces 'Brazil' (#787 NFKD normalization)", async () => {
    const user = userEvent.setup();
    render(
      <CountriesMergedListClient
        countries={[makeCountry("Brazil", "BR"), makeCountry("Mexico", "MX")]}
        tierCounts={tierCounts}
      />
    );

    const searchBox = screen.getByPlaceholderText(/Search/i);
    await user.type(searchBox, "Brésil");

    expect(screen.getByRole("link", { name: /Brazil/ })).toBeInTheDocument();
  });

  it("typing 'Italia' (IT endonym) surfaces 'Italy' (#787)", async () => {
    // Avoids the watchlist-overlap caveat: Germany / Syria / Iran / Venezuela
    // / Georgia all render in the Editor's Pick section regardless of
    // search (#789 unrelated bug). Italy is NOT in mockWatchCountries
    // so the test asserts a single link cleanly.
    const user = userEvent.setup();
    render(
      <CountriesMergedListClient
        countries={[makeCountry("Italy", "IT"), makeCountry("Mexico", "MX")]}
        tierCounts={tierCounts}
      />
    );

    const searchBox = screen.getByPlaceholderText(/Search/i);
    await user.type(searchBox, "Italia");

    expect(screen.getByRole("link", { name: /Italy/ })).toBeInTheDocument();
  });

  it("typing diacritic-form 'Türkiye' matches without accent (NFKD strip on the search side)", async () => {
    const user = userEvent.setup();
    render(
      <CountriesMergedListClient
        countries={[makeCountry("Turkiye", "TR"), makeCountry("Mexico", "MX")]}
        tierCounts={tierCounts}
      />
    );

    const searchBox = screen.getByPlaceholderText(/Search/i);
    await user.type(searchBox, "Türkiye");

    expect(screen.getByRole("link", { name: /Turkiye/ })).toBeInTheDocument();
  });

  it("topCategoryLabel finds globally-leading category even if it sits at position 4+ in a tier window (#Rank-14 Aisha R4)", async () => {
    const { topCategoryLabel } = await import("./CountriesMergedListClient");
    // Construct a country where the globally-leading salience signal is
    // at position 4 in the S tier window — would have been invisible to
    // the old `.slice(0, 3)` per-tier logic.
    const country: CountryRisk = {
      name: "Morocco",
      alpha_2: "MA",
      curated: true,
      overall_risk_tier: "MODERATE" as RiskTier,
      tiers: {
        S: {
          top_categories: [
            // The first 3 entries are the would-have-been "top 3"
            {
              category: "civil_war_and_insurgency",
              salience_score: 1.2,
              z_score: 1.2,
              severity_tier: 2,
              rrf_rank: 1,
              rrf_score: 1,
              recipe_count: 1,
              last_event_year: null,
            },
            {
              category: "bilateral_treaty",
              salience_score: 1.0,
              z_score: 1.0,
              severity_tier: 2,
              rrf_rank: 2,
              rrf_score: 1,
              recipe_count: 1,
              last_event_year: null,
            },
            {
              category: "elections_and_voting",
              salience_score: 0.9,
              z_score: 0.9,
              severity_tier: 2,
              rrf_rank: 3,
              rrf_score: 1,
              recipe_count: 1,
              last_event_year: null,
            },
            // Position 4 — globally highest salience. Old code missed this.
            {
              category: "political_repression",
              salience_score: 2.5,
              z_score: 2.5,
              severity_tier: 3,
              rrf_rank: 4,
              rrf_score: 1,
              recipe_count: 1,
              last_event_year: null,
            },
          ],
        },
      },
    };
    expect(topCategoryLabel(country)).toBe("Political Repression");
  });

  it("Editor's Pick section is hidden on active search (#789 Aisha R5)", async () => {
    const user = userEvent.setup();
    render(
      <CountriesMergedListClient
        countries={[makeCountry("Mexico", "MX"), makeCountry("Turkiye", "TR")]}
        tierCounts={tierCounts}
      />
    );

    // Empty search: Editor's Pick visible (aria-label "5 countries to watch this week").
    expect(screen.getByLabelText(/5 countries to watch this week/i)).toBeInTheDocument();

    // Active search: Editor's Pick gone.
    const searchBox = screen.getByPlaceholderText(/Search/i);
    await user.type(searchBox, "Mex");
    expect(
      screen.queryByLabelText(/5 countries to watch this week/i)
    ).not.toBeInTheDocument();
  });

  it("a non-alias query continues to match by name substring", async () => {
    const user = userEvent.setup();
    render(
      <CountriesMergedListClient
        countries={[makeCountry("Mexico", "MX"), makeCountry("Turkiye", "TR")]}
        tierCounts={tierCounts}
      />
    );

    const searchBox = screen.getByPlaceholderText(/Search/i);
    await user.type(searchBox, "Mex");

    expect(screen.getByRole("link", { name: /Mexico/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Turkiye/ })).not.toBeInTheDocument();
  });
});
