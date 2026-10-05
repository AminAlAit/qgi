/**
 * Synthetic monitoring smoke (#443 Part B).
 *
 * Runs against PRODUCTION (qgintelligence.com) every 15 minutes via
 * .github/workflows/synthetic.yml. Verifies the critical user flows
 * are still rendering — the gap CI can't see because CI tests preview
 * deployments, not prod.
 *
 * Designed to be tiny and tolerant: 5 assertions, generous timeouts,
 * no DOM-detail probes (those belong in the regular E2E suite). When
 * this fails, prod is broken in a way users will notice.
 *
 * Failure surfaces as a red workflow run; GitHub default email
 * notifications page Amin within minutes. Future #443 follow-up wires
 * Sentry + Slack / SES.
 */
import { test, expect } from "@playwright/test";

const PROD = process.env.PLAYWRIGHT_BASE_URL ?? "https://qgintelligence.com";

test.describe("synthetic prod smoke", () => {
  test("landing renders the hero", async ({ page }) => {
    const res = await page.goto(PROD, { waitUntil: "domcontentloaded" });
    expect(res?.status()).toBe(200);
    // The hero contains "Quantitative" + "Geopolitical" + "Intelligence" as
    // its h1. Match on text the marketing copy is unlikely to drop in a
    // routine cycle but a hero-blank-out would clearly miss.
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByText(/Quantitative/i).first()).toBeVisible();
  });

  test("/countries lists countries", async ({ page }) => {
    const res = await page.goto(`${PROD}/countries`, {
      waitUntil: "domcontentloaded",
    });
    expect(res?.status()).toBe(200);
    // The "View profile" footer button appears on every country card; counting
    // it is a quick proxy for "the card grid actually rendered."
    const cards = page.locator("text=View profile");
    await expect
      .poll(async () => await cards.count(), { timeout: 15_000 })
      .toBeGreaterThan(20);
  });

  test("country profile loads (Syria)", async ({ page }) => {
    const res = await page.goto(`${PROD}/countries/217`, {
      waitUntil: "domcontentloaded",
    });
    expect(res?.status()).toBe(200);
    await expect(page.getByRole("heading", { level: 1, name: /Syria/i })).toBeVisible();
  });

  test("/api/health returns 200", async ({ request }) => {
    const res = await request.get(`${PROD}/api/health`);
    expect(res.status()).toBe(200);
  });

  test("/api/country-risks returns a populated payload", async ({ request }) => {
    const res = await request.get(`${PROD}/api/country-risks`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    // Don't pin to a specific number; just verify the dict isn't empty.
    expect(Object.keys(body.countries ?? {}).length).toBeGreaterThan(20);
  });
});
