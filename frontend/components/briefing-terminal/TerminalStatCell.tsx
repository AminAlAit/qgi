/**
 * TerminalStatCell — tightly-sized stat readout (value / label / unit).
 *
 * Used in the hero panel stat mosaic. Left-border accent, no outer radius
 * on inner cells, value at clamp(28px, 3.2vw, 40px), label at 9px monospace.
 */
export interface TerminalStatCellProps {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  accentColor: string;
  bgTint?: string;
  isFirst?: boolean;
  isLast?: boolean;
}

export function TerminalStatCell({
  label,
  value,
  unit,
  sub,
  accentColor,
  bgTint,
  isFirst = false,
  isLast = false,
}: TerminalStatCellProps) {
  const radius = isFirst ? "4px 0 0 4px" : isLast ? "0 4px 4px 0" : "0";
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "3px",
        padding: "8px 12px",
        background: bgTint ?? "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderLeft: isFirst ? `3px solid ${accentColor}` : "none",
        borderRadius: radius,
        minWidth: "80px",
      }}
    >
      <span
        style={{
          fontSize: "9px",
          fontFamily: "ui-monospace, monospace",
          letterSpacing: "1.8px",
          textTransform: "uppercase",
          color: "var(--qgi-text-dim)",
        }}
      >
        {label}
      </span>
      <div style={{ display: "flex", alignItems: "baseline", gap: "2px" }}>
        <span
          style={{
            fontSize: "clamp(22px, 3.2vw, 36px)",
            fontWeight: 700,
            fontFamily: "ui-monospace, monospace",
            fontVariantNumeric: "tabular-nums",
            letterSpacing: "-0.5px",
            color: "var(--qgi-text)",
            lineHeight: 1,
          }}
        >
          {value}
        </span>
        {unit && (
          <span
            style={{
              fontSize: "11px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            {unit}
          </span>
        )}
      </div>
      {sub && (
        <span
          style={{
            fontSize: "10px",
            fontFamily: "ui-monospace, monospace",
            color: accentColor,
            letterSpacing: "0.2px",
            marginTop: "1px",
          }}
        >
          {sub}
        </span>
      )}
    </div>
  );
}
