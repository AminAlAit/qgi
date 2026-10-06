import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { ScdiTable } from "@/components/patterns-v1/ScdiTable";

const SCDIS = [
  {
    index_name: "GDP growth (annual %)",
    sector: "Economic",
    org: "World Bank",
    correlation: 0.92,
    predicted: false,
  },
  {
    index_name: "Population, total",
    sector: "Demographic",
    org: "World Bank",
    correlation: 0.78,
    predicted: false,
  },
  {
    index_name: "Life expectancy at birth, total (years)",
    sector: "Health",
    org: "World Bank",
    correlation: 0.55,
    predicted: true,
  },
  {
    index_name: "Arms imports (SIPRI trend indicator values)",
    sector: "Military",
    org: "SIPRI / World Bank",
    correlation: 0.81,
    predicted: false,
  },
];

describe("ScdiTable", () => {
  it("renders all SCDI rows", () => {
    render(<ScdiTable scdis={SCDIS} />);
    expect(screen.getByText(/GDP growth/)).toBeInTheDocument();
    expect(screen.getByText(/Population/)).toBeInTheDocument();
    expect(screen.getByText(/Life expectancy/)).toBeInTheDocument();
  });

  it("shows PREDICTED badge for predicted rows", () => {
    render(<ScdiTable scdis={SCDIS} />);
    expect(screen.getByText("PREDICTED")).toBeInTheDocument();
  });

  it("formats correlation as 3-decimal r value", () => {
    // #125: switched from 92.0% to 0.920 — Pearson r is more appropriate
    // for the analyst audience and matches the chart subtext format.
    render(<ScdiTable scdis={SCDIS} />);
    expect(screen.getByText("0.920")).toBeInTheDocument();
    expect(screen.getByText("0.780")).toBeInTheDocument();
  });

  it("calls onRowSelect when a row is clicked", async () => {
    const onSelect = vi.fn();
    render(<ScdiTable scdis={SCDIS} onRowSelect={onSelect} />);
    await userEvent.click(screen.getByText(/GDP growth/));
    expect(onSelect).toHaveBeenCalledWith("GDP growth (annual %)");
  });

  it("filters rows by sector when chip is clicked", async () => {
    render(<ScdiTable scdis={SCDIS} />);
    const econChip = screen.getByRole("button", { name: "ECONOMIC" });
    await userEvent.click(econChip);
    // Only Economic sector rows visible
    expect(screen.getByText(/GDP growth/)).toBeInTheDocument();
    expect(screen.queryByText(/Population/)).not.toBeInTheDocument();
  });
});
