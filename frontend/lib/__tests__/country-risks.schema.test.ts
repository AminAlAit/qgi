/**
 * country-risks Zod schema tests (#440 Part B).
 *
 * Three things this verifies:
 *   1. The actual baked `data/country-risks.json` is schema-valid
 *      (catches a pipeline regen that drifts the shape).
 *   2. A mutation (rename a field, drop a required key) fails — proves
 *      the schema is actually enforcing things, not just .passthrough().
 *   3. Optional/nullable fields stay optional/nullable — protects
 *      against accidentally tightening the schema in a way that breaks
 *      historical data loads.
 */
import { describe, expect, it } from "vitest";
import countryRisks from "@/data/country-risks.json";
import { CountryRisksDataSchema } from "@/lib/country-risks.schema";

describe("CountryRisksDataSchema", () => {
  it("validates the baked data/country-risks.json", () => {
    const result = CountryRisksDataSchema.safeParse(countryRisks);
    if (!result.success) {
      // Surface the first 3 issues so a broken payload produces an
      // actionable message instead of "expected object got string".
      const issues = result.error.issues
        .slice(0, 3)
        .map((i) => `${i.path.join(".") || "<root>"}: ${i.message}`)
        .join("\n  ");
      throw new Error(`country-risks.json failed schema:\n  ${issues}`);
    }
    expect(result.success).toBe(true);
  });

  it("rejects a payload with a renamed field (mutation test)", () => {
    const mutated = JSON.parse(JSON.stringify(countryRisks));
    // Pretend the pipeline renamed `overall_risk_tier` → `risk_tier`.
    const firstCountryId = Object.keys(mutated.countries)[0];
    const c = mutated.countries[firstCountryId];
    delete c.overall_risk_tier;
    c.risk_tier = "HIGH";
    const result = CountryRisksDataSchema.safeParse(mutated);
    expect(result.success).toBe(false);
  });

  it("rejects a payload with a wrong tier enum value", () => {
    const mutated = JSON.parse(JSON.stringify(countryRisks));
    const firstCountryId = Object.keys(mutated.countries)[0];
    mutated.countries[firstCountryId].overall_risk_tier = "EXTREME"; // not in enum
    const result = CountryRisksDataSchema.safeParse(mutated);
    expect(result.success).toBe(false);
  });

  it("rejects a missing top-level required field", () => {
    const mutated = JSON.parse(JSON.stringify(countryRisks));
    delete mutated.version;
    const result = CountryRisksDataSchema.safeParse(mutated);
    expect(result.success).toBe(false);
  });

  it("accepts last_event_year being null (optional → nullable behaviour)", () => {
    const mutated = JSON.parse(JSON.stringify(countryRisks));
    const firstCountryId = Object.keys(mutated.countries)[0];
    const cats = mutated.countries[firstCountryId].tiers?.S?.top_categories;
    if (Array.isArray(cats) && cats[0]) {
      cats[0].last_event_year = null;
    }
    const result = CountryRisksDataSchema.safeParse(mutated);
    expect(result.success).toBe(true);
  });
});
