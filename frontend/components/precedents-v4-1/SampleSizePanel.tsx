/**
 * Sample-size sufficiency panel (capability #4) — V4.1, #138.
 *
 * Three small metric chips with plain-English captions directly beneath each.
 * Variable indicator count handled upstream; this panel reports event counts.
 */
export function SampleSizePanel({
  familyColor,
  nPositives,
  nCohorts,
  thresholdMet,
  threshold,
}: {
  familyColor: string;
  nPositives: number;
  nCohorts: number;
  thresholdMet: boolean;
  threshold: number;
}) {
  return (
    <section
      aria-labelledby="sample-size-panel-heading"
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
      <header>
        <h3
          id="sample-size-panel-heading"
          style={{
            fontSize: "15px",
            fontWeight: 600,
            color: familyColor,
            margin: 0,
            letterSpacing: "0.1px",
          }}
        >
          Sample-size sufficiency
        </h3>
      </header>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "14px" }}>
        <Metric
          label="Verified positives"
          value={nPositives.toLocaleString()}
          caption={`How many real-world cases of this event we've documented for the recipe to learn from. The threshold of ${threshold} must be met before any walk fires.`}
          familyColor={familyColor}
        />
        <Metric
          label="LOCO cohorts"
          value={String(nCohorts)}
          caption="Leave-One-Cohort-Out folds the verified positives are split into for honest discrimination scoring."
          familyColor={familyColor}
        />
        <Metric
          label={`≥${threshold}-pos threshold`}
          value={thresholdMet ? "Met" : "Not met"}
          caption={
            thresholdMet
              ? `${nPositives.toLocaleString()} ≥ ${threshold}. The recipe is eligible for a walk.`
              : `${nPositives.toLocaleString()} < ${threshold}. The recipe stays in the queue until more verified cases are curated.`
          }
          familyColor={familyColor}
          valueColor={thresholdMet ? "#3FBF8F" : "#E68F29"}
        />
      </div>
    </section>
  );
}

function Metric({
  label,
  value,
  caption,
  familyColor,
  valueColor,
}: {
  label: string;
  value: string;
  caption: string;
  familyColor: string;
  valueColor?: string;
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
          lineHeight: 1,
          color: valueColor ?? familyColor,
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
