import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PublicNav } from "./PublicNav";

describe("PublicNav", () => {
  it("renders all 5 content links + Open Dashboard CTA", () => {
    render(<PublicNav />);
    expect(screen.getAllByText("Reports").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Blog").length).toBeGreaterThan(0);
    expect(screen.getByText("Methodology")).toBeInTheDocument();
    expect(screen.getByText("About")).toBeInTheDocument();
    expect(screen.getAllByText("Contact").length).toBeGreaterThan(0);
    expect(screen.getByText("Open Dashboard")).toBeInTheDocument();
  });

  it("renders the desktop nav order ratified by Sunita 2026-05-23 (Reports, Blog, Methodology, About, Contact, Open Dashboard)", () => {
    const { container } = render(<PublicNav />);
    // Pull desktop-visible link labels in document order. The mobile dropdown
    // is hidden until the hamburger fires, so only the top-row links count.
    const desktopLabels = Array.from(container.querySelectorAll("nav > a, nav > button"))
      .map((el) => el.textContent?.trim())
      .filter((t): t is string => Boolean(t) && t !== "");
    // First 6 entries should be the nav vocabulary in the ratified order.
    // The hamburger button is also in this list at the end; ignore it via
    // length check.
    expect(desktopLabels.slice(0, 6)).toEqual([
      "Reports",
      "Blog",
      "Methodology",
      "About",
      "Contact",
      "Open Dashboard",
    ]);
  });

  it("highlights currentPage in accent color, leaves siblings muted", () => {
    render(<PublicNav currentPage="about" />);
    const aboutLink = screen.getByText("About");
    // currentPage gets var(--qgi-accent); others get var(--qgi-text-muted).
    expect(aboutLink.getAttribute("style")).toContain("var(--qgi-accent)");
    const methodologyLink = screen.getByText("Methodology");
    expect(methodologyLink.getAttribute("style")).toContain("var(--qgi-text-muted)");
  });

  it("renders a hamburger button labeled Open menu initially", () => {
    render(<PublicNav />);
    const btn = screen.getByRole("button", { name: /open menu/i });
    expect(btn).toBeInTheDocument();
    expect(btn).toHaveAttribute("aria-expanded", "false");
    expect(btn).toHaveAttribute("aria-controls", "public-mobile-menu");
  });

  it("toggles aria-expanded and reveals mobile drawer when clicked", () => {
    render(<PublicNav />);
    const btn = screen.getByRole("button", { name: /open menu/i });
    expect(screen.queryByRole("button", { name: /close menu/i })).toBeNull();

    fireEvent.click(btn);

    const closeBtn = screen.getByRole("button", { name: /close menu/i });
    expect(closeBtn).toHaveAttribute("aria-expanded", "true");

    // Reports + Blog + Contact now appear TWICE each (desktop inline + mobile drawer).
    expect(screen.getAllByText("Reports").length).toBe(2);
    expect(screen.getAllByText("Blog").length).toBe(2);
    expect(screen.getAllByText("Contact").length).toBe(2);
  });

  it("closes drawer when a drawer link is clicked", () => {
    render(<PublicNav />);
    fireEvent.click(screen.getByRole("button", { name: /open menu/i }));
    expect(screen.getAllByText("Reports").length).toBe(2);

    const reportsLinks = screen.getAllByText("Reports");
    fireEvent.click(reportsLinks[1]);

    expect(screen.getAllByText("Reports").length).toBe(1);
  });
});
