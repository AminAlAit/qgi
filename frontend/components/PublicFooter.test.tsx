import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PublicFooter } from "./PublicFooter";

describe("PublicFooter", () => {
  it("renders all 7 nav links in the IA-ratified order (About, Methodology, Reports, Blog, Contact, Privacy, Terms)", () => {
    const { container } = render(<PublicFooter />);
    const navLabels = Array.from(container.querySelectorAll("nav a"))
      .map((el) => el.textContent?.trim())
      .filter((t): t is string => Boolean(t));
    expect(navLabels).toEqual([
      "About",
      "Methodology",
      "Reports",
      "Blog",
      "Contact",
      "Privacy",
      "Terms",
    ]);
  });

  it("renders copyright + tagline", () => {
    render(<PublicFooter />);
    expect(screen.getByText(/2026 QG Intelligence/i)).toBeInTheDocument();
    expect(screen.getByText(/Pattern Recurrence Intelligence/i)).toBeInTheDocument();
  });

  it("contact link points to /contact (fill-in form)", () => {
    const { container } = render(<PublicFooter />);
    const contact = Array.from(container.querySelectorAll("nav a")).find(
      (el) => el.textContent?.trim() === "Contact"
    );
    expect(contact).toBeTruthy();
    expect(contact?.getAttribute("href")).toBe("/contact");
  });

  it("footer nav has an aria-label", () => {
    const { container } = render(<PublicFooter />);
    const nav = container.querySelector("nav");
    expect(nav?.getAttribute("aria-label")).toBe("Footer");
  });
});
