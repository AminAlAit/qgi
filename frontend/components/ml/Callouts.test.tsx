import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  AdvisoryOnlyCallout,
  ConcentrationAlertCallout,
  FRuleAnomalyCallout,
  InterpretationHintBadge,
  LloydsCallout,
  NotMeasuredHint,
  TufteCallout,
} from "./Callouts";

describe("TufteCallout", () => {
  it("renders body text + default marker", () => {
    render(<TufteCallout level="info">a footnote</TufteCallout>);
    expect(screen.getByText("a footnote")).toBeInTheDocument();
    expect(screen.getByText("¹")).toBeInTheDocument();
  });

  it("respects custom marker for stacked footnotes", () => {
    render(
      <TufteCallout level="warning" marker="²">
        second note
      </TufteCallout>
    );
    expect(screen.getByText("²")).toBeInTheDocument();
  });

  it("renders with role=note for screen-reader discoverability", () => {
    render(<TufteCallout level="info">x</TufteCallout>);
    expect(screen.getByRole("note")).toBeInTheDocument();
  });
});

describe("LloydsCallout", () => {
  it("renders title + body when title is provided", () => {
    render(
      <LloydsCallout level="warning" title="Caution">
        body content
      </LloydsCallout>
    );
    expect(screen.getByText("Caution")).toBeInTheDocument();
    expect(screen.getByText("body content")).toBeInTheDocument();
  });

  it("renders body without title", () => {
    render(<LloydsCallout level="info">just body</LloydsCallout>);
    expect(screen.getByText("just body")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// AdvisoryOnlyCallout
// ---------------------------------------------------------------------------

describe("AdvisoryOnlyCallout", () => {
  it("renders composite-only callout on Tufte variant", () => {
    render(<AdvisoryOnlyCallout style="tufte" nPosLoco={1} />);
    expect(screen.getByText(/Composite-only/)).toBeInTheDocument();
    expect(screen.getByText(/1 held-out positive/)).toBeInTheDocument();
  });

  it("renders composite-only title on Lloyd's variant", () => {
    render(<AdvisoryOnlyCallout style="lloyds" nPosLoco={1} />);
    expect(screen.getByText("Composite-only signal")).toBeInTheDocument();
  });

  it("defaults nPosLoco to 1 when not provided", () => {
    render(<AdvisoryOnlyCallout style="tufte" />);
    expect(screen.getByText(/1 held-out positive/)).toBeInTheDocument();
  });

  it("renders plural 'positives' when nPosLoco > 1", () => {
    render(<AdvisoryOnlyCallout style="tufte" nPosLoco={3} />);
    expect(screen.getByText(/3 held-out positives/)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// ConcentrationAlertCallout
// ---------------------------------------------------------------------------

describe("ConcentrationAlertCallout", () => {
  it("returns null for level='none' (multilateral_agreement case)", () => {
    const { container } = render(
      <ConcentrationAlertCallout style="tufte" level="none" country={null} share={null} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders low-concentration as informational note", () => {
    render(
      <ConcentrationAlertCallout style="tufte" level="low" country="china" share={0.1} />
    );
    expect(screen.getByText(/Low concentration/)).toBeInTheDocument();
    expect(screen.getByText("china")).toBeInTheDocument();
    expect(screen.getByText("(10.0%)")).toBeInTheDocument();
  });

  it("renders low-concentration as Tufte footnote even when style='lloyds'", () => {
    // Intentional design: low concentration is always Tufte-style regardless
    // of the page's chrome. See JSDoc note in Callouts.tsx.
    render(
      <ConcentrationAlertCallout style="lloyds" level="low" country="china" share={0.1} />
    );
    expect(screen.getByText(/Low concentration/)).toBeInTheDocument();
    // No banner title would appear in Tufte fallback
    expect(screen.queryByText("Low concentration — china")).not.toBeInTheDocument();
  });

  it("renders caution body without hyphenation artifacts (country-years copy)", () => {
    // Regression test for "country- years" copy defect (spurious space across
    // a JSX line break) flagged in QA review.
    render(
      <ConcentrationAlertCallout
        style="lloyds"
        level="caution"
        country="syria"
        share={0.222}
      />
    );
    // Text must be "country-years" (no space), not "country- years"
    const text = screen.getByText(/syria-adjacent/).textContent ?? "";
    expect(text).toContain("country-years");
    expect(text).not.toContain("country- years");
  });

  it("renders caution-level with country + share — Tufte", () => {
    render(
      <ConcentrationAlertCallout
        style="tufte"
        level="caution"
        country="syria"
        share={0.222}
      />
    );
    expect(screen.getByText(/22.2%/)).toBeInTheDocument();
    expect(screen.getByText(/syria-adjacent/)).toBeInTheDocument();
  });

  it("renders HIGH-level with banner title on Lloyd's variant", () => {
    render(
      <ConcentrationAlertCallout
        style="lloyds"
        level="HIGH"
        country="venezuela"
        share={0.714}
      />
    );
    expect(
      screen.getByText("HIGH training-data concentration: venezuela")
    ).toBeInTheDocument();
    expect(screen.getByText(/71.4%/)).toBeInTheDocument();
  });

  it("renders caution title on Lloyd's variant", () => {
    render(
      <ConcentrationAlertCallout
        style="lloyds"
        level="caution"
        country="colombia"
        share={0.25}
      />
    );
    expect(screen.getByText("Caution-level concentration: colombia")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// NotMeasuredHint (per Nasrin's binding "Not measured" rule)
// ---------------------------------------------------------------------------

describe("NotMeasuredHint", () => {
  it("returns null when status is 'measured'", () => {
    const { container } = render(
      <NotMeasuredHint style="tufte" status="measured" reason={null} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders 'Not measured' explicit text on Tufte (Nasrin's rule)", () => {
    render(
      <NotMeasuredHint
        style="tufte"
        status="not_measured"
        reason="no anchor cases in v2 regression suite"
      />
    );
    expect(screen.getByText("Not measured")).toBeInTheDocument();
    expect(
      screen.getByText(/no anchor cases in v2 regression suite/)
    ).toBeInTheDocument();
  });

  it("strips duplicate 'Not measured —' prefix from reason", () => {
    // Regression: bake produces reason="Not measured — no anchor cases..."
    // and the callout title also says "Not measured". Without prefix-strip
    // the on-screen text reads "Not measured — Not measured — no anchor..."
    const { container } = render(
      <NotMeasuredHint
        style="lloyds"
        status="not_measured"
        reason="Not measured — no anchor cases in v2 regression suite"
      />
    );
    const text = container.textContent ?? "";
    // The body shouldn't contain "Not measured — Not measured"
    expect(text).not.toMatch(/Not measured\s*—\s*Not measured/);
    expect(text).toContain("no anchor cases in v2 regression suite");
  });

  it("renders 'Anchor stability: not yet measured' title on Lloyd's variant", () => {
    render(
      <NotMeasuredHint
        style="lloyds"
        status="not_measured"
        reason="remediation = v3 anchor battery"
      />
    );
    expect(screen.getByText("Anchor stability: not yet measured")).toBeInTheDocument();
    expect(screen.getByText(/remediation = v3 anchor battery/)).toBeInTheDocument();
  });

  it("renders without reason if reason is null", () => {
    render(<NotMeasuredHint style="tufte" status="not_measured" reason={null} />);
    expect(screen.getByText("Not measured")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// InterpretationHintBadge (per #656 DECISION + Ji-Hoon's binding rule)
// ---------------------------------------------------------------------------

describe("InterpretationHintBadge", () => {
  it("renders 'Risk-elevation indicator' for risk_elevation", () => {
    render(<InterpretationHintBadge style="tufte" hint="risk_elevation" />);
    expect(screen.getByText("Risk-elevation indicator")).toBeInTheDocument();
  });

  it("renders Ji-Hoon's parenthetical for engagement_signal — Tufte", () => {
    // Ji-Hoon's binding rule from #656 cross-cutting note: engagement_signal
    // MUST include "does not imply premium reduction" parenthetical
    render(<InterpretationHintBadge style="tufte" hint="engagement_signal" />);
    expect(screen.getByText(/Engagement indicator/)).toBeInTheDocument();
    expect(screen.getByText(/does not imply premium reduction/)).toBeInTheDocument();
  });

  it("renders Ji-Hoon's parenthetical for engagement_signal — Lloyd's", () => {
    render(<InterpretationHintBadge style="lloyds" hint="engagement_signal" />);
    expect(screen.getByText(/does not imply premium reduction/)).toBeInTheDocument();
  });

  it("renders 'Context-dependent' for ambiguous", () => {
    render(<InterpretationHintBadge style="tufte" hint="ambiguous" />);
    expect(
      screen.getByText("Context-dependent: read mechanism narrative")
    ).toBeInTheDocument();
  });

  it("Tufte vs Lloyd's variants both render the same hint text", () => {
    // Ji-Hoon's parenthetical is binding regardless of visual style — the
    // disclosure is content, not chrome.
    const { container: cTufte } = render(
      <InterpretationHintBadge style="tufte" hint="engagement_signal" />
    );
    const { container: cLloyds } = render(
      <InterpretationHintBadge style="lloyds" hint="engagement_signal" />
    );
    expect(cTufte.textContent).toContain("does not imply premium reduction");
    expect(cLloyds.textContent).toContain("does not imply premium reduction");
  });
});

// ---------------------------------------------------------------------------
// FRuleAnomalyCallout (wired for future epidemic_and_pandemic-class recipes)
// ---------------------------------------------------------------------------

describe("FRuleAnomalyCallout", () => {
  it("renders the F-rule anomaly disclosure on Tufte", () => {
    render(<FRuleAnomalyCallout style="tufte" />);
    expect(screen.getByText(/In-sample fit falls below threshold/)).toBeInTheDocument();
  });

  it("renders title on Lloyd's variant", () => {
    render(<FRuleAnomalyCallout style="lloyds" />);
    expect(screen.getByText("F-rule anomaly")).toBeInTheDocument();
  });
});
