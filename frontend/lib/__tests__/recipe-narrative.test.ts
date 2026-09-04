import { describe, it, expect } from "vitest";
import { buildSlugMap, rewriteRecipeSlugsInProse } from "@/lib/recipe-narrative";

const SLUG_MAP = {
  civil_war_and_insurgency: "Civil war and insurgency",
  elections_and_voting: "Elections and voting",
  bilateral_treaty: "Bilateral treaty",
};

describe("rewriteRecipeSlugsInProse", () => {
  it("capitalizes display name at sentence start (position 0)", () => {
    const out = rewriteRecipeSlugsInProse(
      "civil_war_and_insurgency predicts active-conflict onset.",
      SLUG_MAP
    );
    expect(out).toBe("Civil war and insurgency predicts active-conflict onset.");
  });

  it("lowercases first letter mid-sentence", () => {
    const out = rewriteRecipeSlugsInProse(
      "Under D5, elections_and_voting uses different features.",
      SLUG_MAP
    );
    expect(out).toBe("Under D5, elections and voting uses different features.");
  });

  it("handles multiple slugs in one string", () => {
    const out = rewriteRecipeSlugsInProse(
      "Compare civil_war_and_insurgency with bilateral_treaty: both rely on D2.",
      SLUG_MAP
    );
    expect(out).toBe(
      "Compare civil war and insurgency with bilateral treaty: both rely on D2."
    );
  });

  it("respects word boundaries — does not match inside other words", () => {
    // Made-up: "pre_civil_war_and_insurgency_post" should NOT match
    const out = rewriteRecipeSlugsInProse(
      "pre_civil_war_and_insurgency_post is a fake compound token.",
      SLUG_MAP
    );
    // Match should NOT replace inside the bigger compound token
    expect(out).toBe("pre_civil_war_and_insurgency_post is a fake compound token.");
  });

  it("handles slug at end of string", () => {
    const out = rewriteRecipeSlugsInProse(
      "The model trained on civil_war_and_insurgency",
      SLUG_MAP
    );
    expect(out).toBe("The model trained on civil war and insurgency");
  });

  it("handles slug followed by punctuation", () => {
    const out = rewriteRecipeSlugsInProse(
      "Sibling recipes (civil_war_and_insurgency, elections_and_voting).",
      SLUG_MAP
    );
    expect(out).toBe("Sibling recipes (civil war and insurgency, elections and voting).");
  });

  it("returns input unchanged when no slug present", () => {
    const out = rewriteRecipeSlugsInProse("No slugs in this sentence.", SLUG_MAP);
    expect(out).toBe("No slugs in this sentence.");
  });

  it("returns empty input as empty", () => {
    expect(rewriteRecipeSlugsInProse("", SLUG_MAP)).toBe("");
  });

  it("handles empty slug map (no-op)", () => {
    expect(
      rewriteRecipeSlugsInProse("civil_war_and_insurgency predicts conflict.", {})
    ).toBe("civil_war_and_insurgency predicts conflict.");
  });
});

describe("buildSlugMap", () => {
  it("builds map from recipe entries", () => {
    const map = buildSlugMap([
      // Only the fields we care about; cast to satisfy the type
      {
        recipe_id: "civil_war_and_insurgency",
        display_name: "Civil war and insurgency",
      } as never,
      {
        recipe_id: "elections_and_voting",
        display_name: "Elections and voting",
      } as never,
    ]);
    expect(map).toEqual({
      civil_war_and_insurgency: "Civil war and insurgency",
      elections_and_voting: "Elections and voting",
    });
  });

  it("skips entries with missing recipe_id or display_name", () => {
    const map = buildSlugMap([
      { recipe_id: "valid_slug", display_name: "Valid display" } as never,
      { recipe_id: "", display_name: "No id" } as never,
      { recipe_id: "no_name", display_name: "" } as never,
    ]);
    expect(map).toEqual({ valid_slug: "Valid display" });
  });

  it("empty input → empty map", () => {
    expect(buildSlugMap([])).toEqual({});
  });
});
