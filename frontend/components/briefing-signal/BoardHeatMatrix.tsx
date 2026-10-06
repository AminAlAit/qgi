"use client";
/**
 * BoardHeatMatrix — country × topic heat matrix for the Signal Board.
 *
 * Each cell is a colored div (no text inside). Hover shows a tooltip with
 * country name, topic, struct, pulse, verdict. Clicking navigates to /risk-board.
 *
 * "use client" for hover tooltip only. Cell data is passed from the server page.
 */
import { useState } from "react";
import { useRouter } from "next/navigation";
import type { HfCell, HfVerdict, HfTopic, HfCountry } from "@/lib/hf/topics-data";

const VERDICT_COLOR: Record<HfVerdict, string> = {
  ACTIVE: "rgba(224,92,92,0.85)",
  SIGNAL: "rgba(245,158,11,0.80)",
  LATENT: "rgba(91,126,153,0.70)",
  QUIET: "rgba(36,51,71,0.50)",
};

interface TooltipState {
  x: number;
  y: number;
  countryName: string;
  topicLabel: string;
  struct: number | null;
  pulse: number;
  verdict: HfVerdict;
  iso3: string;
}

interface Props {
  cells: Record<string, HfCell>;
  countries: HfCountry[];
  topics: HfTopic[];
}

export function BoardHeatMatrix({ cells, countries, topics }: Props) {
  const router = useRouter();
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  // Only board topics (the six founder-ratified columns)
  const boardTopics = topics.filter((t) => t.board);

  function handleMouseEnter(
    e: React.MouseEvent,
    country: HfCountry,
    topic: HfTopic,
    cell: HfCell | undefined
  ) {
    if (!cell) return;
    const rect = (e.target as HTMLElement).getBoundingClientRect();
    setTooltip({
      x: rect.left + rect.width / 2,
      y: rect.top - 8,
      countryName: country.name,
      topicLabel: topic.label,
      struct: cell.struct,
      pulse: cell.pulse,
      verdict: cell.verdict,
      iso3: country.iso3,
    });
  }

  function handleMouseLeave() {
    setTooltip(null);
  }

  function handleCellClick(cell: HfCell | undefined) {
    if (!cell || cell.verdict === "QUIET") return;
    router.push("/risk-board");
  }

  const CELL_W = 48;
  const CELL_H = 36;
  const GAP = 2;
  const ROW_HEADER_W = 60;
  const COL_HEADER_H = 64;

  return (
    <>
      <style>{`
        .qgi-heat-cell {
          transition: opacity 100ms ease, outline 100ms ease;
        }
        .qgi-heat-cell:hover {
          opacity: 1 !important;
          outline: 2px solid rgba(255,255,255,0.35);
          outline-offset: -1px;
          z-index: 2;
          position: relative;
        }
      `}</style>

      <div style={{ overflowX: "auto", width: "100%" }}>
        {/* Column headers row */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: `${ROW_HEADER_W}px repeat(${boardTopics.length}, ${CELL_W}px)`,
            gap: `0 ${GAP}px`,
            marginBottom: `${GAP}px`,
          }}
        >
          {/* Empty corner */}
          <div style={{ height: `${COL_HEADER_H}px` }} />
          {boardTopics.map((topic) => (
            <div
              key={topic.id}
              style={{
                width: `${CELL_W}px`,
                height: `${COL_HEADER_H}px`,
                display: "flex",
                alignItems: "flex-end",
                justifyContent: "center",
                paddingBottom: "6px",
                overflow: "hidden",
              }}
            >
              <span
                style={{
                  fontFamily: "ui-monospace, monospace",
                  fontSize: "12px",
                  letterSpacing: "0.5px",
                  color: "var(--qgi-text-muted)",
                  display: "block",
                  transformOrigin: "center bottom",
                  transform: "rotate(-45deg)",
                  whiteSpace: "nowrap",
                  lineHeight: 1,
                }}
              >
                {topic.label}
              </span>
            </div>
          ))}
        </div>

        {/* Country rows */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: `${GAP}px`,
          }}
        >
          {countries.map((country) => (
            <div
              key={country.iso3}
              style={{
                display: "grid",
                gridTemplateColumns: `${ROW_HEADER_W}px repeat(${boardTopics.length}, ${CELL_W}px)`,
                gap: `0 ${GAP}px`,
                alignItems: "center",
              }}
            >
              {/* Row header: ISO3 */}
              <div
                style={{
                  width: `${ROW_HEADER_W}px`,
                  fontSize: "11px",
                  fontFamily: "ui-monospace, monospace",
                  color: "var(--qgi-text-dim)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                  paddingRight: "6px",
                  textAlign: "right",
                }}
                title={country.name}
              >
                {country.iso3}
              </div>

              {/* Cells */}
              {boardTopics.map((topic) => {
                const key = `${country.iso3}|${topic.id}`;
                const cell = cells[key];
                const verdict: HfVerdict = cell?.verdict ?? "QUIET";
                const isClickable = verdict !== "QUIET" && !!cell;

                return (
                  <div
                    key={topic.id}
                    className="qgi-heat-cell"
                    style={{
                      width: `${CELL_W}px`,
                      height: `${CELL_H}px`,
                      borderRadius: "3px",
                      background: VERDICT_COLOR[verdict],
                      cursor: isClickable ? "pointer" : "default",
                      opacity: verdict === "QUIET" ? 0.55 : 0.88,
                    }}
                    onMouseEnter={(e) => handleMouseEnter(e, country, topic, cell)}
                    onMouseLeave={handleMouseLeave}
                    onClick={() => handleCellClick(cell)}
                  />
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div
          style={{
            position: "fixed",
            left: tooltip.x,
            top: tooltip.y,
            transform: "translate(-50%, -100%)",
            zIndex: 999,
            background: "var(--qgi-surface)",
            border: "1px solid var(--qgi-border)",
            borderRadius: "6px",
            padding: "8px 12px",
            pointerEvents: "none",
            boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
            minWidth: "160px",
          }}
        >
          <div
            style={{
              fontSize: "11px",
              fontWeight: 600,
              color: "var(--qgi-text)",
              marginBottom: "4px",
            }}
          >
            {tooltip.countryName}
            <span style={{ color: "var(--qgi-border)", margin: "0 4px" }}>·</span>
            <span style={{ color: "var(--qgi-text-muted)", fontWeight: 400 }}>
              {tooltip.topicLabel}
            </span>
          </div>
          <div style={{ display: "flex", gap: "12px" }}>
            {tooltip.struct !== null && (
              <div>
                <div
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    fontSize: "9px",
                    color: "var(--qgi-text-dim)",
                    textTransform: "uppercase",
                    letterSpacing: "1px",
                  }}
                >
                  Struct
                </div>
                <div
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    fontSize: "14px",
                    fontWeight: 700,
                    color: "var(--qgi-text)",
                  }}
                >
                  {Math.round(tooltip.struct)}
                </div>
              </div>
            )}
            <div>
              <div
                style={{
                  fontFamily: "ui-monospace, monospace",
                  fontSize: "9px",
                  color: "var(--qgi-text-dim)",
                  textTransform: "uppercase",
                  letterSpacing: "1px",
                }}
              >
                Pulse
              </div>
              <div
                style={{
                  fontFamily: "ui-monospace, monospace",
                  fontSize: "14px",
                  fontWeight: 700,
                  color: "var(--qgi-text)",
                }}
              >
                {Math.round(tooltip.pulse)}
              </div>
            </div>
            <div>
              <div
                style={{
                  fontFamily: "ui-monospace, monospace",
                  fontSize: "9px",
                  color: "var(--qgi-text-dim)",
                  textTransform: "uppercase",
                  letterSpacing: "1px",
                }}
              >
                Verdict
              </div>
              <div
                style={{
                  fontFamily: "ui-monospace, monospace",
                  fontSize: "11px",
                  fontWeight: 700,
                  color:
                    tooltip.verdict === "ACTIVE"
                      ? "#E05C5C"
                      : tooltip.verdict === "SIGNAL"
                        ? "#f59e0b"
                        : tooltip.verdict === "LATENT"
                          ? "#5B7E99"
                          : "var(--qgi-text-dim)",
                }}
              >
                {tooltip.verdict}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
