import { describe, it, expect } from "vitest";
import { applyTransformation } from "@/lib/transforms";

const VALUES = [10, 20, 30, 40, 50];

describe("applyTransformation", () => {
  it("raw returns values unchanged", () => {
    expect(applyTransformation(VALUES, "raw")).toEqual(VALUES);
  });

  it("normalised maps to [0, 1]", () => {
    const result = applyTransformation(VALUES, "normalised");
    expect(result[0]).toBe(0);
    expect(result[result.length - 1]).toBe(1);
    for (const v of result) {
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThanOrEqual(1);
    }
  });

  it("standardised has mean ~0 and std ~1", () => {
    const result = applyTransformation(VALUES, "standardised");
    const mean = result.reduce((s, v) => s + v, 0) / result.length;
    expect(Math.abs(mean)).toBeLessThan(1e-10);
    const variance = result.reduce((s, v) => s + (v - mean) ** 2, 0) / result.length;
    expect(Math.abs(Math.sqrt(variance) - 1)).toBeLessThan(1e-10);
  });

  it("base_indexed sets first value to 100", () => {
    const result = applyTransformation(VALUES, "base_indexed");
    expect(result[0]).toBe(100);
    expect(result[1]).toBe(200); // 20/10 * 100
  });

  it("log produces increasing values for positive input", () => {
    const result = applyTransformation(VALUES, "log");
    expect(result.length).toBe(VALUES.length);
    for (let i = 1; i < result.length; i++) {
      expect(result[i]).toBeGreaterThan(result[i - 1]);
    }
  });

  it("growth first value is 0 by convention", () => {
    const result = applyTransformation(VALUES, "growth");
    expect(result[0]).toBe(0);
    expect(result[1]).toBeCloseTo(100); // (20-10)/10 * 100
  });

  it("handles empty array", () => {
    expect(applyTransformation([], "raw")).toEqual([]);
    expect(applyTransformation([], "normalised")).toEqual([]);
  });

  it("normalised handles constant array", () => {
    const result = applyTransformation([5, 5, 5], "normalised");
    expect(result).toEqual([0, 0, 0]);
  });
});
