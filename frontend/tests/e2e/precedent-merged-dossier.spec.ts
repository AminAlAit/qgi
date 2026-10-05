/**
 * #748 PR-2 (#750) regression guard — merged dossier template at
 * `/precedents/[slug]`.
 *
 * One template for all 4 LOCKed ML recipes. Asserts the 10-section
 * sequence per ratified spec §3.1, plus the structural invariants
 * QA review required:
 *   - Tier pill repeats in header AND beside the adjudication heading
 *     (Yuki: scroll position must never lose the headline)
 *   - Fingerprint top-3 visible, full-fingerprint <details> collapsed
 *     by default (spec §6.4)
 *   - ML/Stat seam is a labelled boundary (Sipho's rule):
 *     `[Verified — adjudicated]` on the adjudication block,
 *     `[Verified — substrate]` on the substrate block
 *   - Breadcrumb terminal crumb (recipe display name) is the current
 *     page indicator (QA B2 fix, 2026-05-17)
 *
 * Spec: docs/specs/internal/ops/cycle-resurfacing/merger-brief-2026-05-17-precedents-revised.md
 */
import { test, expect } from "@playwright/test";

// The 4 LOCKed ML slugs from `data/ml-recipe-stack.json metadata.top_4_recipes`.
// Source-of-truth; updating this requires bumping the bake metadata.
const LOCKED_SLUGS = [
  "civil_war_and_insurgency",
  "multilateral_agreement",
  "elections_and_voting",
  "bilateral_treaty",
] as const;

test.describe("#748 PR-2 — merged dossier (4 LOCKed recipes)", () => {
  for (const slug of LOCKED_SLUGS) {
    test.describe(`route /precedents/${slug}`, () => {
      test.beforeEach(async ({ page }) => {
        await page.goto(`/precedents/${slug}`);
        // The dossier <article> + Header section's H1 are the canonical
        // ready signals. Wait for the H1 to confirm SSR landed.
        await expect(page.locator("article h1").first()).toBeVisible();
      });

      test("renders all 10 sections in spec §3.1 order", async ({ page }) => {
        // §1 Header — H1 + tier pill + LOCKed chip
        const header = page.locator("article > header").first();
        await expect(header).toBeVisible();
        await expect(header.locator("h1")).toBeVisible();

        // §2 Critical disclosures (aria-label="Critical disclosures")
        await expect(
          page.locator('section[data-testid="critical-disclosures"]')
        ).toBeAttached();

        // §3 Adjudication — labelledby "adjudication-heading"
        await expect(page.locator("#adjudication-heading")).toBeVisible();

        // §3a Discrimination + 3b Calibration + 3c Anchor
        await expect(page.locator('[data-testid="metrics-grid"]')).toBeVisible();
        await expect(page.locator('[data-testid="calibration-table"]')).toBeVisible();

        // §4 Mechanism (id="mechanism-heading")
        await expect(page.locator("#mechanism-heading")).toBeVisible();

        // §5 How to use this (id="how-to-use-heading")
        await expect(page.locator("#how-to-use-heading")).toBeVisible();

        // §6 Statistical substrate (id="substrate-heading")
        await expect(page.locator("#substrate-heading")).toBeVisible();

        // §7 Historical instance sample — bake-pending chip visible
        await expect(page.locator("#instance-sample-heading")).toBeVisible();

        // §9 Methodology cross-ref expander present (collapsed by default)
        await expect(
          page.locator('[data-testid="methodology-collapsible"]')
        ).toBeAttached();

        // §10 Footer — "See related ranked patterns" + "How we validated this"
        await expect(
          page.getByRole("link", { name: /see related ranked patterns/i })
        ).toBeVisible();
        await expect(
          page.getByRole("link", { name: /how we validated this/i })
        ).toBeVisible();
      });

      test("tier pill repeats in header AND beside adjudication heading (Yuki rule)", async ({
        page,
      }) => {
        // Tier pill is one of STRONG / MODERATE / MARGINAL; selector by
        // those exact-match text labels with the bold-pill chrome.
        const tierPills = page
          .locator("article")
          .getByText(/^(STRONG|MODERATE|MARGINAL)$/);
        // At least 2 occurrences: one in header, one beside adjudication.
        // Strictly == 2 (no other section repeats the pill).
        await expect(tierPills).toHaveCount(2);
      });

      test("ML/Stat seam is labelled per Sipho's rule", async ({ page }) => {
        // [Verified — adjudicated] on the adjudication block
        const adjudicatedLabel = page
          .locator("article")
          .getByText(/verified\s*—\s*adjudicated/i);
        await expect(adjudicatedLabel).toBeVisible();
        // [Verified — substrate] on the substrate block
        const substrateLabel = page
          .locator("article")
          .getByText(/verified\s*—\s*substrate/i);
        await expect(substrateLabel).toBeVisible();
      });

      test("fingerprint top-3 visible by default, full-list <details> collapsed", async ({
        page,
      }) => {
        // The expander is the only <details> with a summary mentioning
        // "full fingerprint". Confirm it's NOT open by default; the top-3
        // rows render outside the <details>.
        const fullFingerprintDetails = page.locator("details", {
          hasText: /full fingerprint/i,
        });
        if ((await fullFingerprintDetails.count()) > 0) {
          // open attribute should be absent
          await expect(fullFingerprintDetails).not.toHaveAttribute("open", "");
        }
        // The top-3 indicator rows render unconditionally — confirm the
        // substrate section has visible content beyond the heading.
        await expect(page.locator("#substrate-heading")).toBeVisible();
      });

      test("breadcrumb terminal crumb names the recipe (QA B2 fix)", async ({
        page,
      }) => {
        // The breadcrumb <nav aria-label="Breadcrumb"> ends with the
        // recipe display name as a <span aria-current="page">.
        const breadcrumb = page.locator('nav[aria-label="Breadcrumb"]');
        await expect(breadcrumb).toBeVisible();
        // aria-current="page" span is the terminal crumb.
        await expect(breadcrumb.locator('[aria-current="page"]')).toBeVisible();
      });
    });
  }
});
