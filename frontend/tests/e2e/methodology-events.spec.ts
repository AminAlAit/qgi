/**
 * #738 item 3 regression guard (2026-05-16) — WCAG 1.3.1 + 4.1.2
 * compliance for the methodology Events table filter bar.
 *
 * Pre-fix: the 5 filter inputs/selects (search, country, category, year
 * min, year max) on /methodology/events relied on `placeholder` text +
 * `aria-label` only. Placeholder is not a programmatic label (1.3.1).
 * aria-label satisfies 4.1.2 but loses the click-target benefit of a
 * real `<label>` association.
 *
 * Post-fix (PR #83): each input has an explicit visually-hidden
 * `<label htmlFor="events-{slug}">` paired with `id="events-{slug}"`.
 * The label is the canonical accessible name; placeholder remains as
 * the visible hint.
 *
 * Test: load the page, then for each known filter id, assert (a) the
 * input exists, (b) a matching <label[for=id]> exists, (c) the label
 * text is non-empty.
 */
import { test, expect } from "@playwright/test";

const FILTERS: Array<{ id: string; expectedLabel: RegExp }> = [
  { id: "events-search", expectedLabel: /search event titles/i },
  { id: "events-country", expectedLabel: /filter by country/i },
  { id: "events-category", expectedLabel: /filter by category/i },
  { id: "events-year-min", expectedLabel: /earliest year/i },
  { id: "events-year-max", expectedLabel: /latest year/i },
];

test.describe("methodology/events filter labels (#738 item 3, WCAG 1.3.1 + 4.1.2)", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/methodology/events");
    // EventsTable lazy-imports a 2.4MB JSON; wait for the filter bar
    // to render before assertions. The Reset button is the last item in
    // the filter bar's flex container, so its appearance signals the
    // filter UI is fully mounted.
    await expect(page.getByRole("button", { name: /^reset$/i })).toBeVisible();
  });

  for (const { id, expectedLabel } of FILTERS) {
    test(`input #${id} has associated <label> with text matching ${expectedLabel}`, async ({
      page,
    }) => {
      // (a) Input exists.
      const input = page.locator(`#${id}`);
      await expect(input).toHaveCount(1);

      // (a.1) `aria-label` MUST be absent — double-naming
      //       (label + aria-label) causes aria-label to win precedence
      //       per accname-1.2 §4.3, which silently negates the <label>
      //       association we just established. This negative assertion
      //       pins the regression path.
      await expect(input).not.toHaveAttribute("aria-label", /.+/);

      // (b) <label for="..."> exists pointing at the input.
      const label = page.locator(`label[for="${id}"]`);
      await expect(label).toHaveCount(1);

      // (c) Label text is non-empty and matches the expected accessible
      //     name (also pins the label-text shape so it can't drift to
      //     something useless like "Filter" or "" in a future refactor).
      await expect(label).toHaveText(expectedLabel);
    });
  }

  test("filter labels are visually hidden (sr-only) but in the DOM/AT tree", async ({
    page,
  }) => {
    // sr-only utility renders width:1px / height:1px / clip-rect — not
    // visible to sighted users but present in the accessibility tree.
    // toBeAttached() pins "is in the DOM" (distinguishes from
    // display:none which would also pass not.toBeVisible());
    // toBeVisible() is checked separately to confirm the sr-only
    // visual-hiding is still in effect.
    for (const { id } of FILTERS) {
      const label = page.locator(`label[for="${id}"]`);
      await expect(label).toBeAttached();
      await expect(label).not.toBeVisible();
    }
  });
});
