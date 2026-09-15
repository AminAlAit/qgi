/**
 * PanelBase — V4.1 panel primitive.
 *
 * Family color (Charter L1 family — e.g. Foreign Intervention = #E64545
 * Conflict & Violence) is applied as a thin 3px left border + chip / accent
 * tints inside the panel + the panel title color. Surface stays dark navy;
 * family color never floods the background.
 *
 * 2026-05-27 polish (#154 — scrub internal terminology): section-pending
 * dual copy rephrased to drop "gate" / "walk" from visible text. The
 * methodology distinction (separation vs. probability) is preserved; the
 * underlying R&D facts stay in the tooltips for technical readers.
 */
import type { CSSProperties, ReactNode } from "react";
import { TooltipChip } from "./TooltipChip";

type SectionPending = "discrimination" | "probability" | null;

interface Props {
  title: string;
  titleTooltip?: string;
  familyColor: string;
  sectionPending?: SectionPending;
  id?: string;
  /** Optional data-tour anchor for product tour steps. */
  dataTour?: string;
  headerSlot?: ReactNode;
  caption?: string;
  /** Optional style overrides merged onto the panel <section> (e.g.
   *  `gridColumn: "span 2"` to make a panel span two grid columns). */
  style?: CSSProperties;
  children?: ReactNode;
}

/** V4.1 §0 polish (#23 — 2026-05-29):
 *  Confidence-first pending copy. The old text leaked exposure
 *  ("Fills once this recipe has been tested...") — the new text reads as
 *  forward motion ("In active rotation — discrimination view fills on the
 *  next validation pass"). Same fact, sold not hedged. */
const PENDING_COPY: Record<NonNullable<SectionPending>, string> = {
  discrimination: "In active rotation. This view fills on the next validation pass.",
  probability:
    "In active rotation. The probability layer arrives once the rank stabilizes across validation passes.",
};

const PENDING_LABEL: Record<NonNullable<SectionPending>, string> = {
  discrimination: "Next pass",
  probability: "Probability layer pending",
};

export function PanelBase({
  title,
  titleTooltip,
  familyColor,
  sectionPending = null,
  id,
  dataTour,
  headerSlot,
  caption,
  style,
  children,
}: Props) {
  return (
    <section
      id={id}
      data-tour={dataTour}
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderLeft: `3px solid ${familyColor}`,
        borderRadius: "6px",
        padding: "18px 18px 16px",
        display: "flex",
        flexDirection: "column",
        gap: "12px",
        minHeight: "140px",
        ...style,
      }}
    >
      <header style={{ display: "flex", alignItems: "baseline", gap: "10px" }}>
        <h2
          style={{
            fontSize: "15px",
            fontWeight: 600,
            lineHeight: 1.25,
            margin: 0,
            color: familyColor,
            flex: 1,
            letterSpacing: "0.1px",
          }}
        >
          {title}
        </h2>
        {titleTooltip && (
          <TooltipChip
            label={`About ${title}`}
            tooltip={titleTooltip}
            accentColor={familyColor}
          />
        )}
        {headerSlot && <div style={{ flexShrink: 0 }}>{headerSlot}</div>}
      </header>

      {caption && (
        <p
          style={{
            fontSize: "12px",
            lineHeight: 1.5,
            color: "var(--qgi-text-muted)",
            margin: 0,
          }}
        >
          {caption}
        </p>
      )}

      {sectionPending ? (
        <div
          role="status"
          aria-live="polite"
          style={{
            padding: "16px 14px",
            border: "1px dashed var(--qgi-border)",
            background: "rgba(255,255,255,0.015)",
            borderRadius: "5px",
            display: "flex",
            flexDirection: "column",
            gap: "6px",
            marginTop: "auto",
          }}
        >
          <div
            style={{
              fontSize: "10px",
              letterSpacing: "1.1px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
              textTransform: "uppercase",
            }}
          >
            {PENDING_LABEL[sectionPending]}
          </div>
          <div
            style={{
              fontSize: "13px",
              lineHeight: 1.5,
              color: "var(--qgi-text-muted)",
            }}
          >
            {PENDING_COPY[sectionPending]}
          </div>
        </div>
      ) : (
        <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
          {children}
        </div>
      )}
    </section>
  );
}
