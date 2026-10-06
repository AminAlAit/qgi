/**
 * Patterns ranking regression suite (#435 Bug 3 + #439).
 *
 * Locks the row-as-anchor refactor shipped in #435: every row in
 * /patterns/ranking must be an `<a href>`, not a `<button onClick>`,
 * so right-click / middle-click / cmd-click open in a new tab and
 * SEO crawlers see the link target.
 */
import { test, expect } from "@playwright/test";

test.describe("/patterns/ranking", () => {
  test("renders the leaderboard", async ({ page }) => {
    await page.goto("/patterns/ranking");
    // The header H1 is screen-reader-only; assert the ranking row count
    // instead. Wait up to 15s for the client-side fetch.
    await expect
      .poll(
        async () => await page.locator("a, button").filter({ hasText: /^#\d+/ }).count(),
        {
          timeout: 15_000,
        }
      )
      .toBeGreaterThan(10);
  });

  test("rows are <a href> elements (not buttons)", async ({ page }) => {
    await page.goto("/patterns/ranking");
    await page.waitForSelector('a[href*="/patterns?country_a"]', { timeout: 15_000 });
    // The first 5 rows must all be anchors with proper hrefs. This is
    // the regression check for #435 Bug 3 — the bug was that rows used
    // button onClick which broke right-click / middle-click / cmd-click.
    const anchors = page.locator('a[href*="/patterns?country_a"]');
    const count = await anchors.count();
    expect(count).toBeGreaterThan(5);
    const firstHref = await anchors.first().getAttribute("href");
    expect(firstHref).toMatch(
      /^\/patterns\?country_a=\d+&country_b=\d+&length=\d+&start_a=\d+&start_b=\d+$/
    );
  });

  test("filter chips persist + apply visually", async ({ page }) => {
    await page.goto("/patterns/ranking");
    await page.waitForSelector('a[href*="/patterns?country_a"]', { timeout: 15_000 });
    const before = await page.locator('a[href*="/patterns?country_a"]').count();
    // Click an S-tier chip — should narrow to S patterns only.
    const sChip = page.getByRole("button", { name: /^S$/ }).first();
    await sChip.click();
    // Wait a beat for the re-render.
    await page.waitForTimeout(500);
    const after = await page.locator('a[href*="/patterns?country_a"]').count();
    // S tier is a strict subset of the universe, so the count must shrink.
    expect(after).toBeLessThan(before);
    expect(after).toBeGreaterThan(0);
  });
});
