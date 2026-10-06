/**
 * MinorPanels — smaller panels for Recipes V4.1.
 *
 * Polish pass (Sofia, 2026-05-27 — #153 / #154 / #155 / #156):
 *   - DefinitionPanel still exported for back-compat but no longer used
 *     by the V4.1 page (Definition now lives in PageLayout's header lede).
 *   - IdentityCardPanel slimmed: walk metadata + window dropped. Status
 *     renders as a user-facing phrase (formatStatus), not the raw enum.
 *   - WindowPanel + DiscriminationPanel get de-jargonized captions while
 *     preserving methodology meaning (R&D Q5 binds the FACT, not the
 *     word "LOCK"); technical readers find the threshold in the tooltip.
 *   - All "gate" / "walk" / "walked_no_graduation" phrasing scrubbed
 *     from visible copy.
 */
import type { ReactNode } from "react";
import { PanelBase } from "./PanelBase";
import { IndicatorDonut } from "./IndicatorDonut";
import { flagFor } from "@/lib/te-mock/country-flags";
import { stripProviderSuffix } from "@/lib/indicator-labels";
import type { IndicatorWithWeight, CountryScore } from "@/lib/te-mock/recipe-v4-1-mock";

/* ───────── DefinitionPanel (deprecated — kept for compat) ──────────── */
export function DefinitionPanel({
  familyColor,
  definition,
}: {
  familyColor: string;
  definition: string;
}) {
  return (
    <PanelBase
      title="Definition"
      familyColor={familyColor}
      titleTooltip="The trend's structural identity. Locked at trend creation; refines as curated events grow."
      id="cap-1"
    >
      <p
        style={{ fontSize: "14px", lineHeight: 1.6, color: "var(--qgi-text)", margin: 0 }}
      >
        {definition}
      </p>
    </PanelBase>
  );
}

/* ───────── IndicatorSet (interactive donut of signal weights) ────────── */
/*                                                                          */
/* 2026-05-31 (founder): the per-indicator bar list became a donut so the   */
/* part-to-whole reading is immediate. `wide` spans two grid columns. The   */
/* donut itself is the interactive client component IndicatorDonut (hover a */
/* slice or legend row to light it and fade the others); the legend names   */
/* stay fixed on the right.                                                 */

export function IndicatorSetPanel({
  familyColor,
  indicators,
  wide = false,
}: {
  familyColor: string;
  indicators: IndicatorWithWeight[];
  /** Span two grid columns and render the donut + legend side by side. */
  wide?: boolean;
}) {
  const hasWeights =
    indicators.length > 0 && indicators.every((i) => typeof i.shapWeightPct === "number");
  const sorted = hasWeights
    ? [...indicators].sort((a, b) => b.shapWeightPct - a.shapWeightPct)
    : indicators;

  return (
    <PanelBase
      title="What moves with this trend"
      familyColor={familyColor}
      titleTooltip={`The ${indicators.length || "N"} indicators whose combined canonical movement shape defines this trend. Each slice is one signal's weight, derived from its SHAP contribution; weights total 100% across the set.`}
      caption={
        indicators.length > 0
          ? `These indicators move together with this trend: a correlated blend that gives it its statistical fingerprint. They are associations, not proven drivers.`
          : undefined
      }
      sectionPending={indicators.length === 0 ? "discrimination" : null}
      id="cap-2"
      style={wide ? { gridColumn: "span 2" } : undefined}
    >
      {!hasWeights ? (
        <ul
          style={{
            listStyle: "none",
            padding: 0,
            margin: 0,
            display: "flex",
            flexDirection: "column",
            gap: "8px",
          }}
        >
          {indicators.map((ind) => (
            <li
              key={ind.code}
              style={{ fontSize: "12.5px", color: "var(--qgi-text)" }}
              title={ind.code}
            >
              <span
                style={{
                  fontSize: "9.5px",
                  letterSpacing: "0.6px",
                  color: "var(--qgi-text-dim)",
                  fontFamily: "ui-monospace, monospace",
                  textTransform: "uppercase",
                  marginRight: "8px",
                }}
              >
                {ind.provider}
              </span>
              {stripProviderSuffix(ind.name)}
            </li>
          ))}
        </ul>
      ) : (
        <IndicatorDonut familyColor={familyColor} indicators={sorted} />
      )}
    </PanelBase>
  );
}

/* ───────── Optimal window (#156 polish) ─────────────────────────────── */

export function WindowPanel({
  familyColor,
  windowYears,
  trendName,
  example,
  ciLow,
  ciHigh,
}: {
  familyColor: string;
  windowYears: number;
  /** This trend's display name, used in the plain-English line + example. */
  trendName: string;
  /** A real precedent grounding the example; omitted when none is available. */
  example?: {
    country: string;
    iso2: string;
    year: number;
    label: string;
  } | null;
  ciLow?: number;
  ciHigh?: number;
}) {
  const sweepCopy =
    ciLow !== undefined && ciHigh !== undefined
      ? ` Chosen by searching ${ciLow}–${ciHigh} years of history and keeping the most predictive length.`
      : "";
  // Lower-case the trend so it reads mid-sentence ("a foreign intervention").
  const trendLower = trendName.charAt(0).toLowerCase() + trendName.slice(1);
  const startYear = example ? example.year - windowYears : null;

  return (
    <PanelBase
      title="Optimal Window"
      familyColor={familyColor}
      titleTooltip="Chosen by sweeping a range of window lengths and keeping the one whose canonical movement shape separates pre-event years most cleanly."
      caption={`In the data, the warning signs of a ${trendLower} build over about ${windowYears} years. That is the run-up this trend reads before the ${trendLower} event arrives.`}
      id="cap-3"
      dataTour="window-panel"
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "14px",
          marginTop: "2px",
        }}
      >
        <div style={{ display: "flex", alignItems: "flex-end", gap: "10px" }}>
          <span
            style={{
              fontSize: "64px",
              fontWeight: 700,
              color: familyColor,
              fontFamily: "ui-monospace, monospace",
              lineHeight: 0.95,
              letterSpacing: "-2.5px",
            }}
          >
            {windowYears}
          </span>
          <span
            style={{
              fontSize: "16px",
              fontWeight: 600,
              color: "var(--qgi-text-muted)",
              fontFamily: "ui-monospace, monospace",
              letterSpacing: "0.5px",
              paddingBottom: "8px",
              textTransform: "uppercase",
            }}
          >
            years
          </span>
        </div>

        {/* Advanced layer — the methodology wording, for readers who want it.
            The plain-English version lives in the panel caption above. */}
        <p
          style={{
            fontSize: "11.5px",
            lineHeight: 1.55,
            color: "var(--qgi-text-dim)",
            margin: 0,
          }}
        >
          Technically, the trend&apos;s canonical movement shape spans the {windowYears}{" "}
          years of indicator history leading up to each event.{sweepCopy}
        </p>

        {/* Example — a real precedent. End year is the event itself; the start
            year is one window earlier, so the line shows the actual run-up. */}
        {example && startYear !== null && (
          <div
            style={{
              borderTop: "1px dashed var(--qgi-border)",
              paddingTop: "12px",
              display: "flex",
              flexDirection: "column",
              gap: "8px",
            }}
          >
            <div
              style={{
                fontSize: "9.5px",
                letterSpacing: "1px",
                color: "var(--qgi-text-dim)",
                fontFamily: "ui-monospace, monospace",
                textTransform: "uppercase",
              }}
            >
              Example
            </div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                flexWrap: "wrap",
              }}
            >
              <img
                src={`https://flagcdn.com/24x18/${example.iso2}.png`}
                alt={`${example.country} flag`}
                width={24}
                height={18}
                style={{ borderRadius: "2px", flexShrink: 0 }}
              />
              <span
                style={{ fontSize: "13px", color: "var(--qgi-text)", fontWeight: 600 }}
              >
                {example.country}
              </span>
              <span style={{ color: familyColor, fontWeight: 700 }}>→</span>
              <span style={{ fontSize: "13px", color: familyColor, fontWeight: 600 }}>
                {trendLower}
              </span>
            </div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                fontFamily: "ui-monospace, monospace",
                fontSize: "12px",
                color: "var(--qgi-text-muted)",
              }}
            >
              <span>{startYear}</span>
              <span
                style={{
                  flex: 1,
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  color: "var(--qgi-text-dim)",
                  minWidth: "70px",
                }}
              >
                <span
                  style={{ flex: 1, height: "1px", background: "var(--qgi-border)" }}
                />
                {windowYears}y
                <span
                  style={{ flex: 1, height: "1px", background: "var(--qgi-border)" }}
                />
                <span style={{ color: familyColor }}>→</span>
              </span>
              <span style={{ color: "var(--qgi-text)", fontWeight: 600 }}>
                {example.year}
              </span>
            </div>
            <div
              style={{ fontSize: "11px", lineHeight: 1.45, color: "var(--qgi-text-dim)" }}
            >
              {example.label}
            </div>
          </div>
        )}
      </div>
    </PanelBase>
  );
}

/* ───────── Identity card (merged with sample-size — #161 / Sofia 2026-05-27) ─── */
/*                                                                                  */
/* Founder #161: Sample-size sufficiency stops being a sibling panel; its           */
/* user-facing essence (real-world case count + an "is the recipe big enough        */
/* to be evaluated" yes/no) folds into Identity card. The "LOCO cohorts" tile       */
/* and the "≥60-pos" jargon are gone from visible copy. Threshold detail stays      */
/* in the tooltip for technical readers. R&D Q5 binding preserved.                  */

/** V4.1 §4: status labels map directly to the four audience-facing buckets.
 *  Validated / In play / Coming soon / Prior version — no methodology jargon. */
const STATUS_LABELS: Record<string, string> = {
  graduated: "Validated",
  walked_no_graduation: "In play",
  in_progress: "In play",
  queued: "Coming soon",
  retired: "Retired",
  live_legacy: "Prior version",
  // "vacated" is on the V4.1 banned-vocab list; surface as "In play" until
  // re-evaluation completes (the audit is happening; we keep the chip calm).
  vacated: "In play",
  in_validation: "In play",
};

function formatStatus(raw: string): string {
  if (STATUS_LABELS[raw]) return STATUS_LABELS[raw];
  const friendly = raw.replace(/_/g, " ").toLowerCase();
  return friendly.charAt(0).toUpperCase() + friendly.slice(1);
}

/** V4.1 polish 2026-05-29 (#23):
 *   - Drop the family-letter glyph from the Category tile (§1.2).
 *   - Rename "L1 family" → "Category", "L2 sub-class" → "Subcategory" (§1.3).
 *   - Drop the "Tracker vintage" tile entirely (§2; one stamp per session).
 *   - Status renders the V4.1 audience-facing label.
 *
 * `l1_id` was previously read for the breadcrumb-style prefix; we still
 * accept the prop (callers haven't been updated everywhere) but don't
 * render it. Marked deprecated. */
export function IdentityCardPanel({
  familyColor,
  l1_label,
  l2_label,
  nIndicators,
  status,
  nPositives,
  thresholdMet,
}: {
  familyColor: string;
  /** Deprecated 2026-05-29: family-letter glyph no longer rendered (§1.2). */
  l1_id?: string;
  l1_label: string;
  l2_label: string;
  nIndicators: number;
  status: string;
  /** Deprecated 2026-05-29: per-card vintage replaced by single header stamp. */
  vintage?: string;
  /** Curated count of documented real-world cases of this event. */
  nPositives: number;
  /** Whether the corpus is large enough for the recipe to be evaluated. */
  thresholdMet: boolean;
}) {
  const eligibleColor = thresholdMet ? "#3FBF8F" : "#7A8FA0";
  const eligibleLabel = thresholdMet ? "Ready to evaluate" : "Building the case corpus";
  return (
    <PanelBase
      title="Identity Card"
      familyColor={familyColor}
      titleTooltip="The trend's ID badge: where it sits in the taxonomy, how many signals it uses, where it stands today, and how many real-world cases are documented in its corpus."
      id="cap-5"
      dataTour="identity-card-panel"
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
          gap: "14px 18px",
        }}
      >
        <Field label="Category" value={l1_label} accent={familyColor} />
        <Field label="Subcategory" value={l2_label} />
        <Field label="Signals" value={String(nIndicators)} />
        <Field label="Status" value={formatStatus(status)} />
        <Field
          label="Documented cases"
          value={nPositives.toLocaleString()}
          inlineChip={
            <span
              title={
                thresholdMet
                  ? "The case corpus is large enough for a clean assessment."
                  : "We are still expanding the case corpus; the trend enters assessment when the corpus crosses the threshold."
              }
              style={{
                fontSize: "9.5px",
                letterSpacing: "0.6px",
                fontFamily: "ui-monospace, monospace",
                color: eligibleColor,
                border: `1px solid ${eligibleColor}`,
                borderRadius: "3px",
                padding: "1px 6px",
                textTransform: "uppercase",
                whiteSpace: "nowrap",
              }}
            >
              {eligibleLabel}
            </span>
          }
        />
      </div>
    </PanelBase>
  );
}

function Field({
  label,
  value,
  accent,
  inlineChip,
}: {
  label: string;
  value: string;
  accent?: string;
  inlineChip?: ReactNode;
}) {
  return (
    <div>
      <div
        style={{
          fontSize: "9.5px",
          letterSpacing: "0.7px",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
          marginBottom: "3px",
          textTransform: "uppercase",
        }}
      >
        {label}
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          flexWrap: "wrap",
        }}
      >
        <div
          style={{
            fontSize: "12.5px",
            color: accent ?? "var(--qgi-text)",
            fontWeight: 500,
            fontFamily: "ui-monospace, monospace",
          }}
        >
          {value}
        </div>
        {inlineChip}
      </div>
    </div>
  );
}

/* ───────── Discrimination (#156 polish — de-jargonized caption) ─────── */

export function DiscriminationPanel({
  familyColor,
  locoAuc,
  ciLow,
  ciHigh,
  lockFloor = 0.7986,
  showResults,
  cvAucFull,
}: {
  familyColor: string;
  locoAuc: number | null;
  ciLow?: number;
  ciHigh?: number;
  lockFloor?: number;
  showResults: boolean;
  /** Round-2: 5-fold CV AUC from scores file top-level. */
  cvAucFull?: number | null;
}) {
  const cleared = locoAuc !== null && locoAuc >= lockFloor;
  const chipColor = cleared ? "#3FBF8F" : "#E68F29";
  const distance = locoAuc !== null ? Math.abs(locoAuc - lockFloor) : 0;
  const verdictCopy = cleared
    ? `Above the validation threshold by ${distance.toFixed(3)}.`
    : `Below the validation threshold by ${distance.toFixed(3)}.`;
  return (
    <PanelBase
      title="Discrimination"
      familyColor={familyColor}
      titleTooltip={`Leave-One-Cohort-Out AUC: the trend is scored only on country groups it never trained on. The pre-registered validation threshold is ${lockFloor.toFixed(4)}; a trend must clear it to graduate.`}
      caption="Can this trend tell apart countries heading for the event from those that are not? Higher means a cleaner split. 0.50 is a coin toss."
      sectionPending={!showResults || locoAuc === null ? "discrimination" : null}
      id="cap-6"
      dataTour="discrimination-panel"
    >
      {showResults && locoAuc !== null && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "10px",
            marginTop: "2px",
          }}
        >
          <div style={{ display: "flex", alignItems: "flex-end", gap: "12px" }}>
            <span
              style={{
                fontSize: "56px",
                fontWeight: 700,
                color: chipColor,
                fontFamily: "ui-monospace, monospace",
                lineHeight: 0.95,
                letterSpacing: "-2px",
              }}
            >
              {locoAuc.toFixed(3)}
            </span>
            <span
              style={{
                fontSize: "11px",
                color: "var(--qgi-text-dim)",
                fontFamily: "ui-monospace, monospace",
                letterSpacing: "0.6px",
                paddingBottom: "10px",
                textTransform: "uppercase",
              }}
            >
              Discrimination score
            </span>
          </div>
          <p
            style={{
              fontSize: "12.5px",
              lineHeight: 1.55,
              color: "var(--qgi-text-muted)",
              margin: 0,
            }}
          >
            <span style={{ color: chipColor, fontWeight: 600 }}>{verdictCopy}</span>
            {ciLow !== undefined && ciHigh !== undefined && (
              <>
                {" "}
                <span style={{ color: "var(--qgi-text-dim)" }}>
                  95% confidence interval{" "}
                  <code
                    style={{
                      fontFamily: "ui-monospace, monospace",
                      color: "var(--qgi-text-muted)",
                    }}
                  >
                    [{ciLow.toFixed(3)}, {ciHigh.toFixed(3)}]
                  </code>
                  .
                </span>
              </>
            )}
          </p>
          {cvAucFull != null && (
            <p
              style={{
                fontSize: "11.5px",
                color: "var(--qgi-text-dim)",
                fontFamily: "ui-monospace, monospace",
                margin: "6px 0 0",
                letterSpacing: "0.3px",
              }}
            >
              5-fold CV: {cvAucFull.toFixed(3)}
            </p>
          )}
        </div>
      )}
    </PanelBase>
  );
}

/* ───────── Top scoring countries (deprecated — Talia's CountriesPanel replaces) ─── */

export function TopCountriesPanel({
  familyColor,
  countries,
  showResults,
}: {
  familyColor: string;
  countries: CountryScore[];
  showResults: boolean;
}) {
  return (
    <PanelBase
      title="Top scoring countries"
      familyColor={familyColor}
      titleTooltip="Top-10 by discrimination rank on this recipe."
      sectionPending={!showResults || countries.length === 0 ? "discrimination" : null}
      id="cap-8"
    >
      <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {countries.map((c, i) => (
          <li
            key={c.name}
            style={{
              display: "grid",
              gridTemplateColumns: "22px 18px minmax(0, 1fr) auto",
              gap: "8px",
              alignItems: "center",
              padding: "8px 0",
              borderBottom:
                i < countries.length - 1 ? "1px solid var(--qgi-border)" : "none",
            }}
          >
            <span
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "10.5px",
                color: "var(--qgi-text-dim)",
              }}
            >
              {i + 1}
            </span>
            <span style={{ fontSize: "15px", lineHeight: 1 }} aria-hidden>
              {flagFor(c.name)}
            </span>
            <span style={{ fontSize: "13px", color: "var(--qgi-text)" }}>{c.name}</span>
            <span
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "13px",
                color: familyColor,
                fontWeight: 700,
              }}
            >
              {c.score.toFixed(1)}
            </span>
          </li>
        ))}
      </ol>
    </PanelBase>
  );
}

export function BottomCountriesPanel({
  familyColor,
  countries,
  showResults,
}: {
  familyColor: string;
  countries: CountryScore[];
  showResults: boolean;
}) {
  return (
    <PanelBase
      title="Bottom scoring countries"
      familyColor={familyColor}
      titleTooltip="The lowest-scoring countries on this recipe: the structural negative space."
      sectionPending={!showResults || countries.length === 0 ? "discrimination" : null}
      id="cap-9"
    >
      <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {countries.map((c, i) => (
          <li
            key={c.name}
            style={{
              display: "grid",
              gridTemplateColumns: "22px 18px minmax(0, 1fr) auto",
              gap: "8px",
              alignItems: "center",
              padding: "8px 0",
              borderBottom:
                i < countries.length - 1 ? "1px solid var(--qgi-border)" : "none",
            }}
          >
            <span
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "10.5px",
                color: "var(--qgi-text-dim)",
              }}
            >
              {i + 1}
            </span>
            <span style={{ fontSize: "15px", lineHeight: 1 }} aria-hidden>
              {flagFor(c.name)}
            </span>
            <span style={{ fontSize: "13px", color: "var(--qgi-text)" }}>{c.name}</span>
            <span
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "13px",
                color: "var(--qgi-text-muted)",
                fontWeight: 700,
              }}
            >
              {c.score.toFixed(1)}
            </span>
          </li>
        ))}
      </ol>
    </PanelBase>
  );
}

/* ───────── Calibration ──────────────────────────────────────────────── */

export function CalibrationPanel({
  familyColor,
  showCalibrationData,
  ece,
}: {
  familyColor: string;
  showCalibrationData: boolean;
  ece?: number;
}) {
  return (
    <PanelBase
      title="Calibration"
      familyColor={familyColor}
      titleTooltip="Once the recipe graduates and clears the calibration threshold, the score in country panels flips from a rank to a calibrated probability interval (Venn-Abers, per cohort)."
      sectionPending={showCalibrationData ? null : "probability"}
      id="cap-11"
      dataTour="calibration-panel"
    >
      {showCalibrationData && ece !== undefined && (
        <div style={{ display: "flex", alignItems: "baseline", gap: "14px" }}>
          <div
            style={{
              fontSize: "48px",
              fontWeight: 700,
              color: familyColor,
              fontFamily: "ui-monospace, monospace",
              lineHeight: 1,
            }}
          >
            {ece.toFixed(3)}
          </div>
          <div
            style={{ fontSize: "12px", color: "var(--qgi-text-muted)", lineHeight: 1.5 }}
          >
            Expected Calibration Error (ECE).
            <br />
            Pre-registered threshold: ECE ≤ 0.08.
          </div>
        </div>
      )}
    </PanelBase>
  );
}
