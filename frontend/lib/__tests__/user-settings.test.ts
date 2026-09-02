import { describe, it, expect } from "vitest";
import { sanitizeSettings, DEFAULT_SETTINGS } from "@/lib/user-settings";

describe("sanitizeSettings", () => {
  it("returns defaults for non-object input", () => {
    expect(sanitizeSettings(null)).toEqual(DEFAULT_SETTINGS);
    expect(sanitizeSettings("nope")).toEqual(DEFAULT_SETTINGS);
    expect(sanitizeSettings(undefined)).toEqual(DEFAULT_SETTINGS);
    expect(sanitizeSettings(42)).toEqual(DEFAULT_SETTINGS);
  });

  it("coerces watchlist to a string array, drops non-strings, caps at 200", () => {
    expect(sanitizeSettings({ watchlist: ["US", 1, null, "NG"] }).watchlist).toEqual([
      "US",
      "NG",
    ]);
    expect(sanitizeSettings({ watchlist: "US" }).watchlist).toEqual([]);
    expect(sanitizeSettings({ watchlist: Array(500).fill("US") }).watchlist).toHaveLength(
      200
    );
  });

  it("trendFocus stays null unless it's an array", () => {
    expect(sanitizeSettings({ trendFocus: null }).trendFocus).toBeNull();
    expect(sanitizeSettings({}).trendFocus).toBeNull();
    expect(sanitizeSettings({ trendFocus: ["a", 2, "b"] }).trendFocus).toEqual([
      "a",
      "b",
    ]);
  });

  it("strips unknown/extra fields (injected email, retired defaultLanding)", () => {
    const out = sanitizeSettings({
      email: "victim@x.com",
      defaultLanding: "risk-board",
      watchlist: ["US"],
    });
    expect(out).not.toHaveProperty("email");
    expect(out).not.toHaveProperty("defaultLanding");
    expect(out.watchlist).toEqual(["US"]);
  });
});
