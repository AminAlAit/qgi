/**
 * TerminalScopeInstrument — §5-right: scope stats readout.
 *
 * Terminal readout format — each stat on its own labeled row.
 * Labels dim, values bold. Amber emphasis on TRENDS {inPlayCount} IN PLAY.
 * Vintage stamp at bottom. Server component.
 */
import { TerminalPanelShell } from "./TerminalPanelShell";

export interface TerminalScopeInstrumentProps {
  recipesTotal: number;
  inPlayCount: number;
  familyCount: number;
  indicatorsTracked: number;
  vintageStampStr: string;
  /** Derived from buildHeroCountsV41 — never hardcoded. */
  countriesScored: number;
}

function StatRow({
  label,
  value,
  accentValue,
}: {
  label: string;
  value: string;
  accentValue?: boolean;
}) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "baseline",
        gap: "8px",
        padding: "4px 0",
        borderBottom: "1px solid rgba(42,58,74,0.4)",
      }}
    >
      <span
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: "11px",
          color: "var(--qgi-text-dim)",
          letterSpacing: "0.8px",
          textTransform: "uppercase",
        }}
      >
        {label}
      </span>
      <span
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: "11px",
          fontWeight: 700,
          color: accentValue ? "var(--qgi-amber, #F59E0B)" : "var(--qgi-text)",
          letterSpacing: "-0.3px",
        }}
      >
        {value}
      </span>
    </div>
  );
}

export function TerminalScopeInstrument({
  recipesTotal,
  inPlayCount,
  familyCount,
  indicatorsTracked,
  vintageStampStr,
  countriesScored,
}: TerminalScopeInstrumentProps) {
  return (
    <TerminalPanelShell title="Instrument" accent="#7B5EE6" style={{ height: "100%" }}>
      <div style={{ display: "flex", flexDirection: "column" }}>
        <StatRow label="Countries" value={String(countriesScored)} />
        <StatRow label="Trends" value={String(recipesTotal)} />
        <StatRow label="In Play" value={String(inPlayCount)} accentValue />
        <StatRow label="Families" value={String(familyCount)} />
        <StatRow label="Signals" value={String(indicatorsTracked)} />
        <StatRow label="Refresh" value="QUARTERLY" />
      </div>
      <div style={{ marginTop: "12px" }}>
        <span
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "9px",
            color: "var(--qgi-text-dim)",
            letterSpacing: "0.4px",
          }}
          title={`v${vintageStampStr}`}
        >
          Updated: {vintageStampStr.slice(0, 10)}
        </span>
      </div>
    </TerminalPanelShell>
  );
}
