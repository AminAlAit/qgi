/**
 * StructuralFenceNote — V4.1
 *
 * Promoted from §04-bottom to §02-top (renders directly under the Hero, before
 * any tile). Sofia: "Bottom-of-page firewalls are a tell that the author is
 * hedging. Top-of-page firewalls trust the reader to handle the frame before
 * the content."
 *
 * Changes from V4:
 * - Wrapped in PanelBase (Worker B) with title, caption, accent=#5B7E99.
 * - §01/§02/§03/§04 rule-numbering dropped; parallel hanging titles carry
 *   identity without internal hierarchy markers.
 * - No double-bordering: PanelBase owns the left accent border. Inner grid
 *   uses a light background tint only.
 * - Four rule titles and body copy preserved byte-identical from V4
 *   (Talia + Marcus ratified the copy as already at-bar).
 * - Plain server component; no state, no interactions.
 */

import { PanelBase } from "@/components/dashboard-v4-1/PanelBase";

const CALM_SLATE_BLUE = "#5B7E99";

export function StructuralFenceNote() {
  return (
    <PanelBase
      title="How to read this dashboard"
      caption="What the numbers below mean before you look at them."
      accent={CALM_SLATE_BLUE}
    >
      <div
        style={{
          padding: "14px 16px",
          background: `${CALM_SLATE_BLUE}0F`,
          borderRadius: "5px",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          gap: "16px",
        }}
      >
        <FenceRule
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
          title="Tile counts come from the public tracker."
          body={
            <>
              Trend counts (validated, tested, queued) are integers drawn directly from
              the recipe tracker. Nothing on this dashboard promotes a trend&apos;s tier
              or softens a verdict in transit.
            </>
          }
        />
        <FenceRule
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
    </PanelBase>
  );
}

function FenceRule({ title, body }: { title: string; body: React.ReactNode }) {
  return (
    <div>
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
