/**
 * R8 W2 fix tests — tickets #839 (arrow annotation) and #844 (cohort ECE).
 *
 * #839: When start_year_b < start_year_a, PatternMergedDetail should show
 * the "Follower:" annotation. Verified via data-convention logic, not DOM.
 *
 * #844: cohort ECE selection logic — HIGH → ece_high_cohort, etc.
 */

import { describe, it, expect } from "vitest";

// ---------------------------------------------------------------------------
// #839 — arrow annotation condition
// ---------------------------------------------------------------------------

function shouldShowFollowerAnnotation(
  start_year_a: number,
  start_year_b: number
): boolean {
  return start_year_b < start_year_a;
}

function yearGap(start_year_a: number, start_year_b: number): number {
  return start_year_a - start_year_b;
}

describe("#839 – arrow annotation (Follower: label)", () => {
  it("shows annotation when country_b started first (SA→SK case)", () => {
    // South Africa start=1965, South Korea start=1962 → SK moved first
    expect(shouldShowFollowerAnnotation(1965, 1962)).toBe(true);
  });

  it("does not show annotation when country_a started first or same year", () => {
    expect(shouldShowFollowerAnnotation(1962, 1965)).toBe(false);
    expect(shouldShowFollowerAnnotation(1965, 1965)).toBe(false);
  });

  it("computes yearGap correctly for SA→SK", () => {
    expect(yearGap(1965, 1962)).toBe(3);
  });

  it("yearGap is positive only when annotation should show", () => {
    const gap = yearGap(1965, 1962);
    expect(gap).toBeGreaterThan(0);
    expect(shouldShowFollowerAnnotation(1965, 1962)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// #844 — cohort ECE selection
// ---------------------------------------------------------------------------

type RiskTier = "HIGH" | "MODERATE" | "INDICATIVE";

function selectCohortEce(
  tier: RiskTier | undefined,
  ece_high_cohort: number,
  ece_mid_cohort: number,
  ece_low_cohort: number,
  ece_overall: number
): number {
  const cohortEce =
    tier === "HIGH"
      ? ece_high_cohort
      : tier === "MODERATE"
        ? ece_mid_cohort
        : tier === "INDICATIVE"
          ? ece_low_cohort
          : null;
  return cohortEce ?? ece_overall;
}

describe("#844 – cohort-stratified ECE selection", () => {
  const eceMock = {
    ece_high_cohort: 0.034,
    ece_mid_cohort: 0.0073,
    ece_low_cohort: 0.0043,
    ece_overall: 0.0122,
  };

  it("HIGH tier → ece_high_cohort", () => {
    const result = selectCohortEce(
      "HIGH",
      ...(Object.values(eceMock) as [number, number, number, number])
    );
    expect(result).toBe(0.034);
  });

  it("MODERATE tier → ece_mid_cohort", () => {
    const result = selectCohortEce(
      "MODERATE",
      ...(Object.values(eceMock) as [number, number, number, number])
    );
    expect(result).toBe(0.0073);
  });

  it("INDICATIVE tier → ece_low_cohort", () => {
    const result = selectCohortEce(
      "INDICATIVE",
      ...(Object.values(eceMock) as [number, number, number, number])
    );
    expect(result).toBe(0.0043);
  });

  it("undefined tier falls back to ece_overall", () => {
    const result = selectCohortEce(
      undefined,
      ...(Object.values(eceMock) as [number, number, number, number])
    );
    expect(result).toBe(0.0122);
  });

  it("Uganda HIGH scenario: cohort ECE (0.034) differs from overall (0.012)", () => {
    // Uganda is HIGH tier; elections_and_voting ece_high_cohort=0.034 > 0.02 threshold
    const cohortEce = selectCohortEce("HIGH", 0.034, 0.0073, 0.0043, 0.0122);
    expect(cohortEce).toBe(0.034);
    expect(cohortEce).toBeGreaterThan(0.02); // above calibration-gap threshold
    expect(0.0122).toBeLessThan(0.02); // overall was incorrectly "well-calibrated"
  });
});
