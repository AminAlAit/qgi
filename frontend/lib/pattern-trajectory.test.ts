import { describe, expect, it } from "vitest";
import {
  EVENT_LOOKUP_TOLERANCE_YEARS,
  computePatternTrajectory,
  findTerminatingEvent,
  type VerifiedEvent,
} from "./pattern-trajectory";

const SAMPLE_EVENTS: VerifiedEvent[] = [
  {
    country: "South Korea",
    year: 1987,
    title: "Democratization protests force constitutional reform",
    category: "elections_and_voting",
    source: "https://example/kr-1987",
  },
  {
    country: "South Korea",
    year: 2017,
    title: "Park impeachment",
    category: "elections_and_voting",
    source: "https://example/kr-2017",
  },
  {
    country: "Paraguay",
    year: 1989,
    title: "Stroessner ousted in coup",
    category: "military_coup",
    source: "https://example/py-1989",
  },
  {
    country: "Brazil",
    year: 2019,
    title: "Amazon deforestation surge",
    category: "environmental_disaster",
    source: "https://example/br-2019",
  },
];

describe("findTerminatingEvent", () => {
  it("returns the closest event for the matching country within tolerance", () => {
    const ev = findTerminatingEvent("South Korea", 1987, SAMPLE_EVENTS);
    expect(ev).not.toBeNull();
    expect(ev!.year).toBe(1987);
    expect(ev!.title).toMatch(/Democratization/);
  });

  it("matches across case differences in country name", () => {
    const ev = findTerminatingEvent("south korea", 2017, SAMPLE_EVENTS);
    expect(ev?.title).toBe("Park impeachment");
  });

  it("returns null when no event for the country exists in tolerance window", () => {
    const ev = findTerminatingEvent("South Korea", 2050, SAMPLE_EVENTS);
    expect(ev).toBeNull();
  });

  it("returns null when the country has no events at all", () => {
    const ev = findTerminatingEvent("Atlantis", 2000, SAMPLE_EVENTS);
    expect(ev).toBeNull();
  });

  it("prefers the closest year when multiple events match", () => {
    const events: VerifiedEvent[] = [
      { country: "X", year: 2000, title: "Far", category: "c", source: "s" },
      { country: "X", year: 2001, title: "Near", category: "c", source: "s" },
    ];
    const ev = findTerminatingEvent("X", 2001, events);
    expect(ev?.title).toBe("Near");
  });

  it("respects the ±tolerance boundary (inclusive)", () => {
    const events: VerifiedEvent[] = [
      {
        country: "X",
        year: 2000 + EVENT_LOOKUP_TOLERANCE_YEARS,
        title: "Edge",
        category: "c",
        source: "s",
      },
    ];
    expect(findTerminatingEvent("X", 2000, events)?.title).toBe("Edge");
  });

  it("excludes events outside tolerance", () => {
    const events: VerifiedEvent[] = [
      {
        country: "X",
        year: 2000 + EVENT_LOOKUP_TOLERANCE_YEARS + 1,
        title: "OutOfRange",
        category: "c",
        source: "s",
      },
    ];
    expect(findTerminatingEvent("X", 2000, events)).toBeNull();
  });

  it("marks the result as algorithmic (dataEditorial=false) by default", () => {
    const ev = findTerminatingEvent("South Korea", 1987, SAMPLE_EVENTS);
    expect(ev?.dataEditorial).toBe(false);
  });
});

describe("computePatternTrajectory", () => {
  it("computes leader/follower end years and follower elapsed years correctly", () => {
    const row = {
      country_a: "South Korea",
      country_b: "Paraguay",
      start_year_a: 1962,
      start_year_b: 1963,
      pattern_length: 64,
    };
    const t = computePatternTrajectory(row, SAMPLE_EVENTS, 2026);
    expect(t.leaderEndYear).toBe(1962 + 64);
    expect(t.followerEndYear).toBe(1963 + 64);
    expect(t.followerYearsElapsed).toBe(2026 - 1963);
    expect(t.patternLength).toBe(64);
  });

  it("clamps followerYearsElapsed below 0 to 0", () => {
    const row = {
      country_a: "X",
      country_b: "Y",
      start_year_a: 1900,
      start_year_b: 2100,
      pattern_length: 10,
    };
    const t = computePatternTrajectory(row, [], 2026);
    expect(t.followerYearsElapsed).toBe(0);
  });

  it("clamps followerYearsElapsed above pattern_length to pattern_length", () => {
    const row = {
      country_a: "X",
      country_b: "Y",
      start_year_a: 1900,
      start_year_b: 1900,
      pattern_length: 10,
    };
    const t = computePatternTrajectory(row, [], 2026);
    expect(t.followerYearsElapsed).toBe(10);
  });

  it("populates terminatingEvent when leader has an event near end year", () => {
    const row = {
      country_a: "South Korea",
      country_b: "Paraguay",
      start_year_a: 1985,
      start_year_b: 1987,
      pattern_length: 2,
    };
    const t = computePatternTrajectory(row, SAMPLE_EVENTS, 2026);
    expect(t.terminatingEvent?.title).toMatch(/Democratization/);
  });

  it("leaves terminatingEvent null when no event in tolerance", () => {
    const row = {
      country_a: "Brazil",
      country_b: "Argentina",
      start_year_a: 1900,
      start_year_b: 1900,
      pattern_length: 10,
    };
    const t = computePatternTrajectory(row, SAMPLE_EVENTS, 2026);
    expect(t.terminatingEvent).toBeNull();
  });

  it("populates falsificationAnchor when terminatingEvent is non-null", () => {
    const row = {
      country_a: "South Korea",
      country_b: "Paraguay",
      start_year_a: 1985,
      start_year_b: 1987,
      pattern_length: 2,
    };
    const t = computePatternTrajectory(row, SAMPLE_EVENTS, 2026);
    expect(t.falsificationAnchor).not.toBeNull();
    expect(t.falsificationAnchor!.followerCountry).toBe("Paraguay");
    expect(t.falsificationAnchor!.eventCategory).toBe("elections_and_voting");
    expect(t.falsificationAnchor!.eventCategoryDisplay).toBe("Elections And Voting");
    // followerEndYear = 1987 + 2 = 1989, so window = [1988, 1990]
    expect(t.falsificationAnchor!.windowStart).toBe(1988);
    expect(t.falsificationAnchor!.windowEnd).toBe(1990);
  });

  // #831 (R8-W1redo-Priya-1) — isWindowElapsed flag
  it("sets isWindowElapsed=true when windowEnd is before currentYear", () => {
    // followerEndYear = 1987 + 2 = 1989; windowEnd = 1990. currentYear = 2026 → elapsed.
    const row = {
      country_a: "South Korea",
      country_b: "Paraguay",
      start_year_a: 1985,
      start_year_b: 1987,
      pattern_length: 2,
    };
    const t = computePatternTrajectory(row, SAMPLE_EVENTS, 2026);
    expect(t.falsificationAnchor!.isWindowElapsed).toBe(true);
  });

  it("sets isWindowElapsed=false when windowEnd is in the future", () => {
    // followerEndYear = 2030 + 2 = 2032; windowEnd = 2033. currentYear = 2026 → not elapsed.
    const row = {
      country_a: "South Korea",
      country_b: "Paraguay",
      start_year_a: 1985,
      start_year_b: 2030,
      pattern_length: 2,
    };
    const t = computePatternTrajectory(row, SAMPLE_EVENTS, 2026);
    expect(t.falsificationAnchor!.isWindowElapsed).toBe(false);
  });

  it("leaves falsificationAnchor null when terminatingEvent is null", () => {
    const row = {
      country_a: "Brazil",
      country_b: "Argentina",
      start_year_a: 1900,
      start_year_b: 1900,
      pattern_length: 10,
    };
    const t = computePatternTrajectory(row, SAMPLE_EVENTS, 2026);
    expect(t.terminatingEvent).toBeNull();
    expect(t.falsificationAnchor).toBeNull();
  });

  it("uses leader (country_a) for the event lookup, not follower (country_b)", () => {
    // Paraguay has 1989 coup; South Korea has 1987 democratization.
    // If we accidentally look up follower (country_b = Paraguay) instead
    // of leader (country_a = South Korea) for a leader-end-year=1987
    // pair, we would return the Paraguay 1989 coup. We should return
    // the South Korea 1987 event.
    const row = {
      country_a: "South Korea",
      country_b: "Paraguay",
      start_year_a: 1985,
      start_year_b: 1987,
      pattern_length: 2, // leader end = 1987
    };
    const t = computePatternTrajectory(row, SAMPLE_EVENTS, 2026);
    expect(t.terminatingEvent?.country).toBe("South Korea");
    expect(t.terminatingEvent?.title).toMatch(/Democratization/);
  });
});
