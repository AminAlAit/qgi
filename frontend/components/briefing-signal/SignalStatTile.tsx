/**
 * SignalStatTile — single big-number stat tile used inside HeroSplit.
 * Server component.
 */

interface Props {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  accentColor: string;
  bgTint?: string;
  isFirst?: boolean;
  isLast?: boolean;
}

export function SignalStatTile({
  label,
  value,
  unit,
  sub,
  accentColor,
  bgTint,
  isFirst = false,
  isLast = false,
}: Props) {
  const radius = isFirst ? "6px 0 0 6px" : isLast ? "0 6px 6px 0" : "0";
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "3px",
        padding: "10px 14px",
        minWidth: "90px",
        background: bgTint ?? "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderLeft: isFirst ? `3px solid ${accentColor}` : "none",
        borderRadius: radius,
      }}
    >
      <span
        style={{
          fontSize: "11px",
          fontFamily: "ui-monospace, monospace",
          letterSpacing: "1.2px",
          textTransform: "uppercase",
          color: "var(--qgi-text-dim)",
        }}
      >
        {label}
      </span>
      <div style={{ display: "flex", alignItems: "baseline", gap: "2px" }}>
        <span
          style={{
            fontSize: "clamp(22px, 2.5vw, 30px)",
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
          }}
        >
          {sub}
        </span>
      )}
    </div>
  );
}
