import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CountryMergedDetail } from "./CountryMergedDetail";

/**
 * #853 — WhatsHappeningHere empty top3 guard.
 *
 * When top3 is empty (all top_categories filtered out by lockedRecipeSet in
 * app/(app)/countries/[iso]/page.tsx), WhatsHappeningHere must NOT render an
 * empty sentence fragment ("{name} sits at Tier X — ... The strongest dimension
 * of risk is —; the specific signals driving it include .") and instead render
 * a clear "No ML-validated signals currently firing" note.
 */

const MINIMAL_L1_ROWS = [
  {
    code: "A",
    label: "Political",
    shortLabel: "Pol",
    color: "#f87171",
    salience: null,
  },
];

describe("CountryMergedDetail / WhatsHappeningHere", () => {
  it("#853 — renders 'No ML-validated signals' copy when top3 is empty", () => {
    render(
      <CountryMergedDetail
        iso="qa"
        name="Qatar"
        alpha_2="QA"
        curated={true}
        tier="HIGH"
        l1Rows={MINIMAL_L1_ROWS}
        top3={[]}
        top1L1Label={null}
      />
    );
    expect(
      screen.getByText(
        /No ML-validated signals are currently firing at MODERATE\+ for Qatar/
      )
    ).toBeInTheDocument();
    // Must NOT show the old empty-list pattern "the specific signals driving it include"
    // when top3 is empty.
    expect(
      screen.queryByText(/the specific ML-validated signals driving it include\s*\./)
    ).toBeNull();
  });

  it("#853 — renders the normal narrative with categories when top3 is non-empty (LOCKed)", () => {
    render(
      <CountryMergedDetail
        iso="qa"
        name="Qatar"
        alpha_2="QA"
        curated={true}
        tier="HIGH"
        l1Rows={MINIMAL_L1_ROWS}
        top3={[
          {
            category: "elections_and_voting",
            salience_score: 2.1,
            l1_group: "A",
            recipe_count: 7,
          },
        ]}
        top1L1Label="Political"
      />
    );
    // Normal narrative present.
    expect(
      screen.getByText(/the specific ML-validated signals driving it include/)
    ).toBeInTheDocument();
    expect(screen.getByText(/Elections And Voting/i)).toBeInTheDocument();
    // "No ML-validated signals" note must NOT appear.
    expect(screen.queryByText(/No ML-validated signals are currently firing/)).toBeNull();
  });
});
