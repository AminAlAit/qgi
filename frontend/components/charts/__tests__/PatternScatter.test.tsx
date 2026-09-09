import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { PatternScatter } from "@/components/charts/PatternScatter";
import type { PatternRow } from "@/lib/types";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mockPush }) }));

const mockOnEvents: { click?: (p: unknown) => void } = {};

vi.mock("echarts-for-react", () => ({
  default: ({
    option,
    onEvents,
  }: {
    option: { title: { text: string } };
    onEvents: Record<string, (p: unknown) => void>;
  }) => {
    Object.assign(mockOnEvents, onEvents);
    return <div data-testid="scatter" data-title={option.title.text} />;
  },
}));

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
];

describe("PatternScatter", () => {
  it("renders the chart with correct title", () => {
    render(<PatternScatter patterns={PATTERNS} />);
    const el = screen.getByTestId("scatter");
    expect(el.getAttribute("data-title")).toContain("Strengths & Lengths");
  });

  it("navigates to Patterns Portal on point click", async () => {
    render(<PatternScatter patterns={PATTERNS} />);
    // Simulate ECharts click event. PatternScatter's data tuple is 9-wide:
    // [length, num_indexes, pps, country_a, country_b, start_a, start_b,
    //  country_a_id ?? country_a, country_b_id ?? country_b]
    // The ID slots (7, 8) are what feed the URL — earlier this session the
    // component was widened to prefer numeric country_a_id; this test used
    // to pass 7 values and `caId`/`cbId` destructured to `undefined`,
    // making the URL "country_a=undefined".
    mockOnEvents.click?.({
      value: [10, 22, 0.712, "DEU", "FRA", 2000, 2003, "DEU", "FRA"],
    });
    expect(mockPush).toHaveBeenCalledWith(expect.stringContaining("country_a=DEU"));
    expect(mockPush).toHaveBeenCalledWith(expect.stringContaining("country_b=FRA"));
  });
});
