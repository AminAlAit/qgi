import { describe, it, expect } from "vitest";
import { getIndicatorLabel, resolveIndicatorLabel } from "@/lib/indicator-labels";

describe("resolveIndicatorLabel", () => {
  it("resolves WB code from supplementary map + appends transform descriptor", () => {
    const result = resolveIndicatorLabel("VC.BTL.DETH__diff");
    expect(result.label).toBe(
      "Battle-related deaths (number of people) (year-over-year change)"
    );
    expect(result.found).toBe(true);
    expect(result.baseId).toBe("VC.BTL.DETH");
    expect(result.transformLabel).toBe("year-over-year change");
  });

  it("resolves V-Dem code from supplementary map", () => {
    const result = resolveIndicatorLabel("v2x_polyarchy__diff");
    expect(result.label).toBe(
      "Electoral democracy index (V-Dem) (year-over-year change)"
    );
    expect(result.found).toBe(true);
    expect(result.baseId).toBe("v2x_polyarchy");
  });

  it("resolves WB code from indexes.json catalog (PV.EST)", () => {
    const result = resolveIndicatorLabel("PV.EST__diff");
    expect(result.label).toBe(
      "Political Stability and Absence of Violence/Terrorism (estimate) (year-over-year change)"
    );
    expect(result.found).toBe(true);
  });

  it("graceful fallback for unknown base code — surfaces the raw code", () => {
    const result = resolveIndicatorLabel("UNKNOWN.CODE.X__diff");
    expect(result.label).toBe("UNKNOWN.CODE.X (year-over-year change)");
    expect(result.found).toBe(false);
    expect(result.baseId).toBe("UNKNOWN.CODE.X");
  });

  it("no transform when base code has no recognized suffix", () => {
    const result = resolveIndicatorLabel("VC.BTL.DETH");
    expect(result.label).toBe("Battle-related deaths (number of people)");
    expect(result.transformLabel).toBe("");
  });

  it("handles __lag transform", () => {
    const result = resolveIndicatorLabel("VC.BTL.DETH__lag");
    expect(result.label).toBe("Battle-related deaths (number of people) (lagged value)");
    expect(result.transformLabel).toBe("lagged value");
  });

  it("handles __zscore transform", () => {
    const result = resolveIndicatorLabel("VC.BTL.DETH__zscore");
    expect(result.transformLabel).toBe("z-score");
  });

  it("strips longest suffix first (defensive against future __z addition)", () => {
    // If a future single-letter __z were added, __zscore must still match first
    const result = resolveIndicatorLabel("FOO__zscore");
    expect(result.transformLabel).toBe("z-score");
    expect(result.baseId).toBe("FOO");
  });

  it("getIndicatorLabel returns just the string", () => {
    expect(getIndicatorLabel("VC.BTL.DETH__diff")).toBe(
      "Battle-related deaths (number of people) (year-over-year change)"
    );
  });

  it("empty / null / undefined input is handled gracefully", () => {
    // 2026-05-30: empty / null / undefined all now return the same safe
    // placeholder so the SSR import chain (countries-v4-data → indicator-
    // labels) cannot crash on a bake gap (one fleet-run-1 SHAP entry
    // shipped with no indicator_code).
    expect(resolveIndicatorLabel("").label).toBe("(indicator code missing)");
    expect(resolveIndicatorLabel("").found).toBe(false);
    expect(resolveIndicatorLabel(null).label).toBe("(indicator code missing)");
    expect(resolveIndicatorLabel(undefined).label).toBe("(indicator code missing)");
  });
});
