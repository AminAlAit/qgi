/**
 * Unit tests for getCanonicalRecipeFromBaked() — the #624 replacement for
 * the partition-scanning Athena query that was firing per page load on
 * /signals/[country]/[slug].
 *
 * Pre-#624 behaviour: SELECT country_b_id, start_year_b, length FROM
 * qgi_data.recipes WHERE event_category='X' (no partition pushdown,
 * scanned all 154 country_a_id partitions, ~444 S3 GETs per execution).
 *
 * Post-#624 behaviour: synchronous lookup against canonical_* fields
 * pre-baked into recipes-aggregated.json by scripts/bake-recipes-aggregated.ts.
 *
 * #624 strict-review F1: this test imports the REAL production function
 * from `lib/signals-trajectory-canonical` (extracted from the server-only
 * `lib/signals-trajectory` module specifically so tests can import it
 * without pulling in AWS SDK). No inlined copy — no drift risk.
 */
import { describe, it, expect } from "vitest";
import {
  getCanonicalRecipeFromBaked,
  type BakedCanonicalFields,
} from "@/lib/signals-trajectory-canonical";

describe("getCanonicalRecipeFromBaked", () => {
  it("returns a canonical row when all fields are present", () => {
    const recipe: BakedCanonicalFields = {
      canonical_length: 10,
      canonical_country_b_id: "42",
      canonical_country_b_name: "Vietnam",
      canonical_start_year_b: 1990,
    };
    expect(getCanonicalRecipeFromBaked(recipe)).toEqual({
      country_b_id: "42",
      country_b_name: "Vietnam",
      start_year_b: 1990,
      length: 10,
    });
  });

  it("returns null when canonical_country_b_id is null (older baked JSON)", () => {
    const recipe: BakedCanonicalFields = {
      canonical_length: 10,
      canonical_country_b_id: null,
      canonical_country_b_name: null,
      canonical_start_year_b: null,
    };
    expect(getCanonicalRecipeFromBaked(recipe)).toBeNull();
  });

  it("returns null when canonical_country_b_id is missing entirely (pre-#624 JSON)", () => {
    const recipe: BakedCanonicalFields = {
      canonical_length: 10,
    };
    expect(getCanonicalRecipeFromBaked(recipe)).toBeNull();
  });

  it("returns null when canonical_start_year_b is null even with country id present", () => {
    const recipe: BakedCanonicalFields = {
      canonical_length: 10,
      canonical_country_b_id: "42",
      canonical_country_b_name: "Vietnam",
      canonical_start_year_b: null,
    };
    expect(getCanonicalRecipeFromBaked(recipe)).toBeNull();
  });

  it("falls back to countryById map when canonical_country_b_name is missing", () => {
    const recipe: BakedCanonicalFields = {
      canonical_length: 8,
      canonical_country_b_id: "100",
      canonical_country_b_name: null,
      canonical_start_year_b: 1985,
    };
    const countryById = new Map([["100", "Brazil"]]);
    const result = getCanonicalRecipeFromBaked(recipe, countryById);
    expect(result?.country_b_name).toBe("Brazil");
  });

  it("falls back to placeholder when name is missing AND not in countryById", () => {
    const recipe: BakedCanonicalFields = {
      canonical_length: 8,
      canonical_country_b_id: "999",
      canonical_country_b_name: null,
      canonical_start_year_b: 1985,
    };
    const result = getCanonicalRecipeFromBaked(recipe);
    expect(result?.country_b_name).toBe("Country 999");
  });

  it("does NOT fire any async/Athena call (signature is sync)", () => {
    const recipe: BakedCanonicalFields = {
      canonical_length: 5,
      canonical_country_b_id: "1",
      canonical_country_b_name: "X",
      canonical_start_year_b: 2000,
    };
    const result = getCanonicalRecipeFromBaked(recipe);
    // sync = no Promise wrapper
    expect(result).not.toBeInstanceOf(Promise);
  });

  it("preserves canonical_length verbatim (no parseInt/string conversion bugs)", () => {
    // Edge case noted by #624 strict-review F4: canonical_length must be > 0
    // (upstream invariant — zero would produce a malformed display window
    // downstream in loadTrajectoryPanelData). The function itself does not
    // validate this; it preserves the value verbatim. Test documents the
    // pass-through behaviour.
    const recipe: BakedCanonicalFields = {
      canonical_length: 0,
      canonical_country_b_id: "1",
      canonical_country_b_name: "X",
      canonical_start_year_b: 2000,
    };
    const result = getCanonicalRecipeFromBaked(recipe);
    expect(result?.length).toBe(0);
  });
});
