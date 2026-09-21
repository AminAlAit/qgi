/**
 * TerminalMiniCard — flag + country + topic + dual verdict pill row.
 *
 * Used in signal-state panel (§2-A) and anywhere a compact country-topic
 * entry needs a verdict-colored left border. Server component.
 */
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";

export interface TerminalMiniCardProps {
  countryName: string;
  topicLabel: string;
  pulse: number;
  struct: number;
  verdict: "ACTIVE" | "SIGNAL" | "LATENT" | "QUIET";
}

const VERDICT_COLOR: Record<string, string> = {
  ACTIVE: "#E05C5C",
  SIGNAL: "var(--qgi-amber)",
  LATENT: "#5B7E99",
  QUIET: "var(--qgi-text-dim)",
};

export function TerminalMiniCard({
  countryName,
  topicLabel,
  pulse,
  struct,
  verdict,
}: TerminalMiniCardProps) {
  const vColor = VERDICT_COLOR[verdict] ?? "var(--qgi-text-dim)";
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "4px",
        padding: "8px 10px",
        background: "var(--qgi-bg)",
        border: "1px solid var(--qgi-border)",
        borderLeft: `3px solid ${vColor}`,
        borderRadius: "3px",
      }}
    >
      {/* Line 1: flag + country */}
      <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
        <FlagImg emoji={flagFor(countryName)} name={countryName} width={14} radius={2} />
        <span
          style={{
            fontSize: "11px",
            fontFamily: "ui-monospace, monospace",
            fontWeight: 600,
            color: "var(--qgi-text)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {countryName}
        </span>
      </div>
      {/* Line 2: topic */}
      <span
        style={{
          fontSize: "10px",
          fontFamily: "ui-monospace, monospace",
          color: "var(--qgi-text-muted)",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {topicLabel}
      </span>
      {/* Line 3: dual pill */}
      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
        <PulsePill label="PULSE" value={Math.round(pulse)} color={vColor} />
        <PulsePill
          label="STRUCT"
          value={Math.round(struct)}
          color="var(--qgi-text-dim)"
        />
      </div>
    </div>
  );
}

function PulsePill({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <span
      style={{
        fontFamily: "ui-monospace, monospace",
        fontSize: "9px",
        color: "var(--qgi-text-muted)",
        letterSpacing: "0.5px",
      }}
    >
      {label} <span style={{ color, fontWeight: 700 }}>{value}</span>
    </span>
  );
}
