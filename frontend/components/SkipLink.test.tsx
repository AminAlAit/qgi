import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SkipLink } from "./SkipLink";

describe("SkipLink", () => {
  it("renders an anchor pointing to #main-content by default", () => {
    render(<SkipLink />);
    const link = screen.getByText("Skip to content");
    expect(link).toBeInTheDocument();
    expect(link.getAttribute("href")).toBe("#main-content");
  });

  it("accepts a custom targetId", () => {
    render(<SkipLink targetId="custom-target" />);
    const link = screen.getByText("Skip to content");
    expect(link.getAttribute("href")).toBe("#custom-target");
  });

  it("starts visually hidden (sr-only) but focusable", () => {
    const { container } = render(<SkipLink />);
    const link = container.querySelector("a");
    expect(link?.className).toContain("sr-only");
    expect(link?.className).toContain("focus:not-sr-only");
  });
});
