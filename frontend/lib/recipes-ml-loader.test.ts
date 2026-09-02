/**
 * Tests for `lib/recipes-ml-loader.ts`. Reads the live
 * `data/ml-recipe-stack.json` artifact on this branch + asserts the
 * top-level invariants that V2 route handlers depend on.
 */
import { describe, expect, it, beforeEach } from "vitest";
import {
  _resetMlRecipeStackCache,
  loadMlRecipeBySlug,
  loadMlRecipeStack,
} from "./recipes-ml-loader";

describe("recipes-ml-loader", () => {
  beforeEach(() => {
    _resetMlRecipeStackCache();
  });

  it("loads the stack with schema_version 1.0", async () => {
    const stack = await loadMlRecipeStack();
    expect(stack.metadata.schema_version).toBe("1.0");
    expect(stack.metadata.n_recipes).toBe(4);
  });

  it("metadata lists exactly the top-4 ship list", async () => {
    const stack = await loadMlRecipeStack();
    expect(new Set(stack.metadata.top_4_recipes)).toEqual(
      new Set([
        "civil_war_and_insurgency",
        "multilateral_agreement",
        "elections_and_voting",
        "bilateral_treaty",
      ])
    );
  });

  it("interpretation_hint per recipe matches the #656 DECISION", async () => {
    const stack = await loadMlRecipeStack();
    const byId = Object.fromEntries(
      stack.recipes.map((r) => [r.recipe_id, r.interpretation_hint])
    );
    expect(byId["civil_war_and_insurgency"]).toBe("risk_elevation");
    expect(byId["multilateral_agreement"]).toBe("ambiguous");
    expect(byId["elections_and_voting"]).toBe("ambiguous");
    expect(byId["bilateral_treaty"]).toBe("ambiguous");
  });

  it("disclosures block is embedded", async () => {
    const stack = await loadMlRecipeStack();
    expect(stack.disclosures).toBeTruthy();
    expect(stack.disclosures.schema_version).toBe("1.0");
  });

  it("loadMlRecipeBySlug returns the recipe entry", async () => {
    const r = await loadMlRecipeBySlug("civil_war_and_insurgency");
    expect(r).not.toBeNull();
    expect(r?.tier).toBe("STRONG");
    expect(r?.architecture).toBe("D2");
  });

  it("loadMlRecipeBySlug returns null for unknown slug", async () => {
    const r = await loadMlRecipeBySlug("not_a_real_recipe");
    expect(r).toBeNull();
  });

  it("caches the stack across calls", async () => {
    const a = await loadMlRecipeStack();
    const b = await loadMlRecipeStack();
    expect(a).toBe(b);
  });
});
