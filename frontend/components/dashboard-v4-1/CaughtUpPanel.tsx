/**
 * CaughtUpPanel — news coverage catching up to structural signal.
 *
 * Two sections in one panel (one conceptual story: "the news is confirming
 * structure"):
 *
 *   Section A — "News crossed structural threshold this month": cells where
 *               pulse just crossed 80% of struct for the first time this
 *               vintage (prev was below the floor, current is above it).
 *
 *   Section B — "At a decade high": cells where current pulse is at or above
 *               95% of their all-time historical max (from the 2015-present
 *               pulse-detail series).
 *
 * V4.1 framing: "news coverage catching up to structural signal" — not a
 * prediction claim, but a structural lens on historical resemblance.
 *
 * Server component. No "use client".
 */
import Link from "next/link";
import type { Route } from "next";
import { PanelBase } from "./PanelBase";
import type { CaughtUpCell, HistoricHighCell } from "@/lib/dashboard/briefing-insights";
import type { HfVerdict } from "@/lib/hf/topics-data";

const VERDICT_COLOR: Record<HfVerdict, string> = {
  ACTIVE: "#E05C5C",
  SIGNAL: "#f59e0b",
  LATENT: "#5B7E99",
  QUIET: "var(--qgi-text-dim)",
};

interface Props {
  cells: CaughtUpCell[];
  historicHighs: HistoricHighCell[];
}

export function CaughtUpPanel({ cells, historicHighs }: Props) {
  if (cells.length === 0 && historicHighs.length === 0) return null;

  const rightSlot = (
    <Link
      href={"/risk-board" as Route}
      style={{
        fontSize: "11px",
        color: "var(--qgi-accent)",
        textDecoration: "none",
        fontFamily: "ui-monospace, monospace",
        letterSpacing: "0.3px",
        whiteSpace: "nowrap",
      }}
    >
      Full board →
    </Link>
  );

  return (
    <PanelBase
      title="News coverage catching up to structural signal"
      caption="Where news intensity just converged on structural resemblance — or hit a decade high. Resemblance and precedent, not forecasts."
      accent="#C9A84C"
      rightSlot={rightSlot}
    >
      {/* Section A: Crossed the structural threshold this month */}
      {cells.length > 0 && (
        <div style={{ marginBottom: historicHighs.length > 0 ? "0" : "0" }}>
          <div
            style={{
              fontSize: "10px",
              fontFamily: "ui-monospace, monospace",
              textTransform: "uppercase",
              letterSpacing: "1.5px",
              color: "#C9A84C",
              marginBottom: "10px",
            }}
          >
            Crossed structural threshold this month
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {cells.map((cell) => (
              <CaughtUpRow key={cell.key} cell={cell} />
            ))}
          </div>
        </div>
      )}

      {/* Divider between sections */}
      {cells.length > 0 && historicHighs.length > 0 && (
        <div
          style={{
            position: "relative",
            margin: "20px 0 16px",
            borderTop: "1px solid var(--qgi-border)",
          }}
        >
          <span
            style={{
              position: "absolute",
              top: "50%",
              left: "50%",
              transform: "translate(-50%, -50%)",
              background: "var(--qgi-surface)",
              padding: "0 12px",
              fontSize: "9.5px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
              letterSpacing: "1px",
              textTransform: "uppercase",
              whiteSpace: "nowrap",
            }}
          >
            Also: at decade highs
          </span>
        </div>
      )}

      {/* Section B: At historic high */}
      {historicHighs.length > 0 && (
        <div>
          {cells.length === 0 && (
            <div
              style={{
                fontSize: "10px",
                fontFamily: "ui-monospace, monospace",
                textTransform: "uppercase",
                letterSpacing: "1.5px",
                color: "#C9A84C",
                marginBottom: "10px",
              }}
            >
              At decade highs
            </div>
          )}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
              gap: "8px",
            }}
          >
            {historicHighs.map((cell) => (
              <HistoricHighRow key={cell.key} cell={cell} />
            ))}
          </div>
        </div>
      )}
    </PanelBase>
  );
}

function CaughtUpRow({ cell }: { cell: CaughtUpCell }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "10px",
        padding: "8px 12px",
        background: "var(--qgi-bg)",
        border: "1px solid rgba(201,168,76,0.25)",
        borderLeft: "3px solid #C9A84C",
        borderRadius: "5px",
        flexWrap: "wrap",
      }}
    >
      {/* Labels */}
      <div style={{ flex: 1, minWidth: "120px" }}>
        <span
          style={{
            fontSize: "12.5px",
            fontWeight: 600,
            color: "var(--qgi-text)",
          }}
        >
          {cell.countryName}
        </span>
        <span
          style={{
            fontSize: "11px",
            color: "var(--qgi-text-muted)",
            marginLeft: "6px",
          }}
        >
          · {cell.topicLabel}
        </span>
      </div>

      {/* Before → after */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "6px",
          fontFamily: "ui-monospace, monospace",
          fontSize: "12px",
          flexShrink: 0,
          flexWrap: "wrap",
        }}
      >
        <span style={{ color: "var(--qgi-text-dim)" }}>
          prev pulse:{" "}
          <span style={{ color: "var(--qgi-text-muted)" }}>
            {Math.round(cell.prevPulse)}
          </span>
        </span>
        <span style={{ color: "var(--qgi-text-dim)" }}>→</span>
        <span>
          now:{" "}
          <span style={{ color: "#C9A84C", fontWeight: 700 }}>
            {Math.round(cell.pulse)}
          </span>
        </span>
        <span
          style={{
            fontSize: "9.5px",
            color: "var(--qgi-text-dim)",
          }}
        >
          (struct: {Math.round(cell.struct)} · {cell.crossoverPct}%)
        </span>
      </div>
    </div>
  );
}

function HistoricHighRow({ cell }: { cell: HistoricHighCell }) {
  const verdictColor = VERDICT_COLOR[cell.verdict];
  const isNewHigh = cell.pct > 100;

  return (
    <div
      style={{
        padding: "9px 12px",
        background: "var(--qgi-bg)",
        border: "1px solid rgba(201,168,76,0.20)",
        borderLeft: `3px solid ${verdictColor}`,
        borderRadius: "5px",
        display: "flex",
        alignItems: "center",
        gap: "10px",
        minWidth: 0,
      }}
    >
      {/* Labels */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: "12px",
            fontWeight: 600,
            color: "var(--qgi-text)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {cell.countryName}
        </div>
        <div
          style={{
            fontSize: "10.5px",
            color: "var(--qgi-text-muted)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {cell.topicLabel}
        </div>
      </div>

      {/* Pct of high OR "NEW HIGH" */}
      <div style={{ flexShrink: 0, textAlign: "right" }}>
        {isNewHigh ? (
          <span
            style={{
              fontSize: "10px",
              fontFamily: "ui-monospace, monospace",
              fontWeight: 700,
              color: "#E05C5C",
              letterSpacing: "0.3px",
            }}
          >
            NEW HIGH
          </span>
        ) : (
          <span
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: "13px",
              fontWeight: 700,
              color: "#C9A84C",
            }}
          >
            {cell.pct}%
          </span>
        )}
        <div style={{ marginTop: "2px" }}>
          <span
            style={{
              fontSize: "8.5px",
              padding: "1px 5px",
              borderRadius: "3px",
              background: `${verdictColor}18`,
              border: `1px solid ${verdictColor}55`,
              color: verdictColor,
              fontFamily: "ui-monospace, monospace",
              letterSpacing: "0.3px",
            }}
          >
            {cell.verdict}
          </span>
        </div>
      </div>
    </div>
  );
}
