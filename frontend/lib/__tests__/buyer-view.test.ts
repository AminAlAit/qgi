import { describe, it, expect } from "vitest";
import { toBuyerView, toBuyerViewList, buildSlugMap } from "@/lib/buyer-view";
import type { MlRecipeEntry, MlRecipeStack } from "@/lib/recipes-ml";
import stackData from "@/data/ml-recipe-stack.json";

const stack = stackData as MlRecipeStack;

// ===========================================================================
// CI GATE: assert toBuyerView output is leak-free across all real recipes
// ===========================================================================
// This is the regression gate for the buyer-view boundary. If the bake adds
// a new field or new jargon term, the rewriter doesn't cover it, this test
// fails — the failing PR must either extend `lib/jargon-replace.ts` or
// shape the new field in `toBuyerView()`.
//
// Detector set mirrors `scripts/polish_leak_scan.py` JARGON_TERMS. Keep in
// sync when either side adds a term.
// ===========================================================================

/**
 * Patterns that are LEAKS when found in buyer-rendered prose. Mirrors the
 * scanner's JARGON_TERMS but adapted for in-text regex matching.
 */
const LEAK_PATTERNS: Array<{ pattern: RegExp; name: string }> = [
  // Acronyms
  { pattern: /\bLOCO\b/, name: "LOCO" },
  { pattern: /\bAUC\b/, name: "AUC" },
  { pattern: /\bECE\b/, name: "ECE" },
  { pattern: /\bAHI\b/, name: "AHI" },
  { pattern: /\bRCI\b/, name: "RCI" },
  { pattern: /\bPPS\b/, name: "PPS" },
  { pattern: /\bSCDI\b/, name: "SCDI" },
  { pattern: /\bRRF\b/, name: "RRF" },
  // Architecture codes
  { pattern: /\bD2\s+(?:architecture|head|multi-task)/, name: "D2-architecture" },
  { pattern: /\bD5\s+(?:architecture|head|trajectory)/, name: "D5-architecture" },
  { pattern: /\bhybrid\s+D2\/D5\b/, name: "hybrid D2/D5" },
  // Internal status / process
  { pattern: /\bLOCKed\b/, name: "LOCKed" },
  { pattern: /\bFALSIFIED\b/, name: "FALSIFIED" },
  // Citations
  { pattern: /\bF-H-\d+\b/, name: "F-H-N citation" },
  { pattern: /\bKI-\d+\b/, name: "KI-N citation" },
  { pattern: /\bMajles\b/, name: "Majles" },
  { pattern: /\b(?:Asas|Sard|Ihsa|Bina|Tasweeq|Tijara)\b/, name: "Majles persona" },
  // Pricing-gate terms
  { pattern: /\bADVISORY-ONLY\b/, name: "ADVISORY-ONLY" },
  // Methodology vocabulary
  { pattern: /\bn_pos\b/, name: "n_pos" },
  { pattern: /\bcohort_ece\b/, name: "cohort_ece" },
  { pattern: /\bpre-reg\b/, name: "pre-reg" },
  { pattern: /\bLakatosian\b/, name: "Lakatosian" },
  { pattern: /\bdispatch_sha\b/, name: "dispatch_sha" },
];

function findLeaks(text: string): string[] {
  const hits: string[] = [];
  for (const { pattern, name } of LEAK_PATTERNS) {
    if (pattern.test(text)) hits.push(name);
  }
  return hits;
}

function assertLeakFree(text: string, fieldName: string, recipeName: string): void {
  const hits = findLeaks(text);
  if (hits.length > 0) {
    throw new Error(
      `Leak in ${recipeName}.${fieldName}: ${hits.join(", ")}\nText: ${text.slice(0, 200)}...`
    );
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("toBuyerView — CI gate against real bake output", () => {
  const slugMap = buildSlugMap(stack.recipes);

  for (const raw of stack.recipes) {
    describe(`recipe: ${raw.recipe_id}`, () => {
      const buyer = toBuyerView(raw, slugMap);

      it("mechanism_narrative has no jargon leaks", () => {
        expect(() =>
          assertLeakFree(
            buyer.mechanism_narrative,
            "mechanism_narrative",
            buyer.display_name
          )
        ).not.toThrow();
      });

      it("mechanism_narrative_excerpt has no jargon leaks", () => {
        expect(() =>
          assertLeakFree(
            buyer.mechanism_narrative_excerpt,
            "mechanism_narrative_excerpt",
            buyer.display_name
          )
        ).not.toThrow();
      });

      it("buyer_disclosure_recommendation has no jargon leaks", () => {
        expect(() =>
          assertLeakFree(
            buyer.buyer_disclosure_recommendation,
            "buyer_disclosure_recommendation",
            buyer.display_name
          )
        ).not.toThrow();
      });

      it("anchor_ahi_reason has no jargon leaks (if present)", () => {
        if (buyer.anchor_ahi_reason !== null) {
          expect(() =>
            assertLeakFree(
              buyer.anchor_ahi_reason!,
              "anchor_ahi_reason",
              buyer.display_name
            )
          ).not.toThrow();
        }
      });

      it("zero_positive_cohort_flag has no jargon leaks (if present)", () => {
        if (buyer.zero_positive_cohort_flag !== null) {
          expect(() =>
            assertLeakFree(
              buyer.zero_positive_cohort_flag!,
              "zero_positive_cohort_flag",
              buyer.display_name
            )
          ).not.toThrow();
        }
      });

      it("open_followups items have no jargon leaks", () => {
        for (const followup of buyer.open_followups) {
          expect(() =>
            assertLeakFree(followup, "open_followups[]", buyer.display_name)
          ).not.toThrow();
        }
      });

      it("indicators have friendly labels, no raw codes in label", () => {
        for (const ind of buyer.indicators) {
          // The label must NOT contain the raw __diff/__lag suffix
          expect(ind.label).not.toMatch(/__diff|__lag|__zscore/);
          // The label must NOT be a bare V-Dem code (v2x...) or WB dotted code
          expect(ind.label).not.toMatch(/^v2[a-z]+(_[a-z0-9]+)+$/);
          expect(ind.label).not.toMatch(/^[A-Z]{2,3}\.[A-Z]{2,4}\./);
          // The raw_id IS preserved (for analyst hover)
          expect(ind.raw_id).toBe(raw.top_k_indicators[ind.rank - 1].indicator_id);
        }
      });

      it("indicator country_bias_caveat is buyer-friendly", () => {
        for (const ind of buyer.indicators) {
          if (ind.country_bias_caveat !== null) {
            expect(ind.country_bias_caveat).toBe("Possible country bias");
            // The phrase "fixed-effect" must NOT leak into buyer caveat
            expect(ind.country_bias_caveat).not.toMatch(/fixed-effect/);
          }
        }
      });

      it("architecture_label is plain English, not D2/D5", () => {
        expect(buyer.architecture_label).not.toMatch(/^D[25]$/);
        expect(buyer.architecture_label).toMatch(/model$/);
        expect(buyer.architecture_raw).toMatch(/^D[25]$/);
      });
    });
  }
});

// ---------------------------------------------------------------------------
// Unit tests for toBuyerView shape
// ---------------------------------------------------------------------------

describe("toBuyerView — shape", () => {
  it("preserves identifiers (recipe_id, display_name, paper_section_anchor)", () => {
    const raw = stack.recipes[0];
    const buyer = toBuyerView(raw);
    expect(buyer.recipe_id).toBe(raw.recipe_id);
    expect(buyer.display_name).toBe(raw.display_name);
    expect(buyer.paper_section_anchor).toBe(raw.paper_section_anchor);
  });

  it("preserves numeric metrics verbatim", () => {
    const raw = stack.recipes[0];
    const buyer = toBuyerView(raw);
    expect(buyer.loco_auc).toBe(raw.loco_auc);
    expect(buyer.n_pos_loco).toBe(raw.n_pos_loco);
    expect(buyer.in_sample_f2_auc).toBe(raw.in_sample_f2_auc);
  });

  it("reshapes top_k_indicators to indicators[]", () => {
    const raw = stack.recipes[0];
    const buyer = toBuyerView(raw);
    expect(buyer.indicators.length).toBe(raw.top_k_indicators.length);
    expect(buyer.indicators[0].rank).toBe(raw.top_k_indicators[0].rank);
    expect(buyer.indicators[0].importance).toBe(raw.top_k_indicators[0].mean_abs_shap);
  });

  it("rewrites recipe's own slug at sentence start of mechanism_narrative", () => {
    // Force a test fixture where mechanism narrative opens with the slug
    const fixture: MlRecipeEntry = {
      ...stack.recipes[0],
      mechanism_narrative: "civil_war_and_insurgency predicts conflict.",
    };
    const buyer = toBuyerView(fixture, {
      civil_war_and_insurgency: "Civil war and insurgency",
    });
    expect(buyer.mechanism_narrative).toMatch(/^Civil war and insurgency predicts/);
  });

  it("toBuyerViewList processes all recipes + builds slug map automatically", () => {
    const list = toBuyerViewList(stack.recipes);
    expect(list.length).toBe(stack.recipes.length);
    expect(list[0]).toHaveProperty("indicators");
    expect(list[0]).toHaveProperty("architecture_label");
  });
});

describe("buildSlugMap (re-export)", () => {
  it("builds map from stack recipes", () => {
    const map = buildSlugMap(stack.recipes);
    expect(Object.keys(map).length).toBe(stack.recipes.length);
    expect(map["civil_war_and_insurgency"]).toBe("Civil war and insurgency");
  });
});
