/**
 * Tufte + Lloyd's caveat callout component pair for V2 ML recipe tear-sheets.
 *
 * Per qgi-aws-tf ticket #646 (re-scoped per resurfacing plan Q4): ship BOTH
 * Tufte-style (footnote-like, minimal weight) AND Lloyd's-style (prominent
 * banner) caveat variants. Routes ending `-a` consume `TufteCallout`; routes
 * ending `-b` consume `LloydsCallout`. Both surface the same buyer-disclosure
 * content from `data/ml-recipe-stack.json` (per recipe entry).
 *
 * Binding rules:
 * - Nasrin (2026-05-11): caveats are callout blocks, NOT footnotes; neutral-
 *   toned, no danger red (actuarial readers find color-coding patronizing);
 *   equal-or-greater visual prominence to claims they qualify on Lloyd's-style.
 * - Ji-Hoon (#656 Asas Majles cross-cutting note): when `interpretation_hint
 *   === 'engagement_signal'`, the badge MUST include the parenthetical
 *   "engagement indicator — does not imply premium reduction" — Solvency II
 *   internal-model discipline distinguishes direction-of-effect from pricing
 *   response.
 * - Resurfacing plan §caveat presentation: AHI "Not measured" MUST be
 *   explicit text, never blank; ADVISORY-ONLY rendering wired even if top-4
 *   doesn't currently trigger it (future recipes will); methodology cross-
 *   refs lazy-loaded.
 *
 * No color-coded "danger" palette — both variants use neutral grays + amber
 * for warning + deeper amber for critical (no red).
 */
"use client";

import type { ReactNode } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * Visual style for the caveat. `tufte` = footnote-style (data-ink ratio
 * prioritized); `lloyds` = full-width banner (equal visual prominence to
 * the claim it qualifies).
 */
export type CalloutStyle = "tufte" | "lloyds";

/**
 * Semantic level. `info` = neutral note; `warning` = caution-worthy caveat;
 * `critical` = MUST-NOT-cite-as-strength flag (reserved for degenerate-
 * evidence cases — none in current top-4, wired for future).
 */
export type CalloutLevel = "info" | "warning" | "critical";

/**
 * Interpretation-hint enum from #656 Asas DECISION. Mirrors
 * `data/ml-recipe-stack.json` `recipes[].interpretation_hint`.
 */
export type InterpretationHint = "risk_elevation" | "engagement_signal" | "ambiguous";

/**
 * Concentration alert level derived in the bake script from
 * `top_1_training_country_share` thresholds.
 */
export type ConcentrationAlertLevel = "HIGH" | "caution" | "low" | "none";

/**
 * Anchor AHI status from the bake. When `status === 'not_measured'` Nasrin's
 * binding rule requires the `reason` text to render as explicit italic.
 */
export type AnchorAhiStatus = "measured" | "not_measured";

// ---------------------------------------------------------------------------
// Neutral palette (no danger red per Nasrin's binding rule)
// ---------------------------------------------------------------------------

const LEVEL_COLORS: Record<CalloutLevel, { fg: string; bg: string; border: string }> = {
  info: {
    fg: "var(--qgi-text-dim)",
    bg: "var(--qgi-surface-2)",
    border: "var(--qgi-border)",
  },
  warning: {
    // Amber range — caution, not danger. fg pinned to amber-800 (not -700)
    // for WCAG AA contrast vs amber-100 bg (4.42:1 on amber-700 misses
    // the 4.5 threshold; amber-800 clears at ~6.7:1).
    fg: "#854d0e", // amber-800
    bg: "#fef3c7", // amber-100
    border: "#fbbf24", // amber-400
  },
  critical: {
    // Deepest amber — MUST-NOT but still NOT red (Nasrin's rule). Bumped
    // to amber-900 to maintain visual differentiation from `warning` after
    // the WCAG AA contrast fix moved `warning.fg` from amber-700 to -800.
    fg: "#78350f", // amber-900
    bg: "#fde68a", // amber-200
    border: "#d97706", // amber-600
  },
};

// ---------------------------------------------------------------------------
// Base callouts
// ---------------------------------------------------------------------------

/**
 * Tufte-style callout: small footnote-like text with a leading superscript
 * marker; minimal visual weight; data-ink ratio prioritized.
 *
 * Use inline adjacent to the claim being qualified. The marker is a small
 * superscript glyph; the body text follows in subtly de-emphasized type.
 */
export function TufteCallout({
  level,
  marker = "¹",
  children,
}: {
  level: CalloutLevel;
  /** Footnote marker (¹², etc.). Defaults to ¹. Pass own marker when stacking. */
  marker?: string;
  children: ReactNode;
}) {
  const colors = LEVEL_COLORS[level];
  return (
    <span
      className="text-[11px] leading-relaxed"
      style={{ color: colors.fg }}
      role="note"
    >
      <sup aria-hidden="true" className="mr-1 font-data" style={{ color: colors.fg }}>
        {marker}
      </sup>
      {children}
    </span>
  );
}

/**
 * Lloyd's-style callout: full-width banner; equal-or-greater visual
 * prominence to the claim it qualifies.
 *
 * Use as a block element above or below the qualifying claim. Renders as a
 * bordered card with the level's tonal palette. Title is optional; when
 * present, displayed in bold above the children.
 */
export function LloydsCallout({
  level,
  title,
  children,
}: {
  level: CalloutLevel;
  title?: string;
  children: ReactNode;
}) {
  const colors = LEVEL_COLORS[level];
  return (
    <div
      className="rounded-md px-4 py-3 my-3"
      style={{
        color: colors.fg,
        backgroundColor: colors.bg,
        border: `1px solid ${colors.border}`,
      }}
      role="note"
    >
      {title && (
        <div className="font-semibold text-sm mb-1" style={{ color: colors.fg }}>
          {title}
        </div>
      )}
      <div className="text-sm leading-relaxed">{children}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Specialized ML caveats (per resurfacing plan + #656 binding rules)
// ---------------------------------------------------------------------------

/**
 * ADVISORY-ONLY caveat per F-H-3 (post-KI-1: ↔ n_pos_loco == 1).
 *
 * Renders even when no current top-4 recipe triggers it (none do, post-KI-2),
 * so the wiring is screenshot-testable for the day a future LOCK with
 * n_pos_loco==1 ships. The text cites the Stage 5 paper's authoritative
 * F-H-3 ADVISORY-ONLY definition.
 */
export function AdvisoryOnlyCallout({
  style,
  nPosLoco,
}: {
  style: CalloutStyle;
  /** n_pos_LOCO from the recipe entry; rendered in the body. */
  nPosLoco?: number;
}) {
  const body = (
    <>
      <strong>Composite-only signal:</strong> this recipe has{" "}
      <span className="font-data">
        {nPosLoco ?? 1} held-out positive{(nPosLoco ?? 1) === 1 ? "" : "s"}
      </span>
      . Per buyer-disclosure rule, do not use as a primary signal for standalone risk
      pricing: only as one component of a composite score.
    </>
  );
  if (style === "tufte") {
    return <TufteCallout level="warning">{body}</TufteCallout>;
  }
  return (
    <LloydsCallout level="warning" title="Composite-only signal">
      {body}
    </LloydsCallout>
  );
}

/**
 * Concentration-alert caveat. Thresholds derived in the bake script
 * (`HIGH ≥ 0.30, caution 0.20-0.30, low < 0.20, none for null`).
 *
 * For `none` (multilateral_agreement: "not in concentration audit") returns
 * null — no caveat needed.
 */
export function ConcentrationAlertCallout({
  style,
  level,
  country,
  share,
}: {
  style: CalloutStyle;
  level: ConcentrationAlertLevel;
  country: string | null;
  share: number | null;
}) {
  if (level === "none" || country === null || share === null) {
    return null;
  }
  if (level === "low") {
    // Intentional design: low concentration is informational; always rendered
    // as a Tufte footnote regardless of the page's chrome `style`. Lloyd's
    // banners are visually load-bearing and reserved for caveats with actual
    // underwriting impact — surfacing a "Colombia 10% low" banner would
    // crowd the page. If a future Lloyd's-style page needs banner-level
    // low-concentration notes, add a separate variant rather than
    // overloading this one. (Style argument is preserved for API symmetry.)
    return (
      <TufteCallout level="info">
        Top-1 training country: <span className="font-semibold">{country}</span>{" "}
        <span className="font-data">({(share * 100).toFixed(1)}%)</span>. Low
        concentration; standard caveat applies.
      </TufteCallout>
    );
  }
  // caution or HIGH
  const calloutLevel: CalloutLevel = level === "HIGH" ? "critical" : "warning";
  const title =
    level === "HIGH"
      ? `HIGH training-data concentration: ${country}`
      : `Caution-level concentration: ${country}`;
  const body = (
    <>
      Top-1 training country accounts for{" "}
      <span className="font-data font-semibold">{(share * 100).toFixed(1)}%</span> of the
      held-out partition. Recipe predictions in {country}-adjacent country-years should be
      interpreted with the training-distribution caveat.
    </>
  );
  if (style === "tufte") {
    return <TufteCallout level={calloutLevel}>{body}</TufteCallout>;
  }
  return (
    <LloydsCallout level={calloutLevel} title={title}>
      {body}
    </LloydsCallout>
  );
}

/**
 * Anchor-AHI "Not measured" caveat per Nasrin's binding buyer-disclosure rule:
 * "Not measured" stays as explicit text, never blank or `null` field.
 *
 * When AHI is measured, returns null (numeric value is rendered separately
 * by the parent — this component is only for the not-measured case).
 *
 * Resurfacing plan §shared caveat rules: "Not measured" rendering specifically
 * uses bold italic on Lloyd's variant + italic on Tufte variant.
 */
export function NotMeasuredHint({
  style,
  status,
  reason,
}: {
  style: CalloutStyle;
  status: AnchorAhiStatus;
  /** The reason text from `per_recipe_anchor_ahi_reason` (always non-null
   * when status is `not_measured` per the bake's invariant). */
  reason: string | null;
}) {
  if (status !== "not_measured") return null;
  // The bake's reason field already starts with "Not measured —"
  // (extract_tear_sheets builds it as f"{head} — {reason}"). Strip that
  // prefix before rendering so the on-screen text doesn't say
  // "Not measured — Not measured — ..." twice.
  const trimmedReason = reason ? reason.replace(/^Not measured\s*—\s*/i, "") : null;
  const body = (
    <>
      <em>Not measured</em>
      {trimmedReason && (
        <span className="text-[var(--qgi-text-dim)]">: {trimmedReason}</span>
      )}
    </>
  );
  if (style === "tufte") {
    return <TufteCallout level="info">{body}</TufteCallout>;
  }
  return (
    <LloydsCallout level="info" title="Anchor stability: not yet measured">
      <span className="font-semibold italic">{body}</span>
    </LloydsCallout>
  );
}

/**
 * Interpretation-hint badge per #656 Asas mini-Majles DECISION.
 *
 * Per Ji-Hoon's binding cross-cutting note: when hint is `engagement_signal`,
 * the rendering MUST include the parenthetical "engagement indicator — does
 * not imply premium reduction." Solvency II internal-model discipline
 * distinguishes direction-of-effect from pricing response.
 *
 * `risk_elevation` and `ambiguous` need no additional disclosure text —
 * the labels are self-explanatory to a Lloyd's-aware reader.
 */
export function InterpretationHintBadge({
  style,
  hint,
}: {
  style: CalloutStyle;
  hint: InterpretationHint;
}) {
  const labels: Record<InterpretationHint, string> = {
    risk_elevation: "Risk-elevation indicator",
    engagement_signal: "Engagement indicator (does not imply premium reduction)",
    ambiguous: "Context-dependent: read mechanism narrative",
  };
  const levels: Record<InterpretationHint, CalloutLevel> = {
    risk_elevation: "warning",
    engagement_signal: "info",
    ambiguous: "info",
  };
  const text = labels[hint];
  const level = levels[hint];
  if (style === "tufte") {
    return <TufteCallout level={level}>{text}</TufteCallout>;
  }
  return <LloydsCallout level={level}>{text}</LloydsCallout>;
}

// ---------------------------------------------------------------------------
// f_rule_anomaly callout (currently only epidemic_and_pandemic; not in
// top-4 ship list, but wired for completeness — future recipes will trigger)
// ---------------------------------------------------------------------------

/**
 * F-rule anomaly disclosure. Currently triggers only on
 * `epidemic_and_pandemic` (post-KI-2 lone anomaly). NOT in top-4 ship list,
 * but wired so the day a future LOCK ships with f_rule_anomaly=true, the
 * rendering is already screenshot-tested.
 */
export function FRuleAnomalyCallout({ style }: { style: CalloutStyle }) {
  const body = (
    <>
      In-sample fit falls below threshold under the assigned architecture; tier status
      rests on out-of-country discrimination alone. Buyer-disclosure caveat: do not cite
      the tier label without this anomaly disclosed.
    </>
  );
  if (style === "tufte") {
    return <TufteCallout level="warning">{body}</TufteCallout>;
  }
  return (
    <LloydsCallout level="warning" title="F-rule anomaly">
      {body}
    </LloydsCallout>
  );
}
