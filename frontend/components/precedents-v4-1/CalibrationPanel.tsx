/**
 * CalibrationPanel — V4.1, #160 polish (standalone file).
 *
 * Standalone deliverable from Talia (2026-05-27) for integrator to swap
 * into MinorPanels' export site. Sofia is editing MinorPanels.tsx in
 * parallel for the IdentityCard merge, so the polished Calibration
 * surface ships as its own file to avoid edit collisions.
 *
 *
 * What's polished
 * ───────────────
 *   - When populated: the "ECE" abbreviation is expanded inline to
 *     "Expected Calibration Error", with a one-sentence plain-English
 *     gloss: how close the recipe's score numbers are to actual
 *     frequencies (i.e. when the recipe says "0.8", does the event
 *     happen 80% of the time in similar countries?). Lower = closer.
 *   - A small horizontal threshold bar visualizes where the current
 *     ECE sits relative to the pre-registered 0.08 cut: green chip
 *     when at or below the threshold, amber when above. The bar
 *     surfaces the gap immediately without a second click.
 *   - Pending state unchanged — the "Awaiting probability tuning"
 *     surface stays exactly as Sofia left it (PanelBase sectionPending
 *     prop).
 *
 *
 * What's NOT polished (deliberate)
 * ────────────────────────────────
 *   - Title text and PanelBase title-tooltip are unchanged. The
 *     tooltip wording ("calibration threshold") is already adequate
 *     for the title-hover surface; the in-panel explanation is the
 *     friendly layer.
 *   - Threshold value (0.08) is hard-coded to match the current pre-
 *     reg. When the bake JSON ships per-recipe thresholds we wire
 *     them via a prop; signature stays the same and the integrator
 *     can add `thresholdEce?: number` without breaking callers.
 */
import { PanelBase } from "./PanelBase";

const THRESHOLD_ECE = 0.08;
/** Visual scale for the threshold bar — anything beyond 2× the threshold
 *  pegs to the right edge so very-bad ECEs don't push the bar offscreen. */
const BAR_DOMAIN_MAX = THRESHOLD_ECE * 2;

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
      titleTooltip="Once the trend graduates and clears the calibration threshold, the score in country panels flips from a rank to a calibrated probability interval (Venn-Abers, per cohort)."
      caption="Is the score honest? This checks whether the numbers line up with how often the event actually happens."
      sectionPending={showCalibrationData ? null : "probability"}
      id="cap-11"
      dataTour="calibration-panel"
    >
      {showCalibrationData && ece !== undefined && (
        <CalibrationBody ece={ece} familyColor={familyColor} />
      )}
    </PanelBase>
  );
}

function CalibrationBody({ ece, familyColor }: { ece: number; familyColor: string }) {
  const cleared = ece <= THRESHOLD_ECE;
  const chipColor = cleared ? "#3FBF8F" : "#E68F29";
  const verdictLabel = cleared ? "Within threshold" : "Above threshold";

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "14px",
        marginTop: "2px",
      }}
    >
      {/* Headline number + verdict chip + abbreviation expansion */}
      <div style={{ display: "flex", alignItems: "flex-end", gap: "14px" }}>
        <span
          style={{
            fontSize: "48px",
            fontWeight: 700,
            color: chipColor,
            fontFamily: "ui-monospace, monospace",
            lineHeight: 0.95,
            letterSpacing: "-1.5px",
          }}
        >
          {ece.toFixed(3)}
        </span>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "4px",
            paddingBottom: "6px",
          }}
        >
          <span
            style={{
              fontSize: "10.5px",
              color: "var(--qgi-text-muted)",
              fontFamily: "ui-monospace, monospace",
              letterSpacing: "0.4px",
              textTransform: "uppercase",
            }}
          >
            Expected Calibration Error
          </span>
          <span
            style={{
              fontSize: "9.5px",
              letterSpacing: "0.6px",
              fontFamily: "ui-monospace, monospace",
              color: chipColor,
              border: `1px solid ${chipColor}`,
              borderRadius: "3px",
              padding: "1px 6px",
              textTransform: "uppercase",
              whiteSpace: "nowrap",
              alignSelf: "flex-start",
            }}
          >
            {verdictLabel}
          </span>
        </div>
      </div>

      {/* Plain-English explanation */}
      <p
        style={{
          fontSize: "12px",
          lineHeight: 1.55,
          color: "var(--qgi-text-muted)",
          margin: 0,
        }}
      >
        When the trend says &ldquo;0.8&rdquo;, does the event follow about 80% of the time
        in similar countries? Expected Calibration Error is the gap between the score and
        what actually happens; lower means a closer match.
      </p>

      {/* Threshold bar */}
      <ThresholdBar
        ece={ece}
        threshold={THRESHOLD_ECE}
        chipColor={chipColor}
        familyColor={familyColor}
      />
    </div>
  );
}

/**
 * Horizontal bar from 0 to BAR_DOMAIN_MAX (default 0.16 = 2× threshold).
 * A vertical tick marks the pre-registered threshold (0.08); the current
 * ECE is a filled chevron sitting on the bar. Color matches the verdict
 * chip so the eye reads "green = good, amber = above bar" instantly.
 */
function ThresholdBar({
  ece,
  threshold,
  chipColor,
  familyColor: _familyColor,
}: {
  ece: number;
  threshold: number;
  chipColor: string;
  familyColor: string;
}) {
  const W = 280;
  const H = 28;
  const PAD_L = 4;
  const PAD_R = 4;
  const trackY = 14;
  const trackH = 5;
  const trackW = W - PAD_L - PAD_R;
  const clipped = Math.min(BAR_DOMAIN_MAX, Math.max(0, ece));
  const xForVal = (v: number) =>
    PAD_L + (Math.min(BAR_DOMAIN_MAX, v) / BAR_DOMAIN_MAX) * trackW;
  const xEce = xForVal(clipped);
  const xThresh = xForVal(threshold);

  return (
    <div style={{ width: "100%" }}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: "100%", maxWidth: `${W}px`, height: "auto", display: "block" }}
        role="img"
        aria-label={`Calibration error ${ece.toFixed(3)} relative to threshold ${threshold.toFixed(2)}`}
      >
        {/* Track: green-tinted on the cleared side, amber-tinted on the above side */}
        <rect
          x={PAD_L}
          y={trackY}
          width={xThresh - PAD_L}
          height={trackH}
          rx={1.5}
          fill="#3FBF8F"
          fillOpacity={0.18}
        />
        <rect
          x={xThresh}
          y={trackY}
          width={PAD_L + trackW - xThresh}
          height={trackH}
          rx={1.5}
          fill="#E68F29"
          fillOpacity={0.18}
        />
        <rect
          x={PAD_L}
          y={trackY}
          width={trackW}
          height={trackH}
          rx={1.5}
          fill="none"
          stroke="var(--qgi-border)"
          strokeWidth={0.5}
        />

        {/* Threshold tick */}
        <line
          x1={xThresh}
          x2={xThresh}
          y1={trackY - 4}
          y2={trackY + trackH + 4}
          stroke="var(--qgi-text-dim)"
          strokeWidth={1}
          strokeDasharray="2 2"
        />
        <text
          x={xThresh}
          y={trackY - 6}
          fontSize={8.5}
          fill="var(--qgi-text-dim)"
          textAnchor="middle"
          fontFamily="ui-monospace, monospace"
        >
          threshold {threshold.toFixed(2)}
        </text>

        {/* Current ECE marker — filled circle sitting on the bar */}
        <circle
          cx={xEce}
          cy={trackY + trackH / 2}
          r={4}
          fill={chipColor}
          stroke="var(--qgi-bg)"
          strokeWidth={1.25}
        />
      </svg>
    </div>
  );
}
