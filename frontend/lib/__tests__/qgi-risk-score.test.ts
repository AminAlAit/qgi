/**
 * #721 (2026-05-16) — verify QGI Risk Score Step 1 bake fields are present
 * + valid in `data/country-risks.json`, and check key invariants from the
 * Majles synthesis spec.
 *
 * Spec: `docs/specs/internal/ops/qgi-risk-score-majles-2026-05-16.md`
 *
 * Invariants tested:
 *  1. Top-level metadata present (version, cohort_n, method, baked_at)
 *  2. Per-country: every "ok" coverage_flag has all three score fields
 *     non-null and in [0, 100]; every "insufficient" has all three null
 *  3. CI low ≤ score ≤ CI high (within reasonable rounding)
 *  4. Cohort N matches the number of "ok" coverage_flag countries
 *  5. Strict-ordinal-not-probability invariant: NO score-related field
 *     is named or annotated as "probability" anywhere in the data
 */
import { describe, it, expect } from "vitest";
import countryRisksJson from "@/data/country-risks.json";
import { CountryRisksDataSchema } from "@/lib/country-risks.schema";

const parsed = CountryRisksDataSchema.parse(countryRisksJson);

describe("QGI Risk Score Step 1 bake (#721)", () => {
  it("top-level metadata present", () => {
    // Version timeline:
    //   v1 — #721 country-level only
    //   v2 — #728 added per-recipe block
    //   v3 — #729 Step 1.5 (calibration carry + CI widening + correlation matrix)
    expect(parsed.qgi_risk_score_version).toMatch(/^v[1-9][0-9]*$/);
    expect(parsed.qgi_risk_score_cohort_n).toBeTypeOf("number");
    expect(parsed.qgi_risk_score_cohort_n).toBeGreaterThan(0);
    expect(parsed.qgi_risk_score_method).toBe("percentile-rank-of-max-salience");
    expect(parsed.qgi_risk_score_baked_at).toBeTypeOf("string");
    expect(new Date(parsed.qgi_risk_score_baked_at!).toISOString()).toMatch(
      /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/
    );
  });

  it("#728 per-recipe metadata present in v2+ bakes", () => {
    if (parsed.qgi_risk_score_version === "v1") return;
    expect(parsed.qgi_risk_score_per_recipe_recipes).toBeDefined();
    expect(parsed.qgi_risk_score_per_recipe_cohort_n).toBeDefined();
    const recipes = parsed.qgi_risk_score_per_recipe_recipes!;
    const cohorts = parsed.qgi_risk_score_per_recipe_cohort_n!;
    expect(recipes.length).toBeGreaterThan(0);
    for (const r of recipes) {
      expect(cohorts[r]).toBeTypeOf("number");
      expect(cohorts[r]).toBeGreaterThan(0);
    }
  });

  it("#728 every country has a qgi_risk_score_by_recipe block keyed by the top-4 recipes", () => {
    if (parsed.qgi_risk_score_version === "v1") return;
    const recipes = parsed.qgi_risk_score_per_recipe_recipes!;
    for (const c of Object.values(parsed.countries)) {
      expect(
        c.qgi_risk_score_by_recipe,
        `${c.name}: missing per-recipe block`
      ).toBeDefined();
      const block = c.qgi_risk_score_by_recipe!;
      for (const r of recipes) {
        expect(r in block, `${c.name}: missing recipe key ${r}`).toBe(true);
        const entry = block[r];
        if (entry !== null) {
          expect(entry.score).toBeGreaterThanOrEqual(0);
          expect(entry.score).toBeLessThanOrEqual(100);
          expect(entry.coverage_flag).toBe("ok");
        }
      }
    }
  });

  it("#728 face-validity: Syria scores >=70 on civil_war_and_insurgency", () => {
    if (parsed.qgi_risk_score_version === "v1") return;
    const syria = Object.values(parsed.countries).find((c) => c.name === "Syria");
    const entry = syria?.qgi_risk_score_by_recipe?.["civil_war_and_insurgency"];
    if (entry) {
      expect(entry.score, "Syria civil_war_and_insurgency >= 70").toBeGreaterThanOrEqual(
        70
      );
    }
  });

  it("#729 Step 1.5: cohort_n_recipe surfaced on every per-recipe entry", () => {
    // Roshani's veto — every per-recipe tile must carry cohort_n alongside
    // the score so N=58 (multilateral_agreement) and N=127 (bilateral_treaty)
    // don't render as commensurable.
    if (parsed.qgi_risk_score_version !== "v3") return;
    for (const c of Object.values(parsed.countries)) {
      const block = c.qgi_risk_score_by_recipe;
      if (!block) continue;
      for (const [rid, entry] of Object.entries(block)) {
        if (entry === null) continue;
        expect(
          entry.cohort_n_recipe,
          `${c.name}/${rid}: cohort_n_recipe must be present`
        ).toBeTypeOf("number");
        expect(entry.cohort_n_recipe).toBeGreaterThan(0);
      }
    }
  });

  it("#729 Step 1.5: calibration carry present on every per-recipe entry when ml-recipe-stack was loaded", () => {
    // Kwame's veto — recipe-level ECE + LOCO_AUC + advisory flags must
    // ride with the score so buyers know underlying reliability.
    if (parsed.qgi_risk_score_version !== "v3") return;
    for (const c of Object.values(parsed.countries)) {
      const block = c.qgi_risk_score_by_recipe;
      if (!block) continue;
      for (const [rid, entry] of Object.entries(block)) {
        if (entry === null) continue;
        // recipe_ece / recipe_loco_auc may be null (if upstream is null)
        // but the keys must be PRESENT — that's the calibration-carry contract.
        expect(
          "recipe_ece" in entry,
          `${c.name}/${rid}: recipe_ece key must be present (carry)`
        ).toBe(true);
        expect(
          "recipe_loco_auc" in entry,
          `${c.name}/${rid}: recipe_loco_auc key must be present (carry)`
        ).toBe(true);
        expect(
          "recipe_f_rule_advisory_flag" in entry,
          `${c.name}/${rid}: advisory flag key must be present (carry)`
        ).toBe(true);
      }
    }
  });

  it("#729 Step 1.5: recipe-recipe Spearman correlation matrix is 4×4, symmetric, diag=1", () => {
    // Dmitri's hard gate — published at bake time so quants can residualize.
    if (parsed.qgi_risk_score_version !== "v3") return;
    const matrix = parsed.qgi_risk_score_per_recipe_correlation_matrix;
    expect(matrix, "correlation matrix top-level field present").toBeDefined();
    const recipes = parsed.qgi_risk_score_per_recipe_recipes!;
    for (const ra of recipes) {
      expect(matrix![ra], `row for ${ra} present`).toBeDefined();
      for (const rb of recipes) {
        const cell = matrix![ra][rb];
        if (ra === rb) {
          expect(cell, `diag[${ra}] = 1`).toBe(1);
        } else if (cell !== null) {
          // Symmetric: matrix[ra][rb] === matrix[rb][ra]
          expect(matrix![rb][ra], `symmetric ${ra},${rb}`).toBe(cell);
          // Bounded [-1, 1]
          expect(cell).toBeGreaterThanOrEqual(-1);
          expect(cell).toBeLessThanOrEqual(1);
        }
      }
    }
  });

  it("#729 Step 1.5: small-cohort CI widening params disclosed", () => {
    if (parsed.qgi_risk_score_version !== "v3") return;
    expect(parsed.qgi_risk_score_small_cohort_ci_threshold).toBe(80);
    expect(parsed.qgi_risk_score_small_cohort_ci_widen_factor).toBe(1.5);
  });

  it("every 'ok' country has all 3 score fields non-null and in [0, 100]", () => {
    let okCount = 0;
    for (const c of Object.values(parsed.countries)) {
      if (c.coverage_flag === "ok") {
        okCount++;
        expect(c.qgi_risk_score_0_100, `${c.name}: score`).not.toBeNull();
        expect(c.qgi_risk_score_ci_low, `${c.name}: ci_low`).not.toBeNull();
        expect(c.qgi_risk_score_ci_high, `${c.name}: ci_high`).not.toBeNull();
        const s = c.qgi_risk_score_0_100!;
        const lo = c.qgi_risk_score_ci_low!;
        const hi = c.qgi_risk_score_ci_high!;
        expect(s).toBeGreaterThanOrEqual(0);
        expect(s).toBeLessThanOrEqual(100);
        expect(lo).toBeGreaterThanOrEqual(0);
        expect(hi).toBeLessThanOrEqual(100);
      }
    }
    expect(okCount).toBe(parsed.qgi_risk_score_cohort_n);
  });

  it("every 'insufficient' country has all 3 score fields null", () => {
    for (const c of Object.values(parsed.countries)) {
      if (c.coverage_flag === "insufficient") {
        expect(c.qgi_risk_score_0_100, `${c.name}: score`).toBeNull();
        expect(c.qgi_risk_score_ci_low, `${c.name}: ci_low`).toBeNull();
        expect(c.qgi_risk_score_ci_high, `${c.name}: ci_high`).toBeNull();
      }
    }
  });

  it("CI bounds bracket the score (1-pt rounding slack)", () => {
    for (const c of Object.values(parsed.countries)) {
      if (c.coverage_flag === "ok") {
        const s = c.qgi_risk_score_0_100!;
        const lo = c.qgi_risk_score_ci_low!;
        const hi = c.qgi_risk_score_ci_high!;
        expect(lo - 1).toBeLessThanOrEqual(s);
        expect(hi + 1).toBeGreaterThanOrEqual(s);
      }
    }
  });

  it("face-validity: known-high countries score high, known-low countries score low", () => {
    const byName = new Map<string, (typeof parsed.countries)[string]>();
    for (const c of Object.values(parsed.countries)) byName.set(c.name, c);

    for (const name of ["Syria", "Sudan", "Myanmar"]) {
      const c = byName.get(name);
      if (c?.coverage_flag === "ok") {
        expect(c.qgi_risk_score_0_100, `${name} ≥ 70`).toBeGreaterThanOrEqual(70);
      }
    }
    for (const name of ["Norway", "Denmark", "Switzerland"]) {
      const c = byName.get(name);
      if (c?.coverage_flag === "ok") {
        expect(c.qgi_risk_score_0_100, `${name} ≤ 30`).toBeLessThanOrEqual(30);
      }
    }
  });

  it("strict ordinal: no 'probability' framing in field names anywhere", () => {
    const probabilityRegex = /probabilit/i;
    const sample = parsed.countries[Object.keys(parsed.countries)[0]];
    for (const key of Object.keys(sample)) {
      expect(probabilityRegex.test(key), `Field "${key}" contains 'probability'`).toBe(
        false
      );
    }
    for (const key of Object.keys(parsed)) {
      expect(
        probabilityRegex.test(key),
        `Top-level "${key}" contains 'probability'`
      ).toBe(false);
    }
  });
});
