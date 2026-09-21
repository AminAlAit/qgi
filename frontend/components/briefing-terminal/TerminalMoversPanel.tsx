/**
 * TerminalMoversPanel — §3-left: rising + falling dual columns.
 *
 * Raw terminal panel (no PanelBase wrapper). Red top border.
 * 4 risers + up to 2 fallers. Server component.
 */
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";

export interface MoverRow {
  key: string;
  countryName: string;
  topicLabel: string;
  delta: number;
  pulse: number;
  struct: number;
  direction: "rising" | "falling";
}

export interface TerminalMoversPanelProps {
  risers: MoverRow[];
  fallers: MoverRow[];
}

function MoverItem({ row }: { row: MoverRow }) {
  const isRising = row.direction === "rising";
  const color = isRising ? "#E05C5C" : "#5B7E99";
  const deltaStr = isRising
    ? `+${Math.round(row.delta)} ↑`
    : `${Math.round(row.delta)} ↓`;
  const barWidth = Math.max(2, Math.round((Math.abs(row.delta) / 50) * 60));

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "7px",
        padding: "6px 0",
        borderBottom: "1px solid var(--qgi-border)",
      }}
    >
      <FlagImg
        emoji={flagFor(row.countryName)}
        name={row.countryName}
        width={14}
        radius={2}
      />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "11px",
            color: "var(--qgi-text)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {row.countryName}
        </div>
        <div
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "9px",
            color: "var(--qgi-text-dim)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {row.topicLabel}
        </div>
        {/* Mini inline bar */}
        <div
          style={{
            marginTop: "3px",
            height: "3px",
            width: `${barWidth}px`,
            background: color,
            borderRadius: "2px",
            opacity: 0.7,
          }}
        />
      </div>
      <span
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: "11px",
          fontWeight: 700,
          color,
          flexShrink: 0,
        }}
      >
        {deltaStr}
      </span>
    </div>
  );
}

export function TerminalMoversPanel({ risers, fallers }: TerminalMoversPanelProps) {
  const topRisers = risers.slice(0, 4);
  const topFallers = fallers.slice(0, 2);

  return (
    <div
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderTop: "2px solid #E05C5C",
        borderRadius: "4px",
        padding: "12px 14px",
      }}
    >
      <span
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: "9px",
          fontWeight: 700,
          letterSpacing: "1.8px",
          textTransform: "uppercase",
          color: "var(--qgi-text-dim)",
          display: "block",
          marginBottom: "8px",
        }}
      >
        Pulse Movers
      </span>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "0 16px",
        }}
      >
        {/* Risers column */}
        <div>
          <span
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: "10px",
              letterSpacing: "1px",
              textTransform: "uppercase",
              color: "#E05C5C",
              display: "block",
              marginBottom: "4px",
            }}
          >
            Rising
          </span>
          {topRisers.map((r) => (
            <MoverItem key={r.key} row={r} />
          ))}
        </div>
        {/* Fallers column */}
        <div>
          <span
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: "10px",
              letterSpacing: "1px",
              textTransform: "uppercase",
              color: "#5B7E99",
              display: "block",
              marginBottom: "4px",
            }}
          >
            Falling
          </span>
          {topFallers.map((r) => (
            <MoverItem key={r.key} row={r} />
          ))}
        </div>
      </div>
    </div>
  );
}
