import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RciBadge } from "./RciBadge";
import type { RecipeConfidenceEntry } from "@/lib/recipe-confidence";

const baseEntry: RecipeConfidenceEntry = {
  rci: 0.78,
  tier: "GREEN",
  auc_skill: 0.62,
  sample_factor: 1.0,
  mnar_factor: 1.0,
  test_auc: 0.81,
  auc_ci_low: 0.75,
  auc_ci_high: 0.86,
  n_total: 4231,
  n_pos: 187,
  n_mnar_flagged: 0,
  top_indicator: "v2x_polyarchy",
};

describe("RciBadge", () => {
  it("renders the High confidence label for GREEN tier", () => {
    render(<RciBadge entry={baseEntry} />);
    expect(screen.getByText("High confidence")).toBeInTheDocument();
  });

  it("renders the Moderate confidence label for YELLOW tier", () => {
    render(<RciBadge entry={{ ...baseEntry, tier: "YELLOW" }} />);
    expect(screen.getByText("Moderate confidence")).toBeInTheDocument();
  });

  it("renders the Low confidence label for RED tier", () => {
    render(<RciBadge entry={{ ...baseEntry, tier: "RED" }} />);
    expect(screen.getByText("Low confidence")).toBeInTheDocument();
  });

  it("renders the Insufficient data label for INSUFFICIENT tier", () => {
    render(<RciBadge entry={{ ...baseEntry, tier: "INSUFFICIENT" }} />);
    expect(screen.getByText("Insufficient data")).toBeInTheDocument();
  });

  it("returns null when entry is null or undefined", () => {
    const { container } = render(<RciBadge entry={null} />);
    expect(container.firstChild).toBeNull();
    const { container: c2 } = render(<RciBadge entry={undefined} />);
    expect(c2.firstChild).toBeNull();
  });

  it("includes the holdout AUC and CI in the tooltip when present", () => {
    render(<RciBadge entry={baseEntry} />);
    const badge = screen.getByText("High confidence");
    const tooltip = badge.getAttribute("title") ?? "";
    expect(tooltip).toContain("Holdout AUC 0.81");
    expect(tooltip).toContain("95% CI 0.75");
    expect(tooltip).toContain("0.86");
  });

  it("includes sample counts in the tooltip", () => {
    render(<RciBadge entry={baseEntry} />);
    const badge = screen.getByText("High confidence");
    const tooltip = badge.getAttribute("title") ?? "";
    expect(tooltip).toContain("4,231 samples");
    expect(tooltip).toContain("187 positive");
  });

  it("mentions missingness flag count when n_mnar_flagged > 0", () => {
    render(<RciBadge entry={{ ...baseEntry, n_mnar_flagged: 3 }} />);
    const badge = screen.getByText("High confidence");
    const tooltip = badge.getAttribute("title") ?? "";
    expect(tooltip).toContain("3 indicators flagged for missingness bias");
  });

  it("uses singular 'indicator' when n_mnar_flagged is 1", () => {
    render(<RciBadge entry={{ ...baseEntry, n_mnar_flagged: 1 }} />);
    const badge = screen.getByText("High confidence");
    const tooltip = badge.getAttribute("title") ?? "";
    expect(tooltip).toContain("1 indicator flagged for missingness bias");
    expect(tooltip).not.toContain("indicators flagged");
  });

  it("omits CI from tooltip when bounds are null", () => {
    render(<RciBadge entry={{ ...baseEntry, auc_ci_low: null, auc_ci_high: null }} />);
    const badge = screen.getByText("High confidence");
    const tooltip = badge.getAttribute("title") ?? "";
    expect(tooltip).toContain("Holdout AUC 0.81");
    expect(tooltip).not.toContain("95% CI");
  });

  it("does NOT expose the RCI numeric value or the formula in the tooltip (#482 vague-public)", () => {
    render(<RciBadge entry={baseEntry} />);
    const badge = screen.getByText("High confidence");
    const tooltip = badge.getAttribute("title") ?? "";
    // RCI value is 0.78 in baseEntry — must not appear verbatim
    expect(tooltip).not.toContain("0.78");
    expect(tooltip).not.toContain("RCI");
    expect(tooltip).not.toContain("formula");
    // Formula subcomponents must not leak
    expect(tooltip).not.toContain("auc_skill");
    expect(tooltip).not.toContain("sample_factor");
    expect(tooltip).not.toContain("mnar_factor");
  });

  it("applies different padding/font sizes for xs/sm/md", () => {
    const { rerender } = render(<RciBadge entry={baseEntry} size="xs" />);
    let badge = screen.getByText("High confidence");
    expect(badge.style.fontSize).toBe("9px");
    expect(badge.style.padding).toBe("1px 5px");

    rerender(<RciBadge entry={baseEntry} size="md" />);
    badge = screen.getByText("High confidence");
    expect(badge.style.fontSize).toBe("11px");
    expect(badge.style.padding).toBe("2px 6px");
  });
});
