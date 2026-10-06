/**
 * "5 countries to watch this week" — A3 Family 2 brief curated band.
 *
 * Brief: docs/specs/internal/ops/cycle-resurfacing/merger-brief-2026-05-13.md
 *   §Family 2 / "5 countries to watch" curated band
 *
 * Pinned above the 156-row main table as 5 sticky rows with Sipho's
 * `[Editor's pick · week of {date}]` label.
 *
 * #716 (2026-05-16) — TIER CONSISTENCY FIX.
 *   Persona test 2026-05-15 surfaced a credibility-dealbreaker contradiction:
 *   /countries panel showed Germany "INDICATIVE → MODERATE" while the
 *   /countries/germany detail page showed plain INDICATIVE. James (FT):
 *   "I cannot publish a number when the source contradicts itself."
 *
 *   Root cause: this MOCK array was hand-authored at PR #2 (2026-05) against
 *   a different bake (V1.8 or an earlier V1.9 RC); the V1.9.1 2026-04-30 bake
 *   produced a different tier landscape but the prose was never refreshed.
 *
 *   Audit vs canonical country-risks.json (2026-05-16):
 *     - Syria      → HIGH       ✓ matches canonical
 *     - Iran       → HIGH       ✓ matches canonical
 *     - Venezuela  → was HIGH;  canonical = INDICATIVE → FLIPPED
 *     - Germany    → was MOD;   canonical = INDICATIVE → FLIPPED
 *     - Georgia    → was MOD;   canonical = INDICATIVE → FLIPPED
 *
 *   Fix: flip the 3 stale current_tier values to match canonical; drop
 *   `previous_tier` from the type entirely (unverifiable — no tier-history
 *   field exists in the bake to source it from). Rewrite the `movement`
 *   strings to remove tier-jump claims that no longer hold. Editorial value
 *   of the band is preserved (the 5 countries are still curated by the
 *   editor as "worth watching this week"), but tier claims now match data.
 *
 *   Long-term (Option D per QA investigation): replace this hand-
 *   maintained array with a generator that emits `mockWatchCountries.generated.ts`
 *   from the bake + curator notes. CI-fail when committed file drifts.
 *   Filed as follow-up — out of scope for this fix.
 *
 * Each entry references a country slug that resolves against country-risks.json.
 */

export interface WatchCountry {
  /** ISO slug matching countrySlug(country.name) output. */
  slug: string;
  display_name: string;
  alpha_2: string;
  /** Current tier — MUST match country-risks.json `overall_risk_tier` for
   *  this country. Enforced by CI test (follow-up). */
  current_tier: "HIGH" | "MODERATE" | "INDICATIVE";
  /** 2-3 sentence editorial summary (Ingrid voice). MUST NOT make tier-
   *  history claims (no "moved from X to Y") — there's no tier-history
   *  field in the bake to source them from. Describe drivers + signals only. */
  movement: string;
  /** Driving category slugs — rendered as chips beside the entry. */
  driving_categories: string[];
  /** MOCK: ML coverage count out of 13 LOCKed recipes (PR #4.5 pattern;
   *  upgrades to real when ml-recipe-stack per-country AHI bake lands). */
  ml_coverage: number;
}

export const WATCH_COUNTRIES: ReadonlyArray<WatchCountry> = [
  {
    slug: "syria",
    display_name: "Syria",
    alpha_2: "SY",
    current_tier: "HIGH",
    movement:
      "Civil-conflict indicators show sustained displacement pressure across the corpus window; humanitarian crisis salience remains the dominant signal.",
    driving_categories: [
      "civil_war_and_insurgency",
      "humanitarian_crisis",
      "foreign_intervention",
    ],
    ml_coverage: 4,
  },
  {
    slug: "iran",
    display_name: "Iran",
    alpha_2: "IR",
    current_tier: "HIGH",
    movement:
      "Political repression signals dominate the country profile; mass-protest activity is in the watchlist's upper quartile across the current bake.",
    driving_categories: ["mass_protest", "political_repression", "fiscal_policy_change"],
    ml_coverage: 3,
  },
  {
    slug: "venezuela",
    display_name: "Venezuela",
    alpha_2: "VE",
    // #716: was HIGH; canonical is INDICATIVE.
    current_tier: "INDICATIVE",
    movement:
      "Humanitarian crisis and political repression categories remain the editorial focus; aggregate salience sits in the lower tier despite policy-controlled distribution dynamics.",
    driving_categories: [
      "humanitarian_crisis",
      "political_repression",
      "elections_and_voting",
    ],
    ml_coverage: 2,
  },
  {
    slug: "germany",
    display_name: "Germany",
    alpha_2: "DE",
    // #716: was MODERATE; canonical is INDICATIVE.
    current_tier: "INDICATIVE",
    movement:
      "Elections-and-voting and constitutional-change indicators are the editorial focus for OECD-context watchers; aggregate salience sits below the elevated band.",
    driving_categories: [
      "elections_and_voting",
      "constitutional_change",
      "government_formation",
    ],
    ml_coverage: 1,
  },
  {
    slug: "georgia",
    display_name: "Georgia",
    alpha_2: "GE",
    // #716: was MODERATE; canonical is INDICATIVE.
    current_tier: "INDICATIVE",
    movement:
      "Bilateral-treaty activity with the EU and lingering mass-protest signals from the disputed 2024 election cycle drive editorial interest; aggregate salience remains in the indicative band.",
    driving_categories: ["bilateral_treaty", "mass_protest", "elections_and_voting"],
    ml_coverage: 1,
  },
];
