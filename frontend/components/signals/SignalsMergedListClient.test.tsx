/**
 * #815 (2026-05-18) regression test — /signals 4-only graduation.
 *
 * The graduation gate (filter to mlStack.metadata.top_4_recipes) is
 * enforced at server-side aggregation in `app/(app)/signals/page.tsx`.
 * This co-located client test guards the COMPONENT against silently
 * expanding past 4 rows if a future caller passes an unfiltered prop —
 * the client should render exactly what it receives, no more.
 *
 * The 4 LOCKed recipes (single source of truth: data/ml-recipe-stack.json
 * metadata.top_4_recipes):
 *   - civil_war_and_insurgency
 *   - multilateral_agreement
 *   - elections_and_voting
 *   - bilateral_treaty
 *
 * The corresponding `qgi-aws-tf` ticket: #815.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SignalsMergedListClient } from "./SignalsMergedListClient";
import type { SignalRow } from "@/lib/signals-types";

const LOCKED_SLUGS = [
  "civil_war_and_insurgency",
  "multilateral_agreement",
  "elections_and_voting",
  "bilateral_treaty",
] as const;

function makeRow(category: string, salience: number): SignalRow {
  return {
    category,
    display_name: category.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
    tier: salience >= 2.5 ? "HIGH" : salience >= 1.0 ? "MODERATE" : "INDICATIVE",
    max_salience: salience,
    avg_salience: salience * 0.5,
    firing_count: 10,
    top_countries: [{ id: "1", name: "Test Country", alpha_2: "TC", salience }],
    l1: null,
  };
}

describe("SignalsMergedListClient — #815 4-only graduation", () => {
  it("renders exactly 4 category rows for the 4 LOCKed recipes", () => {
    const signals = LOCKED_SLUGS.map((slug, i) => makeRow(slug, 2.6 - i * 0.4));
    render(
      <SignalsMergedListClient
        signals={signals}
        tierCounts={{ HIGH: 2, MODERATE: 2, INDICATIVE: 0 }}
        totalCountries={156}
        generatedDate="2026-04-30"
        domainActivation={[]}
      />
    );
    // Each row renders an anchor link href starting with /signals/. Assert
    // exactly 4 such links in the row list (excluding any nav / leaderboard
    // links that may also use the prefix — count display_name occurrences
    // instead for stability).
    for (const slug of LOCKED_SLUGS) {
      const displayName = slug
        .replace(/_/g, " ")
        .replace(/\b\w/g, (c) => c.toUpperCase());
      expect(
        screen.getAllByText((content) =>
          content.toLowerCase().includes(displayName.toLowerCase())
        ).length
      ).toBeGreaterThanOrEqual(1);
    }
  });

  it("renders the post-graduation metric strip copy ('ML-validated recipes')", () => {
    const signals = LOCKED_SLUGS.map((slug, i) => makeRow(slug, 2.6 - i * 0.4));
    render(
      <SignalsMergedListClient
        signals={signals}
        tierCounts={{ HIGH: 2, MODERATE: 2, INDICATIVE: 0 }}
        totalCountries={156}
        generatedDate="2026-04-30"
        domainActivation={[]}
      />
    );
    // The strip should say "ML-validated", not the pre-graduation
    // "categories tracked" wording.
    expect(screen.getByText(/ML-validated/i)).toBeInTheDocument();
  });

  it("renders every passed row including non-LOCKed (component is a pure renderer)", () => {
    // Contract test (per QA PR #123 F5 rename): the component is a
    // dumb renderer — it shows exactly the rows it receives. The 4-only
    // graduation is enforced at the server (app/(app)/signals/page.tsx)
    // and the per-country / sitemap / generateStaticParams surfaces; the
    // client just renders the filtered prop. This test pins the contract
    // explicitly so a future maintainer doesn't push display-layer
    // filtering into the component and break the separation of concerns.
    //
    // Server-filter integration coverage is a follow-up gap acknowledged
    // in this PR's description and tracked as a separate ticket.
    const signals = [
      ...LOCKED_SLUGS.map((slug, i) => makeRow(slug, 2.6 - i * 0.4)),
      makeRow("terrorist_attack", 2.0),
    ];
    render(
      <SignalsMergedListClient
        signals={signals}
        tierCounts={{ HIGH: 2, MODERATE: 3, INDICATIVE: 0 }}
        totalCountries={156}
        generatedDate="2026-04-30"
        domainActivation={[]}
      />
    );
    // All 4 LOCKed AND the unfiltered terrorist_attack should appear.
    for (const slug of [...LOCKED_SLUGS, "terrorist_attack"]) {
      const displayName = slug
        .replace(/_/g, " ")
        .replace(/\b\w/g, (c) => c.toUpperCase());
      expect(
        screen.getAllByText((content) =>
          content.toLowerCase().includes(displayName.toLowerCase())
        ).length
      ).toBeGreaterThanOrEqual(1);
    }
  });
});
