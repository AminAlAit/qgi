import { describe, expect, it } from "vitest";
import {
  formatBakeMonthYear,
  formatDataThrough,
  daysSinceBake,
} from "@/lib/format-bake-date";

describe("formatBakeMonthYear", () => {
  it("formats a valid ISO date as 'Month YYYY'", () => {
    expect(formatBakeMonthYear("2026-04-30")).toBe("April 2026");
    expect(formatBakeMonthYear("2025-12-15")).toBe("December 2025");
    expect(formatBakeMonthYear("2024-01-01")).toBe("January 2024");
  });

  it("returns empty string for falsy or malformed input", () => {
    expect(formatBakeMonthYear(undefined)).toBe("");
    expect(formatBakeMonthYear(null)).toBe("");
    expect(formatBakeMonthYear("")).toBe("");
    expect(formatBakeMonthYear("bad input")).toBe("");
    expect(formatBakeMonthYear("2026/04/30")).toBe("");
    expect(formatBakeMonthYear("2026-13-01")).toBe("");
  });
});

describe("formatDataThrough", () => {
  it("composes 'Data through {Month YYYY}' for valid dates", () => {
    expect(formatDataThrough("2026-04-30")).toBe("Data through April 2026");
  });

  it("falls back to 'Data release unknown' for bad input", () => {
    expect(formatDataThrough(undefined)).toBe("Data release unknown");
    expect(formatDataThrough("bad")).toBe("Data release unknown");
  });
});

describe("daysSinceBake", () => {
  it("returns the integer day-count for a past bake", () => {
    const now = new Date("2026-05-18T15:00:00Z");
    expect(daysSinceBake("2026-04-30", now)).toBe(18);
    expect(daysSinceBake("2026-05-18", now)).toBe(0);
    expect(daysSinceBake("2026-05-17", now)).toBe(1);
  });

  it("returns null for future bake dates (sanity guard)", () => {
    const now = new Date("2026-05-18T15:00:00Z");
    expect(daysSinceBake("2026-05-19", now)).toBe(null);
    expect(daysSinceBake("2027-01-01", now)).toBe(null);
  });

  it("returns null for malformed or missing input", () => {
    expect(daysSinceBake(undefined)).toBe(null);
    expect(daysSinceBake(null)).toBe(null);
    expect(daysSinceBake("")).toBe(null);
    expect(daysSinceBake("bad input")).toBe(null);
    expect(daysSinceBake("2026/04/30")).toBe(null);
  });

  it("is time-of-day independent (stable per UTC date)", () => {
    const morningUtc = new Date("2026-05-18T00:00:01Z");
    const lateUtc = new Date("2026-05-18T23:59:59Z");
    expect(daysSinceBake("2026-04-30", morningUtc)).toBe(
      daysSinceBake("2026-04-30", lateUtc)
    );
  });
});
