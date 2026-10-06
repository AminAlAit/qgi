import { CALM_SLATE_BLUE } from "@/lib/te-mock/l1-families";

export function StructuralFenceNote() {
  return (
    <section style={{ marginBottom: "32px" }}>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "12px",
          marginBottom: "12px",
        }}
      >
        <span
          style={{
            fontSize: "10px",
            letterSpacing: "1.5px",
            fontFamily: "ui-monospace, monospace",
            color: "var(--qgi-text-dim)",
          }}
        >
          §04
        </span>
        <h2
          style={{
            fontSize: "16px",
            fontWeight: 600,
            margin: 0,
            color: CALM_SLATE_BLUE,
            flex: 1,
          }}
        >
          How to read this dashboard
        </h2>
      </div>
      <div
        style={{
          padding: "18px 20px",
          border: `1px solid ${CALM_SLATE_BLUE}55`,
          borderLeft: `3px solid ${CALM_SLATE_BLUE}`,
          background: `${CALM_SLATE_BLUE}0F`,
          borderRadius: "8px",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          gap: "16px",
        }}
      >
        <FenceRule
          n="01"
          title="Scores are ranks, not probabilities."
          body={
            <>
              Every score on this page is a <strong>discrimination rank</strong>: it
              reflects how closely a country&apos;s current indicator trajectory resembles
              a validated crisis pattern, not the likelihood of an event occurring. A high
              rank means resemblance, nothing more.
            </>
          }
        />
        <FenceRule
          n="02"
          title="Tile counts come from the public tracker."
          body={
            <>
              Recipe counts (validated, tested, queued) are integers drawn directly from
              the recipe tracker. Nothing on this dashboard promotes a recipe&apos;s tier
              or softens a verdict in transit.
            </>
          }
        />
        <FenceRule
          n="03"
          title="Corrections are surfaced on purpose."
          body={
            <>
              When a prior result does not hold up under further review, the correction
              appears here alongside the original. The activity timeline and recipe
              tracker carry the full record. Publishing corrections is part of how the
              program works.
            </>
          }
        />
        <FenceRule
          n="04"
          title="Nothing here is a forecast."
          body={
            <>
              QGI describes and ranks current conditions; it does not predict future
              events or assign probabilities to outcomes. No tile, score, or trend line on
              this page should be read as a forward claim.
            </>
          }
        />
      </div>
    </section>
  );
}

function FenceRule({
  n,
  title,
  body,
}: {
  n: string;
  title: string;
  body: React.ReactNode;
}) {
  return (
    <div>
      <div
        style={{
          fontSize: "10px",
          letterSpacing: "1.2px",
          color: CALM_SLATE_BLUE,
          fontFamily: "ui-monospace, monospace",
          marginBottom: "6px",
        }}
      >
        §{n}
      </div>
      <div
        style={{
          fontSize: "13px",
          fontWeight: 600,
          color: "var(--qgi-text)",
          marginBottom: "5px",
        }}
      >
        {title}
      </div>
      <div style={{ fontSize: "12.5px", color: "var(--qgi-text)", lineHeight: 1.55 }}>
        {body}
      </div>
    </div>
  );
}
