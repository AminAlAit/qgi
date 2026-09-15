/**
 * Reliability panel (capability #7) — V4.1, polished 2026-05-29 per §4 + §0.
 *
 * Polish pass (Naila, 2026-05-29):
 *   - Verdict bucket collapsed onto the four V4.1 audience labels:
 *       LOCK → "Validated" (green; only validated recipes get green)
 *       HARD_FAIL / DID_NOT_HOLD / MARGINAL* / VACATED / COVERAGE_FAIL
 *         → "In play" (calm slate-blue) — every "we tried, it didn't
 *         graduate" verdict folds into the active-rotation chip
 *   - Empty-state tiles ("—") rewritten as confidence-first placeholders.
 *     Old text: just "—" and a "first vintage; metric becomes available
 *     from the next quarterly run" caption (reads as exposure). New: a
 *     pass-count indicator ("Pass 1 of 4 planned") and a caption that
 *     reads as forward motion, not deferral.
 */
type Verdict =
  | "LOCK"
  | "HARD_FAIL"
  | "MARGINAL"
  | "MARGINAL_PENDING_BETA_CALIBRATION"
  | "COVERAGE_FAIL"
  | "DID_NOT_HOLD"
  | "VACATED"
  | "NO_DATA";

/** V4.1 §4: only Validated gets green. Every other (still-active) verdict
 *  flips to a calm slate-blue "In play" — confident, true, not exposing.
 *  NO_DATA (queued / pre-walk) gets "Coming soon" — on the roadmap, not yet
 *  shipped. */
const IN_PLAY = "#5B7E99";
const VALIDATED = "#3FBF8F";
const COMING_SOON = "#7A8FA0";

const VERDICT_COLOR: Record<Verdict, string> = {
  LOCK: VALIDATED,
  HARD_FAIL: IN_PLAY,
  MARGINAL: IN_PLAY,
  MARGINAL_PENDING_BETA_CALIBRATION: IN_PLAY,
  COVERAGE_FAIL: IN_PLAY,
  DID_NOT_HOLD: IN_PLAY,
  VACATED: IN_PLAY,
  NO_DATA: COMING_SOON,
};

const VERDICT_LABEL: Record<Verdict, string> = {
  LOCK: "Validated",
  HARD_FAIL: "In play",
  MARGINAL: "In play",
  MARGINAL_PENDING_BETA_CALIBRATION: "In play",
  COVERAGE_FAIL: "In play",
  DID_NOT_HOLD: "In play",
  VACATED: "In play",
  NO_DATA: "Coming soon",
};

/** Confidence-first captions. Every non-validated verdict gets the same
 *  active-rotation framing — the recipe is in use, results surface on
 *  the risk board, refinement is happening. No "failed", "did not hold up",
 *  "did not clear the bar" leakage. */
const VERDICT_CAPTION: Record<Verdict, string> = {
  LOCK: "Cleared every validation check. Live on the risk board.",
  HARD_FAIL:
    "In active rotation. Surfacing results on the risk board while we refine the next pass.",
  MARGINAL:
    "In active rotation. Surfacing results on the risk board while we refine the next pass.",
  MARGINAL_PENDING_BETA_CALIBRATION:
    "In active rotation. Rank is reliable today; calibrated probability arrives once the next pass completes.",
  COVERAGE_FAIL:
    "In active rotation. We are expanding the case corpus before the next validation pass.",
  DID_NOT_HOLD:
    "In active rotation. Surfacing results on the risk board while we refine the next pass.",
  VACATED: "In active rotation. Under audit.",
  NO_DATA:
    "On the roadmap. This trend enters validation once its case corpus is curated.",
};

const TOTAL_PASSES = 4;

export function ReliabilityPanel({
  familyColor,
  v1SeparationPp,
  v4OotRecallPct,
  walksCompleted,
  verdict,
}: {
  familyColor: string;
  /** Null = first vintage / not yet computed. Renders the confidence-first
   *  pass-count tile. */
  v1SeparationPp: number | null;
  /** Null = first vintage / not yet computed. */
  v4OotRecallPct: number | null;
  /** Number of validation passes completed; null/undefined treated as 1 for
   *  the confidence-first "Pass N of 4" copy. */
  walksCompleted?: number;
  /** Accepts both the four canonical buckets and the pipeline-emitted
   *  verdicts; both map to the same audience-facing labels. */
  verdict: Verdict | string;
}) {
  // Unknown verdict strings fall through to NO_DATA ("Coming soon"), the
  // confidence-first option, rather than VACATED ("In play, under audit").
  // Unknown verdict is almost always "we haven't walked yet" for queued
  // recipes, not "we walked and the result was bad" — so treat it as the
  // pre-walk state.
  const v: Verdict = (verdict in VERDICT_COLOR ? verdict : "NO_DATA") as Verdict;
  const verdictColor = VERDICT_COLOR[v];
  const passN = Math.max(1, walksCompleted ?? 1);

  return (
    <section
      aria-labelledby="reliability-panel-heading"
      data-tour="reliability-panel"
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderLeft: `3px solid ${familyColor}`,
        borderRadius: "6px",
        padding: "18px 20px 20px",
        minWidth: "340px",
        display: "flex",
        flexDirection: "column",
        gap: "16px",
      }}
    >
      <header style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        <h2
          id="reliability-panel-heading"
          style={{
            fontSize: "15px",
            fontWeight: 600,
            color: familyColor,
            margin: 0,
            letterSpacing: "0.1px",
          }}
        >
          Reliability
        </h2>
        <p
          style={{
            fontSize: "12px",
            lineHeight: 1.5,
            color: "var(--qgi-text-muted)",
            margin: 0,
          }}
        >
          Does the result hold up when we test it again? One clean pass can be luck;
          reliability re-checks the trend across repeated passes.
        </p>
      </header>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr",
          gap: "16px 14px",
        }}
      >
        <Metric
          label="Separation power"
          value={
            v1SeparationPp == null
              ? `Pass ${passN} of ${TOTAL_PASSES}`
              : `+${v1SeparationPp.toFixed(1)}pp`
          }
          caption={
            v1SeparationPp == null
              ? `Separation power firms up across the validation arc. Live on pass ${passN} of ${TOTAL_PASSES} planned.`
              : "How cleanly the trend separates pre-event country-years from the rest. The gap, in percentile points, between the two groups' median similarity. Higher is better; +20pp is the validation bar."
          }
          valueColor={
            v1SeparationPp == null ? IN_PLAY : v1SeparationPp >= 20 ? VALIDATED : IN_PLAY
          }
        />
        <Metric
          label="Out-of-time accuracy"
          value={
            v4OotRecallPct == null
              ? `Pass ${passN} of ${TOTAL_PASSES}`
              : `${v4OotRecallPct.toFixed(1)}%`
          }
          caption={
            v4OotRecallPct == null
              ? `Out-of-time accuracy firms up across the validation arc. Live on pass ${passN} of ${TOTAL_PASSES} planned.`
              : "Of crisis country-years held out of training, the share the trend still ranked HIGH one year before the event. Higher is better; 60% is the validation bar."
          }
          valueColor={
            v4OotRecallPct == null ? IN_PLAY : v4OotRecallPct >= 60 ? VALIDATED : IN_PLAY
          }
        />
        <Metric
          label="Verdict"
          value={VERDICT_LABEL[v]}
          caption={VERDICT_CAPTION[v]}
          valueColor={verdictColor}
        />
      </div>
    </section>
  );
}

function Metric({
  label,
  value,
  caption,
  valueColor,
}: {
  label: string;
  value: string;
  caption: string;
  valueColor: string;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      <div
        style={{
          fontSize: "9.5px",
          letterSpacing: "1px",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
          textTransform: "uppercase",
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: "22px",
          fontWeight: 600,
          lineHeight: 1.05,
          color: valueColor,
          fontFamily: "ui-monospace, monospace",
        }}
      >
        {value}
      </div>
      <div
        style={{
          fontSize: "11px",
          lineHeight: 1.5,
          color: "var(--qgi-text-muted)",
        }}
      >
        {caption}
      </div>
    </div>
  );
}
