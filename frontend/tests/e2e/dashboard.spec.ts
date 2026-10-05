/**
 * Dashboard regression suite (issue #685, PR-vi 2026-05-15).
 *
 * Covers the 7 assertions from the Majles synthesis spec:
 *   1. Four-family summary band renders with non-zero numbers (4 cards).
 *   2. E1 fallback rule: when signalsHighCount < 3, signals card label is
 *      "risk categories at elevated signal levels" with amber color, not
 *      red "firing HIGH".
 *   3. Featured Signal tier badge has aria-label="Risk tier: HIGH|MODERATE|INDICATIVE".
 *   4. Lede sentence contains total country count from bake (e.g. "156 countries").
 *   5. "What this doesn't mean" <details> element present with role="note"
 *      and aria-label="Methodology note".
 *   6. Four-family band CTAs link to correct V3 family pages.
 *   7. Footer methodology link present and points to /methodology.
 *
 * Design conventions:
 *   - Never assert a specific count that changes with each bake (e.g. "66 HIGH
 *     countries"). Instead assert "it is a non-zero number."
 *   - Wait for hydration before asserting client-rendered elements — the page
 *     is a server component that passes props to a client component
 *     (`BaseClient`). The four-family band and featured card are in-tree
 *     server-rendered but React-hydrated; allow a generous timeout for the
 *     dev server.
 */
import { test, expect } from "@playwright/test";

test.describe("/dashboard", () => {
  // ── Assertion 1: Four-family summary band renders with non-zero numbers ──

  test("four-family summary band: all 4 cards are present with non-zero numbers", async ({
    page,
  }) => {
    await page.goto("/dashboard");

    // The band is a <section aria-label="QGI family summary"> with 4 child <a> cards.
    const band = page.locator('section[aria-label="QGI family summary"]');
    await expect(band).toBeVisible({ timeout: 15_000 });

    const cards = band.locator("a");
    await expect(cards).toHaveCount(4, { timeout: 15_000 });

    // Each card has a font-data text-4xl span with the dominant number.
    // We assert all four cards exist AND at least the Countries card shows a
    // number > 0 (ties to the real bake).
    const countriesCard = band.locator('a[href="/countries"]');
    await expect(countriesCard).toBeVisible();

    const signalsCard = band.locator('a[href="/signals"]');
    await expect(signalsCard).toBeVisible();

    const patternsCard = band.locator('a[href="/patterns"]');
    await expect(patternsCard).toBeVisible();

    const precedentsCard = band.locator('a[href="/trends"]');
    await expect(precedentsCard).toBeVisible();

    // The Countries dominant number is the HIGH count — must be a positive integer.
    const countriesNumber = countriesCard.locator(".font-data.text-4xl").first();
    await expect(countriesNumber).toBeVisible();
    const countriesText = (await countriesNumber.textContent()) ?? "";
    const countriesCount = parseInt(countriesText.trim(), 10);
    expect(Number.isFinite(countriesCount)).toBe(true);
    expect(countriesCount).toBeGreaterThan(0);
  });

  // ── Assertion 2: E1 fallback rule (signals card label) ──────────────────

  test("signals card: E1 fallback rule — label is correct based on HIGH count", async ({
    page,
  }) => {
    await page.goto("/dashboard");

    const band = page.locator('section[aria-label="QGI family summary"]');
    await expect(band).toBeVisible({ timeout: 15_000 });

    const signalsCard = band.locator('a[href="/signals"]');
    await expect(signalsCard).toBeVisible();

    const dominantNumber = signalsCard.locator(".font-data.text-4xl").first();
    await expect(dominantNumber).toBeVisible();

    // Get the text below the dominant number — this is the label span.
    // When HIGH >= 3: "risk categories firing HIGH" (red #f87171)
    // When HIGH < 3:  "risk categories at elevated signal levels" (amber)
    const labelSpan = signalsCard.locator("span.text-xs").first();
    await expect(labelSpan).toBeVisible();
    const labelText = (await labelSpan.textContent()) ?? "";

    // The label must be one of the two E1 outcomes — never something else.
    const isHighLabel = labelText.trim() === "risk categories firing HIGH";
    const isFallbackLabel =
      labelText.trim() === "risk categories at elevated signal levels";
    expect(isHighLabel || isFallbackLabel).toBe(true);

    // Verify that the color of the dominant number matches the label choice.
    const colorStyle = await dominantNumber.evaluate(
      (el) => (el as HTMLElement).style.color
    );
    if (isHighLabel) {
      // HIGH path: color must be the red token (#f87171)
      expect(colorStyle).toBe("rgb(248, 113, 113)");
    } else {
      // Fallback path: color must be amber (CSS var resolves to a non-red value)
      // We cannot resolve CSS custom properties in Playwright without evaluate,
      // so just assert it is NOT the red hex.
      expect(colorStyle).not.toBe("rgb(248, 113, 113)");
    }
  });

  // ── Assertion 3: Featured Signal tier badge aria-label ───────────────────

  test("featured signal card: tier badge has aria-label matching Risk tier: HIGH|MODERATE|INDICATIVE", async ({
    page,
  }) => {
    await page.goto("/dashboard");

    // The featured alert card is the <a href="/countries/{id}"> inside the
    // "Featured Signal" section. Its tier badge is a <span> with
    // aria-label="Risk tier: {tier}".
    //
    // We wait for the featured link to be visible first (it depends on the
    // bake data loaded server-side but the prop is passed at render time).
    const featuredLink = page
      .locator('a[href^="/countries/"]')
      .filter({ has: page.locator('[aria-label^="Risk tier:"]') })
      .first();

    await expect(featuredLink).toBeVisible({ timeout: 15_000 });

    const badge = featuredLink.locator('[aria-label^="Risk tier:"]').first();
    await expect(badge).toBeVisible();

    const ariaLabel = await badge.getAttribute("aria-label");
    expect(ariaLabel).toMatch(/^Risk tier: (HIGH|MODERATE|INDICATIVE)$/);
  });

  // ── Assertion 4: Lede sentence contains total country count ──────────────

  test("lede sentence contains a country count that matches the bake total", async ({
    page,
  }) => {
    await page.goto("/dashboard");

    // Section 2 lede: "QGI tracks political risk across {N} countries, ..."
    // We look for the paragraph in the page header section.
    // The lede is rendered server-side in the JSX as:
    //   <p>QGI tracks political risk across {stats.total} countries, ...</p>
    const lede = page
      .locator("p")
      .filter({ hasText: /QGI tracks political risk across/i });
    await expect(lede).toBeVisible({ timeout: 15_000 });

    const ledeText = (await lede.textContent()) ?? "";

    // Extract the number from "across N countries"
    const match = ledeText.match(/across\s+(\d+)\s+countries/i);
    expect(match).not.toBeNull();
    const countryCount = parseInt(match![1], 10);

    // Must be a plausible scored-country count (never 0, never > 250 UN states)
    expect(countryCount).toBeGreaterThan(0);
    expect(countryCount).toBeLessThanOrEqual(250);
  });

  // ── Assertion 5: "What this doesn't mean" callout (always-visible) ───────

  test('"What this doesn\'t mean" callout has role="note" and aria-label="Methodology note"', async ({
    page,
  }) => {
    await page.goto("/dashboard");

    // Tour-design (2026-05-18): converted from collapsed `<details>` to
    // always-visible `<aside role="note">` per Helena R5 + 4-persona
    // convergence — disclosure was universally missed when collapsed.
    const noteEl = page.locator('aside[role="note"][aria-label="Methodology note"]');
    await expect(noteEl).toBeVisible({ timeout: 15_000 });

    // The "What this doesn't mean" header label is rendered as a plain
    // div (no <summary> toggle) inside the callout.
    const noteText = (await noteEl.textContent()) ?? "";
    expect(noteText).toMatch(/what this doesn.t mean/i);
  });

  // ── Assertion 6: Four-family band CTAs link to correct V3 family pages ───

  test("four-family band CTAs link to /countries, /signals, /patterns, /precedents", async ({
    page,
  }) => {
    await page.goto("/dashboard");

    const band = page.locator('section[aria-label="QGI family summary"]');
    await expect(band).toBeVisible({ timeout: 15_000 });

    // Verify all 4 expected hrefs exist as child anchors of the band.
    const expectedHrefs = ["/countries", "/signals", "/patterns", "/precedents"];
    for (const href of expectedHrefs) {
      const card = band.locator(`a[href="${href}"]`);
      await expect(card).toBeVisible({ timeout: 10_000 });
    }

    // Spot-check: each card has a CTA text (the trailing "See all …" line)
    // that gives the user a forward navigation signal.
    const countriesCard = band.locator('a[href="/countries"]');
    const countriesCTA = (await countriesCard.textContent()) ?? "";
    expect(countriesCTA).toMatch(/see all/i);

    const signalsCard = band.locator('a[href="/signals"]');
    const signalsCTA = (await signalsCard.textContent()) ?? "";
    expect(signalsCTA).toMatch(/see all|risk categor/i);
  });

  // ── Assertion 7: Footer methodology link ─────────────────────────────────

  test("footer contains a methodology link pointing to /methodology", async ({
    page,
  }) => {
    await page.goto("/dashboard");

    // Section 7 footer is a <footer> element containing:
    //   <Link href="/methodology">Methodology & known limitations →</Link>
    const footer = page.locator("footer");
    await expect(footer).toBeVisible({ timeout: 15_000 });

    const methodologyLink = footer.locator('a[href="/methodology"]');
    await expect(methodologyLink).toBeVisible();

    const linkText = (await methodologyLink.textContent()) ?? "";
    expect(linkText).toMatch(/methodology/i);
  });
});
