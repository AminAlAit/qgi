import { describe, expect, it } from "vitest";
import { TOUR_STEPS, TOUR_STEPS_BY_PAGE, TOUR_TOTAL_STEPS } from "@/lib/tour-steps";

/**
 * Tour-steps shape invariants — caught at unit-test time so they don't
 * regress silently into production.
 *
 * 2026-05-28: V4.1 canonical promotion. The original 12 legacy steps
 * (covering /dashboard V3, /precedents, /patterns V3, /signals,
 * /countries V3) were removed because those routes are deleted.
 *
 * 2026-06-04: Anchor-correctness audit + Recipe→Trend rename.
 *   - /patterns/[slug] updated to "172-208" (real cascade data slug).
 *   - /dashboard: 4 dead anchors replaced; how-to-read-button step dropped
 *     (dashboard does not render HowToReadButton). Steps: 6→5.
 *   - /countries: cotw-tile step dropped. Steps: 5→4.
 *   - /trends/foreign_intervention: demo-disclosure step retargeted to the
 *     definition lede (cap-1/DefinitionPanel is not rendered on the page).
 *     Steps: 13→12.
 *   - /risk-board: how-to-read-button dropped + the hero-strip step dropped
 *     (the top-pairs strip moved to /dashboard). Steps: 5→3.
 *   - /compare: locked surface; backdrop panels are aria-hidden; reduced to
 *     h1 + compare-coming-soon. Steps: 6→2.
 *   - /patterns: re-anchored to the live search engine (filters + results);
 *     the old overview/ranking/family/country browse panels no longer render.
 *     Steps: 6→3.
 *   - /patterns/172-208: retargeted to real page anchors; how-to-read-button
 *     dropped. Steps: 7→4.
 */

/** Canonical pages covered by the post-V4.1-promo tour. */
const ALL_TOUR_PAGES = new Set([
  "/dashboard",
  "/trends",
  "/trends/foreign_intervention",
  "/countries",
  "/countries/sdn",
  "/risk-board",
  "/analogues",
  "/compare",
  "/patterns",
  "/patterns/172-208",
]);

/** Pages that render HowToReadButton (anchor: how-to-read-button). */
const PAGES_WITH_HOW_TO_READ = new Set([
  "/trends",
  "/trends/foreign_intervention",
  "/countries",
  "/countries/sdn",
  "/analogues",
]);

describe("TOUR_STEPS — shape invariants", () => {
  it("total step count matches declared constant", () => {
    expect(TOUR_TOTAL_STEPS).toBe(TOUR_STEPS.length);
  });

  it("every page in the tour has at least one step", () => {
    const pages = new Set(TOUR_STEPS.map((s) => s.page));
    for (const p of ALL_TOUR_PAGES) {
      expect(pages.has(p as never), `${p} must have at least one step`).toBe(true);
    }
  });

  it("every page's FIRST step is an (a) introduction (MANDATORY)", () => {
    for (const page of ALL_TOUR_PAGES) {
      const first = TOUR_STEPS.find((s) => s.page === page);
      expect(first, `${page} must have at least one step`).toBeDefined();
      expect(first!.dimension, `${page} first step must be (a)`).toBe("a");
    }
  });

  it("the FIRST step on every page anchors on the page's primary header", () => {
    for (const page of ALL_TOUR_PAGES) {
      const first = TOUR_STEPS.find((s) => s.page === page);
      if (!first) continue;
      const target = first.target as string;
      const valid =
        target === "h1" || target.startsWith('[data-tour="') || target === "header";
      expect(
        valid,
        `${page} first step target "${target}" must be h1 or a data-tour anchor`
      ).toBe(true);
    }
  });

  it("every step has content, target, title (non-empty)", () => {
    for (const s of TOUR_STEPS) {
      expect(s.target, `${s.page}/${s.dimension} target`).toBeTruthy();
      expect(s.content, `${s.page}/${s.dimension} content`).toBeTruthy();
      expect(s.title, `${s.page}/${s.dimension} title`).toBeTruthy();
    }
  });

  it("dimensions are one of a/b/c/d", () => {
    for (const s of TOUR_STEPS) {
      expect(["a", "b", "c", "d"]).toContain(s.dimension);
    }
  });

  it("no step references a deleted route", () => {
    const deletedRoutes = ["/precedents", "/signals", "/base", "/dashboard-v4"];
    for (const s of TOUR_STEPS) {
      for (const deleted of deletedRoutes) {
        expect(
          s.page.startsWith(deleted),
          `Step on page "${s.page}" references deleted route ${deleted}`
        ).toBe(false);
      }
    }
  });

  it("the /patterns detail page uses the real cascade slug 172-208", () => {
    const patternDetailSteps = TOUR_STEPS.filter((s) => s.page.startsWith("/patterns/"));
    expect(patternDetailSteps.length).toBeGreaterThan(0);
    for (const s of patternDetailSteps) {
      expect(s.page).toBe("/patterns/172-208");
    }
  });

  it("no step targets an anchor known to be absent (old broken anchors)", () => {
    // These anchors were confirmed absent in the 2026-06-04 audit.
    const removedAnchors = [
      "hero-tiles",
      "highlights-band",
      "surfaces-grid",
      "activity-timeline",
      "cotw-tile",
      "demo-disclosure",
      "compare-picker",
      "compare-matrix",
      "compare-drivers",
      "compare-at-a-glance",
      "generate-comparison-report-button",
    ];
    for (const s of TOUR_STEPS) {
      const t = s.target as string;
      for (const removed of removedAnchors) {
        expect(
          t.includes(removed),
          `Step on ${s.page} still targets removed anchor "${removed}"`
        ).toBe(false);
      }
    }
  });

  it("how-to-read-button steps only appear on pages that render HowToReadButton", () => {
    for (const s of TOUR_STEPS) {
      const t = s.target as string;
      if (t.includes("how-to-read-button")) {
        expect(
          PAGES_WITH_HOW_TO_READ.has(s.page),
          `${s.page} has a how-to-read-button step but does not render HowToReadButton`
        ).toBe(true);
      }
    }
  });

  it("TOUR_STEPS_BY_PAGE sums to TOUR_TOTAL_STEPS", () => {
    const sum = Object.values(TOUR_STEPS_BY_PAGE).reduce((a, b) => a + b, 0);
    expect(sum).toBe(TOUR_TOTAL_STEPS);
  });
});
