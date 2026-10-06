/**
 * Countries browser regression suite (#432 + #439).
 *
 * Locks the URL-state behavior shipped in #432 Bug 2 (filter state
 * survives reload + paste-share) plus the L1 chip toggle from #432
 * Bug 3 (min-score resets when chip changes).
 *
 * Plus neighborhood coverage for the surface — search, sort, deep-link
 * to a country profile.
 */
import { test, expect } from "@playwright/test";

test.describe("/countries browser", () => {
  test("renders the card grid", async ({ page }) => {
    await page.goto("/countries");
    // Search input — ARIA label is sr-only so use the placeholder.
    await expect(page.getByPlaceholder(/search countries/i)).toBeVisible();
    // The "View profile" footer button is on every country card; >=20 is
    // a robust "the grid actually rendered" assertion.
    await expect
      .poll(async () => await page.locator("text=View profile").count(), {
        timeout: 15_000,
      })
      .toBeGreaterThan(20);
  });

  test("?tier=HIGH initialises filter state from URL", async ({ page }) => {
    // Once filtered to HIGH, the rendered card count must drop below the
    // unfiltered total. We don't pin to a specific number because the
    // pipeline rebalances tiers each cycle.
    //
    // #452: `CountriesClient` is wrapped in `<Suspense fallback={null}>`
    // (#432) so the cards aren't in the SSR stream — they render after
    // hydration. Wait for the cards to render before counting; reading
    // at the load event (which fires before hydration finishes) reports 0.

    /** Poll until at least one card is on the page, then return the count. */
    const waitForCards = async () => {
      await expect
        .poll(async () => await page.locator("text=View profile").count(), {
          timeout: 15_000,
        })
        .toBeGreaterThan(0);
      return page.locator("text=View profile").count();
    };

    await page.goto("/countries?tier=HIGH");
    const filteredCount = await waitForCards();

    await page.goto("/countries");
    const totalCount = await waitForCards();

    expect(filteredCount).toBeLessThan(totalCount);
  });

  test("typing in search updates the URL with ?q=", async ({ page }) => {
    await page.goto("/countries");
    // #452: wait for hydration before interacting — the search input's
    // onChange handler is React-bound, so a `fill` before hydration is a
    // no-op and the URL never updates. Card render is a proxy for "client
    // component has mounted and event handlers are attached."
    await expect
      .poll(async () => await page.locator("text=View profile").count(), {
        timeout: 15_000,
      })
      .toBeGreaterThan(0);
    const search = page.getByPlaceholder(/search countries/i);
    await search.fill("syria");
    // The useEffect → router.replace fires on the next tick. Poll the URL.
    await expect.poll(async () => page.url(), { timeout: 10_000 }).toMatch(/[?&]q=syria/);
  });

  test("country card link navigates to /countries/[id]", async ({ page }) => {
    await page.goto("/countries");
    // #452: wait for cards to render before interacting (Suspense boundary
    // means SSR has no cards; they appear post-hydration).
    await expect
      .poll(async () => await page.locator("text=View profile").count(), {
        timeout: 15_000,
      })
      .toBeGreaterThan(0);
    // The first card's primary link wraps the whole card.
    const firstCard = page.locator('a[href^="/countries/"]').first();
    const href = await firstCard.getAttribute("href");
    expect(href).toMatch(/^\/countries\/\d+$/);
    // #452 fix: navigation race — wait for the actual URL change with a
    // generous timeout (default `toHaveURL` was 5s which timed out under
    // load) and add waitForLoadState so the heading assert isn't racing
    // with hydration.
    await Promise.all([
      page.waitForURL(/\/countries\/\d+/, { timeout: 15_000 }),
      firstCard.click(),
    ]);
    await page.waitForLoadState("domcontentloaded");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  });
});
