/**
 * #426 regression guard + #426 happy-path neighborhood coverage.
 *
 * Bug that was fixed (#426):
 *   - /countries/syria rendered a 200 placeholder titled "Country #syria"
 *     (input reflected into title); /countries/217/nonexistent_category
 *     fabricated a HIGH-tier page.
 *
 * Tests:
 *   1. Numeric ID still works (happy path neighborhood)
 *   2. Slug redirects to canonical numeric URL (new behavior)
 *   3. Alpha-2 code redirects to canonical numeric URL (new behavior)
 *   4. Unknown slug produces a real 404 (not a reflected-input placeholder)
 *   5. Valid category renders (happy path neighborhood)
 *   6. Invalid category returns 404 (fixes the confabulation vector)
 */
import { test, expect } from "@playwright/test";

test.describe("country slug routing (#426)", () => {
  test("numeric id /countries/217 renders Syria profile", async ({ page }) => {
    const res = await page.goto("/countries/217");
    expect(res?.status()).toBeLessThan(400);
    await expect(page).toHaveTitle(/Syria/i);
  });

  test("slug /countries/syria redirects to /countries/217", async ({ page }) => {
    const res = await page.goto("/countries/syria");
    expect(res?.status()).toBeLessThan(400);
    await expect(page).toHaveURL(/\/countries\/\d+/);
    await expect(page).toHaveTitle(/Syria/i);
  });

  test("alpha-2 code /countries/SY redirects to numeric", async ({ page }) => {
    const res = await page.goto("/countries/SY");
    expect(res?.status()).toBeLessThan(400);
    await expect(page).toHaveURL(/\/countries\/\d+/);
  });

  test("hyphenated slug /countries/cape-verde — no slug echo in title", async ({
    page,
  }) => {
    // Cape Verde isn't in the V1.9.1 89-country dataset, so it should
    // 404. The original #426 bug was rendering a 200 with the slug
    // reflected into the title; that's what this test guards against.
    //
    // Note on status assertion: Next 16 surfaces a 200 to `page.goto()`
    // even when the route called `notFound()` (the not-found page is
    // rendered via the same lifecycle as a real page). We assert on the
    // SHAPE of the rendered page instead — a real country profile would
    // have its name in the title; the not-found page won't.
    await page.goto("/countries/cape-verde");
    const url = page.url();
    const title = await page.title();
    if (url.match(/\/countries\/\d+/)) {
      // Success: redirected to numeric ID — must reflect a real country
      expect(title).toMatch(/cape verde/i);
    }
    // The pre-#426 bug: slug literally appeared in the title
    expect(title).not.toContain("cape-verde");
    expect(title).not.toContain("cape_verde");
    expect(title).not.toContain("Country #cape-verde");
  });

  test("unknown slug /countries/zzznonexistent — no fabricated profile", async ({
    page,
  }) => {
    // Same shape-rather-than-status check as above (Next 16 returns 200
    // for notFound() pages via page.goto). The real assertion: the page
    // must NOT render a country profile placeholder titled with the slug.
    await page.goto("/countries/zzznonexistent");
    const title = await page.title();
    expect(title).not.toContain("zzznonexistent");
    expect(title).not.toContain("Country #zzznonexistent");
    // Page body should NOT contain the country-profile-specific
    // "Pattern depth" or "L1 vs World Median" markers — those only
    // appear on real country profiles.
    const bodyText = await page.locator("body").innerText();
    expect(bodyText).not.toMatch(/L1 vs World Median/);
    expect(bodyText).not.toMatch(/Pattern depth:/);
  });

  test("valid category /countries/217/civil_war_and_insurgency renders", async ({
    page,
  }) => {
    const res = await page.goto("/countries/217/civil_war_and_insurgency");
    expect(res?.status()).toBeLessThan(400);
    await expect(page).toHaveTitle(/Syria/i);
    await expect(page).toHaveTitle(/Civil War/i);
  });

  test("invalid category /countries/217/nonexistent_category — no fabricated tier page", async ({
    page,
  }) => {
    // #426: bad category previously rendered a fabricated HIGH-tier page.
    // Same status-vs-shape adaptation as above — Next 16 doesn't surface
    // 404 to `page.goto()` for `notFound()` calls, so we assert shape.
    // The fabricated page (pre-#426) had "Syria" in the title AND
    // "Nonexistent Category" in the title (formatted from the slug).
    await page.goto("/countries/217/nonexistent_category");
    const title = await page.title();
    // The fabricated page reflected both pieces. The not-found page
    // will have neither.
    const titleHadFabrication = /Syria/i.test(title) && /Nonexistent/i.test(title);
    expect(titleHadFabrication).toBe(false);
    // And the slug must not appear verbatim either
    expect(title).not.toContain("nonexistent_category");
  });
});
