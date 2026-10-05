/**
 * Blog index + post regression suite (#433 Article JSON-LD + #439).
 *
 * Verifies:
 *   - /blog renders the post list with proper anchors
 *   - Each post page loads and emits the Article JSON-LD schema
 *     (#433: Google rich-card eligibility)
 *   - The home → /blog → post navigation chain is clickable
 */
import { test, expect } from "@playwright/test";

test.describe("/blog", () => {
  test("blog index lists posts as <a> elements", async ({ page }) => {
    await page.goto("/blog");
    // Each post link is an <a href="/blog/...">.
    const postLinks = page.locator('a[href^="/blog/"]');
    const count = await postLinks.count();
    expect(count).toBeGreaterThanOrEqual(3);
    const first = await postLinks.first().getAttribute("href");
    expect(first).toMatch(/^\/blog\/[a-z0-9-]+$/);
  });

  test("a blog post renders with Article JSON-LD schema", async ({ page }) => {
    await page.goto("/blog");
    const firstPostLink = page
      .locator('a[href^="/blog/"]')
      .filter({ has: page.locator("h2") })
      .first();
    const href = await firstPostLink.getAttribute("href");
    expect(href).toBeTruthy();
    await firstPostLink.click();
    await expect(page).toHaveURL(/\/blog\/[a-z0-9-]+/);
    // Article schema (added in #433) is embedded as <script type="application/ld+json">.
    // Inspect ALL JSON-LD scripts on the page — the root layout injects an
    // Organization schema before the Article one, so .first() would find
    // Organization, not what we're testing for. Aggregate every script's
    // @type and assert "Article" appears in the union.
    const scripts = page.locator('script[type="application/ld+json"]');
    const count = await scripts.count();
    expect(count).toBeGreaterThan(0);
    const types: string[] = [];
    for (let i = 0; i < count; i++) {
      const content = await scripts.nth(i).textContent();
      if (!content) continue;
      try {
        const payload = JSON.parse(content);
        if (Array.isArray(payload)) {
          for (const p of payload) types.push(p["@type"]);
        } else {
          types.push(payload["@type"]);
        }
      } catch {
        // Skip malformed JSON-LD blocks (shouldn't happen but defensive)
      }
    }
    expect(types).toContain("Article");
  });
});
