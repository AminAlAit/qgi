import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Sidebar } from "./Sidebar";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
}));

describe("Sidebar", () => {
  it("renders the QG Intelligence wordmark", () => {
    // Wordmark is two spans: "QG" + "Intelligence" — matches the domain
    // qgintelligence.com (ref #245). Older test checked a single "QGI"
    // string that hasn't existed since the wordmark was split.
    render(<Sidebar />);
    expect(screen.getByText("QG")).toBeInTheDocument();
    expect(screen.getByText("Intelligence")).toBeInTheDocument();
  });

  it("renders the 7 canonical V4.1 entries", () => {
    render(<Sidebar />);
    // 2026-05-29: Recipe Tracker route deleted (folded into /trends).
    // 2026-05-30: Compound Risk route taken down (308 → /risk-board).
    // Will rejuvenate as compound-negative-event-density per Stats trio.
    // Top slot label is "Briefing" (route still /dashboard); the
    // "Dashboard" copy was renamed to "Briefing" — see NAV_STRUCTURE.
    expect(screen.getByText("Briefing")).toBeInTheDocument();
    // 2026-06-04: "Recipes" nav label renamed to "Trends" (route /trends).
    expect(screen.getByText("Trends")).toBeInTheDocument();
    expect(screen.getByText("Countries")).toBeInTheDocument();
    expect(screen.getByText("Risk Board")).toBeInTheDocument();
    expect(screen.getByText("Compare")).toBeInTheDocument();
    expect(screen.getByText("Analogues")).toBeInTheDocument();
    // 2026-06-05: "Patterns" retired (replaced by Analogues); nav entry removed.
    expect(screen.queryByText("Patterns")).not.toBeInTheDocument();
    expect(screen.queryByText("Nearest Analog")).not.toBeInTheDocument();
    expect(screen.queryByText("Recipe Tracker")).not.toBeInTheDocument();
    expect(screen.queryByText("Compound Risk")).not.toBeInTheDocument();
  });

  it("does NOT render any legacy or removed entries", () => {
    render(<Sidebar />);
    const removed = [
      // Removed V3 entries
      "Signals",
      // Old V4.1 label suffixes
      "Dashboard V4.1",
      "Recipes V4.1",
      "Countries V4.1",
      "Patterns V4",
      // TE Mockup group header
      "TE Mockup (local)",
      // Old V1/V2 sub-entries
      "Country browser",
      "Recipe catalogue",
      "Active signals",
      "Pattern atlas",
      "Power ranking",
    ];
    for (const label of removed) {
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    }
  });

  it("renders no LIVE or PREVIEW chips (all entries are PRIMARY, no chip rendered)", () => {
    render(<Sidebar />);
    // NavLeafLink does not render the badge chip in the current implementation.
    expect(screen.queryByText("LIVE")).not.toBeInTheDocument();
    expect(screen.queryByText("PREVIEW")).not.toBeInTheDocument();
    expect(screen.queryByText("PRIMARY")).not.toBeInTheDocument();
  });
});
