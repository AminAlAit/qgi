import { describe, it, expect } from "vitest";
import {
  gradeLive,
  verdictFor,
  overlayCells,
  type RawLive,
} from "@/lib/hf/live-pulse-core";
import type { HfBoard } from "@/lib/hf/topics-data";

const NOW = Date.parse("2026-06-12T12:00:00Z");

function fileAt(isoAgeHours: number, cells: RawLive["cells"] = {}): RawLive {
  const gen = new Date(NOW - isoAgeHours * 3600_000).toISOString();
  return { generated_at: gen, status: "live", stale_after_hours: 2, cells };
}

describe("gradeLive — freshness thresholds", () => {
  it("grades a 30-minute-old file as live", () => {
    const g = gradeLive(fileAt(0.5), "s3", NOW);
    expect(g.status).toBe("live");
    expect(g.ageMinutes).toBe(30);
  });

  it("grades a 5-hour-old file as recent (<=26h)", () => {
    expect(gradeLive(fileAt(5), "s3", NOW).status).toBe("recent");
  });

  it("grades a 40-hour-old file as paused and drops its values", () => {
    const g = gradeLive(fileAt(40, { "LBN|T01": { pulse: 88 } }), "s3", NOW);
    expect(g.status).toBe("paused");
    expect(g.cells).toEqual({}); // paused contributes no live values
  });

  it("honors a custom stale_after_hours", () => {
    const raw = { ...fileAt(3), stale_after_hours: 6 };
    expect(gradeLive(raw, "s3", NOW).status).toBe("live"); // 3h <= 6h
  });

  it("treats seeding / warming markers as absent", () => {
    expect(gradeLive({ status: "seeding" }, "s3", NOW).status).toBe("absent");
    expect(gradeLive({ status: "warming" }, "s3", NOW).status).toBe("absent");
  });

  it("treats a missing or unparseable generated_at as absent", () => {
    expect(gradeLive({ status: "live" }, "s3", NOW).status).toBe("absent");
    expect(
      gradeLive({ generated_at: "not-a-date", status: "live" }, "s3", NOW).status
    ).toBe("absent");
  });

  it("keeps only non-null cells", () => {
    const g = gradeLive(
      fileAt(0.5, { "LBN|T01": { pulse: 70 }, "LBN|T06": { pulse: null } }),
      "s3",
      NOW
    );
    expect(g.cells).toEqual({ "LBN|T01": 70 });
  });
});

describe("verdictFor — four-way rule (thresholds 60/60)", () => {
  const thr = { struct: 60, pulse: 60 };
  it("ACTIVE when both clear", () => {
    expect(verdictFor(75, 80, thr)).toBe("ACTIVE");
  });
  it("SIGNAL when only pulse clears", () => {
    expect(verdictFor(40, 80, thr)).toBe("SIGNAL");
  });
  it("LATENT when only structure clears", () => {
    expect(verdictFor(75, 20, thr)).toBe("LATENT");
  });
  it("QUIET when neither clears", () => {
    expect(verdictFor(30, 30, thr)).toBe("QUIET");
  });
  it("null structure can never be ACTIVE/LATENT", () => {
    expect(verdictFor(null, 80, thr)).toBe("SIGNAL");
    expect(verdictFor(null, 20, thr)).toBe("QUIET");
  });
});

describe("overlayCells — pure board overlay", () => {
  const board = {
    thresholds: { struct: 60, pulse: 60 },
    cells: {
      "LBN|T01": { struct: 72, pulse: 40, prevPulse: 38, verdict: "LATENT" },
      "LBN|T06": { struct: 30, pulse: 30, prevPulse: 31, verdict: "QUIET" },
    },
  } as unknown as HfBoard;

  it("is a no-op when live is absent (returns the same cells object)", () => {
    const { cells, liveKeys } = overlayCells(board, {
      status: "absent",
      generatedAt: null,
      ageMinutes: null,
      cells: {},
      staleAfterHours: 2,
      vintage: null,
      source: "none",
    });
    expect(cells).toBe(board.cells); // identity — byte-identical render
    expect(liveKeys.size).toBe(0);
  });

  it("is a no-op when live is paused (values are not trusted past 26h)", () => {
    const { cells, liveKeys } = overlayCells(board, {
      status: "paused",
      generatedAt: "x",
      ageMinutes: 40 * 60,
      cells: { "LBN|T01": 95 }, // present but stale -> must be ignored
      staleAfterHours: 2,
      vintage: null,
      source: "s3",
    });
    expect(cells).toBe(board.cells); // identity — monthly fallback
    expect(liveKeys.size).toBe(0);
  });

  it("overlays live pulse and recomputes the verdict", () => {
    const { cells, liveKeys } = overlayCells(board, {
      status: "live",
      generatedAt: "x",
      ageMinutes: 10,
      cells: { "LBN|T01": 85 }, // structure 72 + pulse 85 -> ACTIVE
      staleAfterHours: 2,
      vintage: null,
      source: "s3",
    });
    expect(cells["LBN|T01"].pulse).toBe(85);
    expect(cells["LBN|T01"].verdict).toBe("ACTIVE");
    expect(cells["LBN|T01"].prevPulse).toBe(40); // monthly becomes the prior
    expect(cells["LBN|T06"]).toBe(board.cells["LBN|T06"]); // untouched
    expect([...liveKeys]).toEqual(["LBN|T01"]);
  });

  it("never invents a cell the board does not have", () => {
    const { cells, liveKeys } = overlayCells(board, {
      status: "live",
      generatedAt: "x",
      ageMinutes: 10,
      cells: { "ZZZ|T01": 99 },
      staleAfterHours: 2,
      vintage: null,
      source: "s3",
    });
    expect(cells["ZZZ|T01"]).toBeUndefined();
    expect(liveKeys.size).toBe(0);
  });
});
