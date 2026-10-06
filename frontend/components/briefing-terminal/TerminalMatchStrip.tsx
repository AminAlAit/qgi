/**
 * TerminalMatchStrip — §4: horizontally scrollable match tile row (ON RADAR).
 *
 * Renders like a Bloomberg security ticker — flex row, overflow-x auto.
 * Server shell; TerminalMatchTile is also server (score coloring only).
 */
import { TerminalMatchTile, type TerminalMatchTileData } from "./TerminalMatchTile";

export interface TerminalMatchStripProps {
  matches: TerminalMatchTileData[];
}

export function TerminalMatchStrip({ matches }: TerminalMatchStripProps) {
  if (matches.length === 0) return null;

  return (
    <section style={{ marginBottom: "8px" }}>
      <style>{`
        .qgi-match-tile:hover {
          transform: translateY(-2px);
          box-shadow: 0 6px 18px rgba(0,0,0,0.32);
        }
        .qgi-match-strip::-webkit-scrollbar {
          height: 4px;
        }
        .qgi-match-strip::-webkit-scrollbar-track {
          background: var(--qgi-bg);
        }
        .qgi-match-strip::-webkit-scrollbar-thumb {
          background: var(--qgi-border);
          border-radius: 2px;
        }
      `}</style>
      {/* Section header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          marginBottom: "8px",
        }}
      >
        <span
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "9px",
            fontWeight: 700,
            letterSpacing: "2px",
            textTransform: "uppercase",
            color: "var(--qgi-text-dim)",
          }}
        >
          On Radar
        </span>
        <span
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "9px",
            color: "var(--qgi-text-dim)",
          }}
        >
          · {matches.length} active matches
        </span>
      </div>
      {/* Horizontal scroll strip */}
      <div
        className="qgi-match-strip"
        style={{
          display: "flex",
          overflowX: "auto",
          gap: "6px",
          paddingBottom: "6px",
          scrollbarWidth: "thin",
        }}
      >
        {matches.map((m) => (
          <TerminalMatchTile key={`${m.recipe_id}-${m.iso2}`} m={m} />
        ))}
      </div>
    </section>
  );
}
