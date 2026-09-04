import { describe, it, expect } from "vitest";
import {
  INDICATOR_NUMERIC_SUPPLEMENT,
  buildIndicatorNameLookup,
  isBakedUnknown,
} from "@/lib/indicator-numeric-supplement";
import recipesData from "@/data/recipes-aggregated.json";
import indexesData from "@/data/indexes.json";

interface FingerprintEntry {
  indicator_id: number;
  indicator_name: string;
}
interface Recipe {
  indicator_fingerprint: FingerprintEntry[];
}

describe("indicator-numeric-supplement", () => {
  it("covers every '(unknown N)' currently baked into recipes-aggregated.json", () => {
    // Guards against the root-cause regression: if a future Athena bake
    // introduces a new unknown numeric_id, this test fails loudly and
    // the developer must extend the supplement (or fix indexes.json).
    const recipes = (recipesData as { recipes: Recipe[] }).recipes;
    const unknownIds = new Set<number>();
    for (const r of recipes) {
      for (const f of r.indicator_fingerprint) {
        if (isBakedUnknown(f.indicator_name)) {
          unknownIds.add(f.indicator_id);
        }
      }
    }
    const supplementIds = new Set(Object.keys(INDICATOR_NUMERIC_SUPPLEMENT).map(Number));
    const missing = [...unknownIds].filter((id) => !supplementIds.has(id));
    expect(
      missing,
      `recipes-aggregated.json contains unknown indicator_ids ${missing.join(", ")} that the numeric supplement does not cover. Resolve them via qgi-data/reference/indicator-allow-list.json and add to INDICATOR_NUMERIC_SUPPLEMENT.`
    ).toEqual([]);
  });

  it("supplement never overwrites an indexes.json entry", () => {
    // The supplement is strictly additive: indexes.json wins on overlap.
    // Anything else would be a silent rename that bypasses curation.
    const indexIds = new Set<number>();
    for (const idx of indexesData as Array<{ numeric_id: number }>) {
      if (typeof idx.numeric_id === "number") {
        indexIds.add(idx.numeric_id);
      }
    }
    const overlap = Object.keys(INDICATOR_NUMERIC_SUPPLEMENT)
      .map(Number)
      .filter((id) => indexIds.has(id));
    expect(
      overlap,
      `Supplement entries ${overlap.join(", ")} also exist in indexes.json. Remove the supplement override and let the catalog be the source of truth.`
    ).toEqual([]);
  });

  it("buildIndicatorNameLookup overlays supplement onto a base catalog", () => {
    const base: Array<readonly [number, string]> = [
      [15, "Fertility rate, total (births per woman)"],
      [200, "Custom Indicator 200"],
    ];
    const m = buildIndicatorNameLookup(base);
    // base entries preserved
    expect(m.get(15)).toBe("Fertility rate, total (births per woman)");
    expect(m.get(200)).toBe("Custom Indicator 200");
    // supplement fills gaps
    expect(m.get(165)).toBe("Fertility rate, total (births per woman)");
    expect(m.get(276)).toBe("Electoral Democracy Index (V-Dem)");
    expect(m.get(307)).toBe("Free and Fair Elections Index (V-Dem)");
    // unknown is undefined
    expect(m.get(999)).toBeUndefined();
  });

  it("base catalog wins when both define the same numeric_id", () => {
    // Defense-in-depth: even if a supplement entry were accidentally
    // duplicated into indexes.json, the indexes.json value must win
    // (it's the curated source of truth).
    const base: Array<readonly [number, string]> = [[165, "Base catalog wins"]];
    const m = buildIndicatorNameLookup(base);
    expect(m.get(165)).toBe("Base catalog wins");
  });

  it("isBakedUnknown matches the bake script's placeholder format", () => {
    expect(isBakedUnknown("(unknown 165)")).toBe(true);
    expect(isBakedUnknown("(unknown 9999)")).toBe(true);
    expect(isBakedUnknown("Fertility rate, total (births per woman)")).toBe(false);
    expect(isBakedUnknown("(unknown)")).toBe(false); // no id
    expect(isBakedUnknown("unknown 165")).toBe(false); // no parens
    expect(isBakedUnknown(undefined)).toBe(false);
    expect(isBakedUnknown("")).toBe(false);
  });
});
