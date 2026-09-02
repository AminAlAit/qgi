/**
 * Unit tests for the pure math functions backing the Indicator Trajectory Panel.
 *
 * These test meanStd, pearsonR, and the z-score normalization logic
 * independently of Athena/server-only dependencies, exercising the
 * statistical correctness of the trajectory alignment algorithm.
 *
 * Yuki + Lena design decisions exercised here:
 *   - Z-score threshold: <5 non-null observed points → hasData=false
 *   - Pearson r: null when fewer than 3 overlapping pairs
 *   - The "years-from-end" index maps correctly onto calendar years
 */

import { describe, it, expect } from "vitest";

// ---------------------------------------------------------------------------
// Pure utility functions (copied/extracted here to avoid server-only import).
// Keep in sync with lib/signals-trajectory.ts.
// ---------------------------------------------------------------------------

function meanStd(arr: number[]): { mean: number; std: number } {
  if (arr.length === 0) return { mean: 0, std: 1 };
  const mean = arr.reduce((s, v) => s + v, 0) / arr.length;
  const variance = arr.reduce((s, v) => s + (v - mean) ** 2, 0) / arr.length;
  return { mean, std: Math.sqrt(variance) || 1 };
}

function pearsonR(a: (number | null)[], b: (number | null)[]): number | null {
  const pairs: [number, number][] = [];
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    if (a[i] != null && b[i] != null) pairs.push([a[i]!, b[i]!]);
  }
  if (pairs.length < 3) return null;
  const n = pairs.length;
  const mx = pairs.reduce((s, [x]) => s + x, 0) / n;
  const my = pairs.reduce((s, [, y]) => s + y, 0) / n;
  let sxy = 0,
    sxx = 0,
    syy = 0;
  for (const [x, y] of pairs) {
    sxy += (x - mx) * (y - my);
    sxx += (x - mx) ** 2;
    syy += (y - my) ** 2;
  }
  const denom = Math.sqrt(sxx * syy);
  return denom === 0 ? null : sxy / denom;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("meanStd", () => {
  it("returns mean=0, std=1 for empty array (safe fallback)", () => {
    const { mean, std } = meanStd([]);
    expect(mean).toBe(0);
    expect(std).toBe(1);
  });

  it("computes correct mean for [2, 4, 6]", () => {
    const { mean } = meanStd([2, 4, 6]);
    expect(mean).toBeCloseTo(4, 10);
  });

  it("computes correct std for [2, 4, 6] (population std)", () => {
    // Population std = sqrt(((2-4)^2 + (4-4)^2 + (6-4)^2) / 3) = sqrt(8/3)
    const { std } = meanStd([2, 4, 6]);
    expect(std).toBeCloseTo(Math.sqrt(8 / 3), 8);
  });

  it("returns std=1 when all values are identical (avoids division by zero)", () => {
    const { std } = meanStd([5, 5, 5]);
    expect(std).toBe(1);
  });
});

describe("pearsonR", () => {
  it("returns null when fewer than 3 overlapping non-null pairs", () => {
    expect(pearsonR([1, 2], [1, 2])).toBeNull();
    expect(pearsonR([1, null, 3], [1, null, 3])).toBeNull();
  });

  it("returns 1.0 for perfectly positively correlated series", () => {
    const a = [1, 2, 3, 4, 5].map((v) => v as number | null);
    const b = [2, 4, 6, 8, 10].map((v) => v as number | null);
    const r = pearsonR(a, b);
    expect(r).not.toBeNull();
    expect(r!).toBeCloseTo(1.0, 8);
  });

  it("returns -1.0 for perfectly negatively correlated series", () => {
    const a = [1, 2, 3, 4, 5].map((v) => v as number | null);
    const b = [10, 8, 6, 4, 2].map((v) => v as number | null);
    const r = pearsonR(a, b);
    expect(r).not.toBeNull();
    expect(r!).toBeCloseTo(-1.0, 8);
  });

  it("returns ~0 for uncorrelated series", () => {
    const a = [1, 2, 3, 4, 5].map((v) => v as number | null);
    const b = [3, 1, 4, 1, 5].map((v) => v as number | null);
    const r = pearsonR(a, b);
    expect(r).not.toBeNull();
    expect(Math.abs(r!)).toBeLessThan(0.5);
  });

  it("skips null values and uses only overlapping pairs", () => {
    // a: [1, null, 3, 4, 5], b: [2, null, 6, 8, 10]
    // Only pairs: (1,2), (3,6), (4,8), (5,10) — all perfectly linear
    const a = [1, null, 3, 4, 5];
    const b = [2, null, 6, 8, 10];
    const r = pearsonR(a, b);
    expect(r).not.toBeNull();
    expect(r!).toBeCloseTo(1.0, 8);
  });

  it("returns null when constant series (zero denominator)", () => {
    const a = [5, 5, 5, 5, 5].map((v) => v as number | null);
    const b = [1, 2, 3, 4, 5].map((v) => v as number | null);
    // sxx = 0 → denom = 0
    const r = pearsonR(a, b);
    expect(r).toBeNull();
  });
});

describe("z-score normalization invariants", () => {
  it("z-scoring a series gives mean≈0, std≈1 when applied back", () => {
    const raw = [10, 20, 15, 25, 30, 12, 18];
    const { mean, std } = meanStd(raw);
    const zscored = raw.map((v) => (v - mean) / std);
    const { mean: zm, std: zs } = meanStd(zscored);
    expect(Math.abs(zm)).toBeLessThan(1e-10);
    expect(Math.abs(zs - 1)).toBeLessThan(1e-10);
  });

  it("hasData threshold: <5 observed points should be flagged as insufficient", () => {
    // Simulate the hasData check from buildTrajectory.
    const observedCount = (rows: Array<{ is_predicted: boolean }>) =>
      rows.filter((r) => !r.is_predicted).length;

    expect(observedCount([]) < 5).toBe(true); // 0 → insufficient
    expect(observedCount([{ is_predicted: false }, { is_predicted: false }]) < 5).toBe(
      true
    ); // 2 → insufficient
    expect(
      observedCount([
        { is_predicted: false },
        { is_predicted: false },
        { is_predicted: false },
        { is_predicted: false },
        { is_predicted: false },
      ]) < 5
    ).toBe(false); // exactly 5 → sufficient
    expect(
      observedCount([
        { is_predicted: true },
        { is_predicted: false },
        { is_predicted: false },
        { is_predicted: false },
        { is_predicted: false },
        { is_predicted: false },
      ]) < 5
    ).toBe(false); // 5 observed (1 predicted) → sufficient
  });

  // -------------------------------------------------------------------------
  // Top-N indicator selection (filter-then-slice). Mirrors the logic in
  // lib/signals-trajectory.ts:loadTrajectoryPanelData step 1. Keep in sync.
  //
  // Bug it guards against: when an unmapped indicator (V-Dem #165 per #550)
  // appears in the raw top-N, slice-then-filter leaves the panel with 3 cards
  // instead of 4. Filter-then-slice backfills from lower-ranked-but-resolvable
  // indicators so the 2x2 grid stays full.
  // -------------------------------------------------------------------------

  function selectTopResolved(
    fingerprint: Array<{ indicator_id: number; tfidf_score: number }>,
    resolveId: (n: number) => string | null,
    n: number = 4
  ): Array<{ numericId: number; indicatorId: string }> {
    return [...fingerprint]
      .sort((a, b) => b.tfidf_score - a.tfidf_score)
      .map((fp) => ({
        numericId: fp.indicator_id,
        indicatorId: resolveId(fp.indicator_id),
      }))
      .filter((r) => r.indicatorId !== null)
      .slice(0, n) as Array<{ numericId: number; indicatorId: string }>;
  }

  it("selects 4 cards even when an unmapped indicator is in the raw top-N", () => {
    // Mirrors the actual terrorist_attack fingerprint: 4th-best by tfidf is
    // V-Dem #165 (unmapped per #550). Filter-then-slice backfills with #5
    // (GDP) so the panel renders 4 cards, not 3.
    const fingerprint = [
      { indicator_id: 1, tfidf_score: 5.84 },
      { indicator_id: 4, tfidf_score: 4.54 },
      { indicator_id: 14, tfidf_score: 4.33 },
      { indicator_id: 165, tfidf_score: 3.86 }, // unmapped
      { indicator_id: 5, tfidf_score: 3.38 }, // backfill
    ];
    const resolve = (id: number): string | null => {
      const map: Record<number, string> = {
        1: "SP.POP.TOTL",
        4: "SP.DYN.LE00.IN",
        14: "SH.DYN.MORT",
        5: "NY.GDP.MKTP.CD",
      };
      return map[id] ?? null;
    };
    const result = selectTopResolved(fingerprint, resolve);
    expect(result).toHaveLength(4);
    expect(result.map((r) => r.numericId)).toEqual([1, 4, 14, 5]);
    expect(result.every((r) => r.indicatorId !== null)).toBe(true);
  });

  it("returns empty array when no indicators resolve", () => {
    const fingerprint = [{ indicator_id: 999, tfidf_score: 5 }];
    const result = selectTopResolved(fingerprint, () => null);
    expect(result).toHaveLength(0);
  });

  it("returns fewer than N when fewer than N indicators resolve", () => {
    const fingerprint = [
      { indicator_id: 1, tfidf_score: 5 },
      { indicator_id: 999, tfidf_score: 4 },
      { indicator_id: 998, tfidf_score: 3 },
    ];
    const result = selectTopResolved(fingerprint, (id) =>
      id === 1 ? "SP.POP.TOTL" : null
    );
    expect(result).toHaveLength(1);
    expect(result[0].numericId).toBe(1);
  });

  it("respects sort order even when raw fingerprint is shuffled", () => {
    const fingerprint = [
      { indicator_id: 14, tfidf_score: 4.33 },
      { indicator_id: 1, tfidf_score: 5.84 },
      { indicator_id: 4, tfidf_score: 4.54 },
    ];
    const result = selectTopResolved(fingerprint, () => "any");
    expect(result.map((r) => r.numericId)).toEqual([1, 4, 14]);
  });

  it("years-from-end mapping: index i → yearsFromEnd = i - (patternLength - 1)", () => {
    // For a 10-year pattern, index 0 → -9, index 9 → 0, index 11 → +2.
    const patternLength = 10;
    const displayLength = 12;
    const yfe = (i: number) => i - (patternLength - 1);
    expect(yfe(0)).toBe(-9);
    expect(yfe(9)).toBe(0);
    expect(yfe(11)).toBe(2);
    // All indices in [0, displayLength).
    const all = Array.from({ length: displayLength }, (_, i) => yfe(i));
    expect(all[0]).toBe(-(patternLength - 1));
    expect(all[patternLength - 1]).toBe(0);
    expect(all[displayLength - 1]).toBe(displayLength - patternLength);
  });
});
