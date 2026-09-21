/**
 * TrajectorySparkline — inline SVG overlay of the current country's recent
 * 12-quarter composite indicator trajectory against a historical analog's
 * pre-event trajectory in the same 0..100 scale.
 *
 * Honesty regime: this is a SIMILARITY visualisation, NOT a forecast. The
 * analog line stops at its event (t=0 == quarter 12). The current line
 * stops at "today" (the latest available quarter). The visual rhyme is
 * the point; no projection is drawn forward.
 *
 * Server component. Pure SVG, no client interactivity.
 */
export interface TrajectorySparklineProps {
  currentSeries: number[]; // 12 quarters, 0..100
  analogSeries: number[]; // 12 quarters, 0..100
  currentLabel: string;
  analogLabel: string;
  analogColor: string; // primary recipe l1 color
  width?: number;
  height?: number;
  /** X-axis tick labels. Default to the 12-quarter framing; the analogue
   *  comparison page passes a year-window framing (e.g. "-12y" / "run-up end"). */
  leftLabel?: string;
  rightLabel?: string;
}

export function TrajectorySparkline({
  currentSeries,
  analogSeries,
  currentLabel,
  analogLabel,
  analogColor,
  width = 320,
  height = 90,
  leftLabel = "t-12q",
  rightLabel = "t-0",
}: TrajectorySparklineProps) {
  const pad = { top: 8, right: 8, bottom: 16, left: 28 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;

  const all = [...currentSeries, ...analogSeries];
  const minY = Math.min(...all) - 4;
  const maxY = Math.max(...all) + 4;
  const yScale = (v: number) => pad.top + innerH - ((v - minY) / (maxY - minY)) * innerH;
  const xScale = (i: number, n: number) => pad.left + (i / (n - 1)) * innerW;

  const toPath = (series: number[]) =>
    series
      .map(
        (v, i) =>
          `${i === 0 ? "M" : "L"} ${xScale(i, series.length).toFixed(1)} ${yScale(v).toFixed(1)}`
      )
      .join(" ");

  // Gridlines at 25, 50, 75
  const gridYs = [25, 50, 75].filter((g) => g > minY && g < maxY);

  return (
    <div>
      <svg
        width="100%"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`Trajectory overlay: ${currentLabel} (current) vs ${analogLabel} (pre-event)`}
        style={{ display: "block" }}
      >
        {/* Y-axis labels */}
        <text
          x={2}
          y={pad.top + 4}
          fontSize="10"
          fill="var(--qgi-text-dim)"
          fontFamily="ui-monospace, monospace"
        >
          {Math.round(maxY)}
        </text>
        <text
          x={2}
          y={pad.top + innerH}
          fontSize="10"
          fill="var(--qgi-text-dim)"
          fontFamily="ui-monospace, monospace"
        >
          {Math.round(minY)}
        </text>
        {/* Gridlines */}
        {gridYs.map((g) => (
          <line
            key={g}
            x1={pad.left}
            x2={pad.left + innerW}
            y1={yScale(g)}
            y2={yScale(g)}
            stroke="var(--qgi-border)"
            strokeDasharray="2 3"
            strokeWidth={0.5}
          />
        ))}
        {/* Frame */}
        <line
          x1={pad.left}
          x2={pad.left + innerW}
          y1={pad.top + innerH}
          y2={pad.top + innerH}
          stroke="var(--qgi-border)"
          strokeWidth={1}
        />
        {/* Analog series (background — primary recipe color, dashed) */}
        <path
          d={toPath(analogSeries)}
          fill="none"
          stroke={analogColor}
          strokeWidth={1.5}
          strokeDasharray="3 2"
          opacity={0.85}
        />
        {/* Current series (foreground — bright accent, solid) */}
        <path
          d={toPath(currentSeries)}
          fill="none"
          stroke="var(--qgi-accent)"
          strokeWidth={2}
          opacity={0.95}
        />
        {/* End dots */}
        <circle
          cx={xScale(analogSeries.length - 1, analogSeries.length)}
          cy={yScale(analogSeries[analogSeries.length - 1])}
          r={2.6}
          fill={analogColor}
        />
        <circle
          cx={xScale(currentSeries.length - 1, currentSeries.length)}
          cy={yScale(currentSeries[currentSeries.length - 1])}
          r={2.8}
          fill="var(--qgi-accent)"
        />
        {/* X-axis tick labels */}
        <text
          x={pad.left}
          y={height - 2}
          fontSize="10"
          fill="var(--qgi-text-dim)"
          fontFamily="ui-monospace, monospace"
        >
          {leftLabel}
        </text>
        <text
          x={pad.left + innerW}
          y={height - 2}
          fontSize="10"
          fill="var(--qgi-text-dim)"
          fontFamily="ui-monospace, monospace"
          textAnchor="end"
        >
          {rightLabel}
        </text>
      </svg>
      <div
        style={{
          display: "flex",
          gap: "12px",
          fontSize: "10px",
          color: "var(--qgi-text-muted)",
          fontFamily: "ui-monospace, monospace",
          letterSpacing: "0.3px",
          marginTop: "4px",
          flexWrap: "wrap",
        }}
      >
        <span style={{ display: "inline-flex", alignItems: "center", gap: "5px" }}>
          <span
            style={{
              width: "14px",
              height: "2px",
              background: "var(--qgi-accent)",
              display: "inline-block",
            }}
          />
          {currentLabel} (today)
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: "5px" }}>
          <span
            style={{
              width: "14px",
              height: "0",
              borderTop: `2px dashed ${analogColor}`,
              display: "inline-block",
            }}
          />
          {analogLabel} (pre-event)
        </span>
      </div>
    </div>
  );
}
