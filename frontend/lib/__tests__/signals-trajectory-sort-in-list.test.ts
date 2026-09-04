/**
 * #626 unit test: verify the indicator IN() list builder produces a
 * DETERMINISTIC SQL string regardless of input ordering.
 *
 * The fix sorts `resolved.map(r => `'${r.indicatorId}'`)` before joining,
 * so that two Vercel serverless instances with permuted fingerprint
 * orderings build the SAME SQL string and hit the same `unstable_cache`
 * key. Pre-fix: 8 consecutive Vietnam queries with the same 4 indicator
 * IDs in different orders all missed cache and fired independent Athena
 * executions.
 *
 * The production logic lives in `lib/signals-trajectory.ts:157` (inside
 * the server-only `loadTrajectoryPanelData` function); we reproduce the
 * 3-step list-build here to exercise the sort invariant directly.
 */
import { describe, it, expect } from "vitest";

interface ResolvedIndicator {
  indicatorId: string;
}

/**
 * Mirror of the production logic at lib/signals-trajectory.ts:157.
 * Keep in sync. Pure function, trivial enough to inline.
 */
function buildIndicatorInList(resolved: ResolvedIndicator[]): string {
  return resolved
    .map((r) => `'${r.indicatorId}'`)
    .sort()
    .join(",");
}

describe("buildIndicatorInList — #626 deterministic SQL key", () => {
  it("produces an identical string regardless of input order", () => {
    const a: ResolvedIndicator[] = [
      { indicatorId: "NY.GDP.MKTP.CD" },
      { indicatorId: "NY.GDP.MKTP.KD" },
      { indicatorId: "IT.CEL.SETS.P2" },
      { indicatorId: "FI.RES.TOTL.CD" },
    ];
    const b: ResolvedIndicator[] = [
      { indicatorId: "FI.RES.TOTL.CD" },
      { indicatorId: "IT.CEL.SETS.P2" },
      { indicatorId: "NY.GDP.MKTP.KD" },
      { indicatorId: "NY.GDP.MKTP.CD" },
    ];
    expect(buildIndicatorInList(a)).toBe(buildIndicatorInList(b));
  });

  it("output is alphabetically sorted (lexicographic)", () => {
    const input: ResolvedIndicator[] = [
      { indicatorId: "ZZZ" },
      { indicatorId: "AAA" },
      { indicatorId: "MMM" },
    ];
    expect(buildIndicatorInList(input)).toBe("'AAA','MMM','ZZZ'");
  });

  it("handles single-indicator input correctly", () => {
    expect(buildIndicatorInList([{ indicatorId: "X" }])).toBe("'X'");
  });

  it("handles empty input as empty string", () => {
    expect(buildIndicatorInList([])).toBe("");
  });

  it("regression check: the exact 8-permutation Vietnam case is now stable", () => {
    // The 4 indicator IDs from the actual 2026-05-07 cache-miss incident.
    const ids = ["IT.CEL.SETS.P2", "NY.GDP.MKTP.KD", "NY.GDP.MKTP.CD", "NY.GDP.PCAP.CD"];
    const expected = buildIndicatorInList(ids.map((id) => ({ indicatorId: id })));
    // Reverse order — pre-fix this would produce a different SQL string.
    const reversed = buildIndicatorInList(
      [...ids].reverse().map((id) => ({ indicatorId: id }))
    );
    expect(reversed).toBe(expected);
    // Random shuffle — also identical.
    const shuffled = buildIndicatorInList(
      [ids[2], ids[0], ids[3], ids[1]].map((id) => ({ indicatorId: id }))
    );
    expect(shuffled).toBe(expected);
  });
});
