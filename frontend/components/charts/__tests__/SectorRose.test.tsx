import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { SectorRose } from "@/components/charts/SectorRose";

// Mock ReactECharts — it relies on a browser canvas
vi.mock("echarts-for-react", () => ({
  default: ({ option }: { option: { series: { data: { name: string }[] }[] } }) => {
    const sectors = option.series[0].data.map((d: { name: string }) => d.name);
    return (
      <div data-testid="sector-rose">
        {sectors.map((s: string) => (
          <span key={s}>{s}</span>
        ))}
      </div>
    );
  },
}));

const SECTORS = [
  { name: "Economic", value: 42 },
  { name: "Military", value: 12 },
  { name: "Health", value: 18 },
  { name: "Trade", value: 25 },
  { name: "Governance", value: 15 },
  { name: "Demographic", value: 8 },
  { name: "Social", value: 10 },
  { name: "Education", value: 7 },
  { name: "Infrastructure", value: 11 },
  { name: "Environment", value: 9 },
  { name: "Finance", value: 6 },
  { name: "Energy", value: 5 },
  { name: "Government", value: 3 },
];

describe("SectorRose", () => {
  it("renders all sectors", () => {
    render(<SectorRose data={SECTORS} />);
    expect(screen.getByText("Economic")).toBeInTheDocument();
    expect(screen.getByText("Military")).toBeInTheDocument();
    expect(screen.getByText("Governance")).toBeInTheDocument();
  });

  it("renders all 13 sectors", () => {
    render(<SectorRose data={SECTORS} />);
    expect(screen.getAllByText(/./)).toBeTruthy();
    // All 13 sector names should appear
    for (const s of SECTORS) {
      expect(screen.getByText(s.name)).toBeInTheDocument();
    }
  });
});
