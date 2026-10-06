/**
 * #741 PR-a regression guard (2026-05-16) — WCAG 1.3.1 + 4.1.2 for
 * V3 merged-list filter components.
 *
 * Each route's filter strip has a search <input> + (where present) a
 * sort <select>. Pre-fix these used placeholder + (sometimes) aria-label
 * only. Post-fix they all have:
 *   - <label htmlFor="{slug}"> immediately before the control
 *   - matching id="{slug}" on the control
 *   - NO aria-label (accname-1.2 §4.3: double-naming makes aria-label
 *     win and silently negates the <label> association)
 *
 * Mirrors `tests/e2e/methodology-events.spec.ts` (PR #83, the
 * canonical template for this pattern).
 *
 * Five routes covered:
 *   /precedents          components/precedents/PrecedentsMergedListClient
 *   /countries           components/countries/CountriesMergedListClient
 *   /patterns            components/patterns/PatternsMergedListClient
 *   /signals             components/signals/SignalsMergedListClient
 *   /signals/[country]   components/signals/SignalsCountryDetail
 */
import { test, expect } from "@playwright/test";

type Filter = { id: string; expectedLabel: RegExp };
type Route = { path: string; readyLocator: string; filters: Filter[] };

const ROUTES: Route[] = [
  {
    path: "/precedents",
    // #748 PR-1 (2026-05-17) — page now ships 4 LOCKed ML rows with no
    // sort dropdown (column-header click sort) and a more generic
    // "Search precedents" label. The `precedents-merged-sort` <select>
    // and its sr-only label were removed; the search label changed from
    // "Search categories or domains" to "Search precedents".
    readyLocator: "#precedents-merged-search",
    filters: [{ id: "precedents-merged-search", expectedLabel: /search precedents/i }],
  },
  {
    path: "/countries",
    readyLocator: "#countries-merged-search",
    filters: [
      { id: "countries-merged-search", expectedLabel: /search country/i },
      { id: "countries-merged-sort", expectedLabel: /^sort$/i },
    ],
  },
  {
    path: "/patterns",
    readyLocator: "#patterns-merged-search",
    filters: [
      { id: "patterns-merged-search", expectedLabel: /search country pair/i },
      { id: "patterns-merged-sort", expectedLabel: /^sort$/i },
      { id: "patterns-merged-country-search", expectedLabel: /search countries/i },
    ],
  },
  {
    path: "/signals",
    readyLocator: "#signals-merged-search",
    filters: [
      { id: "signals-merged-search", expectedLabel: /search category or l1 domain/i },
      { id: "signals-merged-sort", expectedLabel: /^sort$/i },
    ],
  },
  {
    // SignalsCountryDetail needs a country slug. Pick a stable one that
    // has signals — France (250) is reliably populated in every bake.
    path: "/signals/france",
    readyLocator: "#signals-country-detail-search",
    filters: [
      {
        id: "signals-country-detail-search",
        expectedLabel: /search category or l1 domain/i,
      },
      { id: "signals-country-detail-sort", expectedLabel: /^sort$/i },
    ],
  },
];

test.describe("#741 PR-a — V3 merged filter labels (WCAG 1.3.1 + 4.1.2)", () => {
  for (const route of ROUTES) {
    test.describe(`route ${route.path}`, () => {
      test.beforeEach(async ({ page }) => {
        await page.goto(route.path);
        // Wait for the filter strip to mount (the search input is the
        // canonical ready signal — every route ships it on first paint).
        await expect(page.locator(route.readyLocator)).toBeAttached();
      });

      for (const { id, expectedLabel } of route.filters) {
        test(`input/select #${id} has associated <label> matching ${expectedLabel}`, async ({
          page,
        }) => {
          const control = page.locator(`#${id}`);
          await expect(control).toHaveCount(1);

          // (a.1) aria-label MUST be absent (accname-1.2 §4.3 precedence).
          await expect(control).not.toHaveAttribute("aria-label", /.+/);

          // (b) <label for="..."> exists and points at the control.
          const label = page.locator(`label[for="${id}"]`);
          await expect(label).toHaveCount(1);

          // (c) Label text matches the expected accessible name.
          await expect(label).toHaveText(expectedLabel);

          // (d) Label is in the DOM (toBeAttached); visibility varies —
          //     some labels are sr-only, some (the "Sort" labels) are
          //     intentionally visible. Don't assert visibility here.
          await expect(label).toBeAttached();
        });
      }
    });
  }
});
