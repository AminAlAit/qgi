import { describe, it, expect } from "vitest";
import {
  zTo100,
  windowKey,
  buildBucketSeries,
  type BaselineDoc,
} from "@/lib/hf/live-pulse-buckets-core";

describe("zTo100 — poller pulse mapping parity", () => {
  it("maps z=0 to 50 (own normal)", () => {
    expect(zTo100(0)).toBe(50);
  });
  it("maps +1 sigma to 70 and -1 sigma to 30", () => {
    expect(zTo100(1)).toBe(70);
    expect(zTo100(-1)).toBe(30);
  });
  it("clamps to [2, 100], never 0", () => {
    expect(zTo100(10)).toBe(100);
    expect(zTo100(-10)).toBe(2);
  });
});

describe("windowKey — 15-min stamp to window label", () => {
  it("floors to the hour for 1H", () => {
    expect(windowKey("20260614013000", "1H")).toBe("2026-06-14 01:00");
  });
  it("floors to the 4-hour block for 4H", () => {
    expect(windowKey("20260614053000", "4H")).toBe("2026-06-14 04:00");
  });
  it("floors to the day for 1D", () => {
    expect(windowKey("20260614013000", "1D")).toBe("2026-06-14");
  });
});

describe("buildBucketSeries — reproduces the poller pulse", () => {
  // vec layout: [total, T01, T02, T03, T05, T06, T07]
  const buckets = {
    "20260614010000": { XXX: [100, 0, 15, 0, 0, 0, 0] },
    "20260614011500": { XXX: [100, 0, 15, 0, 0, 0, 0] },
  };
  const baseline: BaselineDoc = {
    stats: { "XXX|T02": { mu: 0.1, sigma: 0.05 } },
  };

  it("computes share = topic/total, z vs baseline, pulse = 50 + 20z", () => {
    const out = buildBucketSeries(buckets, baseline, "XXX", "1H");
    expect(out).not.toBeNull();
    // 1H window sums the two slots: total 200, T02 30 -> share 0.15
    // z = (0.15 - 0.1) / 0.05 = 1.0 -> pulse 70
    expect(out!["T02"].x).toEqual(["2026-06-14 01:00"]);
    expect(out!["T02"].y).toEqual([70]);
    expect(out!["T02"].reliable).toBe(true); // total 200 >= 1H floor 25
  });

  it("returns neutral 50 for a topic with no baseline stat", () => {
    const out = buildBucketSeries(buckets, baseline, "XXX", "1H");
    expect(out!["T01"].y).toEqual([50]); // no XXX|T01 stat -> neutral, not a spike
  });

  it("emits neutral 50 when topic docs are below the per-window floor", () => {
    // T03 has 1 doc in the window (< 1H floor of 2) despite a healthy total
    // and a baseline stat -> neutral, not a false dip (poller sparsity rule).
    const thin = { "20260614010000": { XXX: [100, 0, 0, 1, 0, 0, 0] } };
    const bl: BaselineDoc = { stats: { "XXX|T03": { mu: 0.1, sigma: 0.05 } } };
    const out = buildBucketSeries(thin, bl, "XXX", "1H");
    expect(out!["T03"].y).toEqual([50]);
  });

  it("returns null for a country absent from the cache", () => {
    expect(buildBucketSeries(buckets, baseline, "ZZZ", "1H")).toBeNull();
  });

  it("emits all six board topics", () => {
    const out = buildBucketSeries(buckets, baseline, "XXX", "1D");
    expect(Object.keys(out!).sort()).toEqual(["T01", "T02", "T03", "T05", "T06", "T07"]);
  });
});
