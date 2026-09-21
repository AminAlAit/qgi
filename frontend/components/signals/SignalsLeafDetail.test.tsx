import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SignalsLeafDetail } from "./SignalsLeafDetail";
import type { MlRecipeEntry } from "@/lib/recipes-ml";
import { toBuyerView } from "@/lib/buyer-view";

/**
 * Regression test for #779 — "See full recipe → /precedents" CTA on the
 * V3 signal-leaf page constructed `/precedents/section-4-{recipe}` (the
 * paper-anchor fragment) instead of `/precedents/{recipe_id}` (the
 * actual route slug), 404ing for all four LOCKed recipes.
 *
 * Confirmed in persona-test Round 4 2026-05-17 by 3 independent personas
 * (Karl Henriksen, Mei-Lin Tsai, Helena Castro).
 */

function makeRawRecipe(): MlRecipeEntry {
  return {
    recipe_id: "civil_war_and_insurgency",
    display_name: "Civil war and insurgency",
    tier: "STRONG",
    architecture: "D2",
    loco_auc: 0.7686,
    n_pos_loco: 7,
    assignment_confidence: "MODERATE",
    in_sample_f1_ece: 0.0061,
    in_sample_f2_auc: 0.884,
    in_sample_f2_ci_lower: 0.794,
    in_sample_f2_ci_upper: 0.942,
    ece_overall: 0.0061,
    ece_high_cohort: 0.0068,
    ece_mid_cohort: 0.0118,
    ece_low_cohort: 0.0023,
    zero_positive_cohort_flag: null,
    anchor_ahi_value: 0.1052,
    anchor_ahi_status: "measured",
    anchor_ahi_n_evaluable: null,
    anchor_ahi_reason: null,
    advisory_only_flag: false,
    f_rule_anomaly_flag: false,
    top_1_training_country: "syria",
    top_1_training_country_share: 0.222,
    concentration_alert_level: "caution",
    interpretation_hint: "risk_elevation",
    mechanism_narrative: "Active-conflict onset signature.",
    mechanism_narrative_excerpt: "Active-conflict onset signature.",
    buyer_disclosure_recommendation: "test",
    open_followups: [],
    paper_section_anchor: "section-4-civil_war_and_insurgency",
    top_k_indicators: [],
    model_version: "v1.0",
  };
}

describe("SignalsLeafDetail — #779 'See full recipe' CTA", () => {
  const baseProps = {
    countrySlug: "turkey",
    countryName: "Turkiye",
    alpha2: "TR",
    categorySlug: "civil_war_and_insurgency",
    displayName: "Civil war and insurgency",
    tier: "HIGH" as const,
    l1: null,
    statPanel: {
      max_salience: 3.21,
      by_window: [{ window: "M", salience: 3.21 }],
    },
    mlPanel: {
      recipe: toBuyerView(makeRawRecipe()),
      is_top_4: true,
    },
    generatedDate: "2026-05-17",
    curated: false,
  };

  it("'See full recipe' CTA points at /precedents/{recipe_id}, NOT /precedents/section-4-{recipe} (regression #779)", () => {
    render(<SignalsLeafDetail {...baseProps} />);
    const cta = screen.getByText(/See full recipe/);
    const href = cta.closest("a")?.getAttribute("href");
    expect(href).toBe("/precedents/civil_war_and_insurgency");
    expect(href).not.toMatch(/section-4-/);
  });
});
