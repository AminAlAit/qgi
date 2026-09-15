/**
 * PatternSectorBreakdown — §3 Sector composition chip strip.
 *
 * Kicker: COMPOSITION
 * Heading: "What drove the resemblance"
 * Body: horizontal chip strip, one chip per sector present in the indicator
 * list. Each chip shows sector name + indicator count in that sector.
 * Chip background tinted from sector-colors.ts.
 *
 * Server component (no state, no interactivity).
 */
import type { PatternIndicator } from "@/lib/cascade-patterns/scdi-mock";
import { sectorColor } from "@/lib/cascade-patterns/sector-colors";

interface PatternSectorBreakdownProps {
  indicators: PatternIndicator[];
}

export function PatternSectorBreakdown({ indicators }: PatternSectorBreakdownProps) {
  // Aggregate by sector.
  const counts: Record<string, number> = {};
  for (const ind of indicators) {
    counts[ind.sector] = (counts[ind.sector] ?? 0) + 1;
  }
  // Sort by count desc.
  const sectors = Object.entries(counts).sort((a, b) => b[1] - a[1]);

  return (
    <div
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "10px",
        padding: "20px 22px",
        marginBottom: "20px",
      }}
    >
      <div
        style={{
          fontSize: "9px",
          letterSpacing: "1.6px",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
          marginBottom: "6px",
          fontWeight: 600,
        }}
      >
        COMPOSITION
      </div>
      <h2
        style={{
          fontSize: "15px",
          fontWeight: 700,
          margin: "0 0 14px",
          color: "var(--qgi-text)",
        }}
      >
        What drove the resemblance
      </h2>

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "8px",
        }}
      >
        {sectors.map(([sector, count]) => {
          const color = sectorColor(sector);
          return (
            <div
              key={sector}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                padding: "5px 10px 5px 8px",
                borderRadius: "20px",
                background: `${color}18`,
                border: `1px solid ${color}40`,
                fontSize: "12px",
                color: "var(--qgi-text-muted)",
                fontFamily: "ui-monospace, monospace",
              }}
            >
              {/* Sector color dot */}
              <span
                style={{
                  display: "inline-block",
                  width: "8px",
                  height: "8px",
                  borderRadius: "50%",
                  background: color,
                  flexShrink: 0,
                }}
              />
              <span style={{ fontWeight: 600, color: "var(--qgi-text)" }}>{sector}</span>
              <span style={{ opacity: 0.7 }}>
                {count} indicator{count !== 1 ? "s" : ""}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
