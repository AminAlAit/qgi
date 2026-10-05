/**
 * API endpoint contract tests (#425 + #439).
 *
 * **Scope:** ONLY endpoints that work without AWS credentials. CI runs
 * `npm run dev` with no Athena credentials, so endpoints that reach
 * out to live Athena will 500. Those endpoints are covered by
 * `tests/e2e/synthetic/smoke.spec.ts` which runs against prod.
 *
 * Locked here:
 *   - /api/health             (static)
 *   - /api/country-risks      (reads baked data/country-risks.json)
 *
 * Out of scope (live in synthetic/):
 *   - /api/recipes/country    (Athena live)
 *   - /api/patterns/lengths   (Athena live)
 *   - /api/patterns/years     (Athena live)
 *   - /api/scdis              (Athena live)
 *   - /api/patterns/detail    (Athena live)
 */
import { test, expect } from "@playwright/test";

test.describe("API health (data-independent)", () => {
  test("/api/health returns 200", async ({ request }) => {
    const res = await request.get("/api/health");
    expect(res.status()).toBe(200);
  });

  test("/api/country-risks returns a populated countries dict", async ({ request }) => {
    const res = await request.get("/api/country-risks");
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(Object.keys(body.countries ?? {}).length).toBeGreaterThan(20);
    // Locked by #431 — the version field is the source of truth for
    // the dashboard scoring label.
    expect(body.version).toMatch(/^V\d+\.\d+(\.\d+)?$/);
  });
});
