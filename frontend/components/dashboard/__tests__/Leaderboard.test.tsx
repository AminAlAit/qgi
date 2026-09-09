import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Leaderboard } from "@/components/dashboard/Leaderboard";
import type { PatternRow } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const PATTERNS: PatternRow[] = [
  {
    country_a: "DEU",
    country_b: "FRA",
    start_year_a: 2000,
    start_year_b: 2003,
    pattern_length: 10,
    avg_correlation: 0.85,
    pattern_power_score: 0.712,
    num_indexes: 22,
    predicted: false,
  },
  {
    country_a: "USA",
    country_b: "GBR",
    start_year_a: 1995,
    start_year_b: 1998,
    pattern_length: 8,
    avg_correlation: 0.79,
    pattern_power_score: 0.644,
    num_indexes: 18,
    predicted: false,
  },
];

describe("Leaderboard", () => {
  it("renders all pattern rows", () => {
    render(<Leaderboard patterns={PATTERNS} />);
    expect(screen.getByText("DEU")).toBeInTheDocument();
    expect(screen.getByText("FRA")).toBeInTheDocument();
    expect(screen.getByText("USA")).toBeInTheDocument();
    expect(screen.getByText("GBR")).toBeInTheDocument();
  });

  it("displays PPS formatted to 3 decimal places", () => {
    render(<Leaderboard patterns={PATTERNS} />);
    expect(screen.getByText("0.712")).toBeInTheDocument();
    expect(screen.getByText("0.644")).toBeInTheDocument();
  });

  it("shows pattern length", () => {
    render(<Leaderboard patterns={PATTERNS} />);
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
  });
});
