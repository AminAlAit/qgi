/**
 * PatternShapeSparkline — inline SVG of one pattern's canonical movement
 * shape. Used in three places:
 *   - PatternCard (compact preview, ~84px tall)
 *   - PatternDetail §1 (large, with axes + reference band)
 *   - PatternRankingTable (NOT used here; runner-up is just text)
 *
 * The shape is rendered with:
 *   - a soft fill under the curve to read at small sizes
 *   - a zero-baseline reference line (the benign / danger threshold)
 *   - end-cap dots at t-0 (the terminating event in TE language)
 *
 * Honesty regime: this is a HISTORICAL canonical shape, not a forecast.
 * x-axis units are recipe-window years; y-axis is standardized indicator
 * z-score. The full-detail variant shows the axis ticks; the card variant
 * suppresses them for visual quiet.
 *
 * Server component. Pure SVG, no client interactivity.
 */
export interface PatternShapeSparklineProps {
  /** 12-point z-score series describing the canonical shape. */
  points: number[];
  /** Family color for the curve. */
  color: string;
  /** Window length in years — drives the t-axis labels. */
  windowY: number;
  /** Render mode. "card" = compact, "detail" = full axes + labels. */
  variant?: "card" | "detail";
  width?: number;
  height?: number;
}

export function PatternShapeSparkline({
  points,
  color,
  windowY,
  variant = "card",
  width = variant === "detail" ? 720 : 220,
  height = variant === "detail" ? 220 : 84,
}: PatternShapeSparklineProps) {
  const pad =
    variant === "detail"
      ? { top: 18, right: 22, bottom: 28, left: 40 }
      : { top: 6, right: 6, bottom: 12, left: 16 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;

  // Symmetric scale around 0 so the zero-line sits in the middle of the panel.
  const absMax = Math.max(2.2, ...points.map((p) => Math.abs(p)));
  const yMin = -absMax;
  const yMax = absMax;
  const yScale = (v: number) => pad.top + innerH - ((v - yMin) / (yMax - yMin)) * innerH;
  const xScale = (i: number) => pad.left + (i / (points.length - 1)) * innerW;

  const linePath = points
    .map(
      (v, i) => `${i === 0 ? "M" : "L"} ${xScale(i).toFixed(1)} ${yScale(v).toFixed(1)}`
    )
    .join(" ");
  // Soft fill under the curve down to the zero baseline.
  const baselineY = yScale(0);
  const fillPath =
    `M ${xScale(0).toFixed(1)} ${baselineY.toFixed(1)} ` +
    points.map((v, i) => `L ${xScale(i).toFixed(1)} ${yScale(v).toFixed(1)}`).join(" ") +
    ` L ${xScale(points.length - 1).toFixed(1)} ${baselineY.toFixed(1)} Z`;

  const fillId = `pat-shape-fill-${Math.abs(points[0] * 1000 + windowY * 7).toFixed(0)}`;

  const showAxes = variant === "detail";

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Canonical movement shape over ${windowY} years (z-score from -${absMax.toFixed(1)} to ${absMax.toFixed(1)})`}
      style={{ display: "block" }}
    >
      <defs>
        <linearGradient id={fillId} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.45} />
          <stop offset="100%" stopColor={color} stopOpacity={0.02} />
        </linearGradient>
      </defs>

      {/* Zero baseline */}
      <line
        x1={pad.left}
        x2={pad.left + innerW}
        y1={baselineY}
        y2={baselineY}
        stroke="var(--qgi-border)"
        strokeDasharray="2 3"
        strokeWidth={1}
      />

      {/* y-axis grid + labels (detail only) */}
      {showAxes && (
        <>
          {[yMax, 0, yMin].map((g, i) => (
            <g key={i}>
              <line
                x1={pad.left}
                x2={pad.left + innerW}
                y1={yScale(g)}
                y2={yScale(g)}
                stroke="var(--qgi-border)"
                strokeOpacity={g === 0 ? 0.6 : 0.25}
                strokeDasharray={g === 0 ? "2 3" : "1 4"}
                strokeWidth={0.7}
              />
              <text
                x={pad.left - 6}
                y={yScale(g) + 3}
                fontSize="9"
                textAnchor="end"
                fill="var(--qgi-text-dim)"
                fontFamily="ui-monospace, monospace"
              >
                {g > 0 ? `+${g.toFixed(1)}` : g.toFixed(1)}
              </text>
            </g>
          ))}
          <text
            x={6}
            y={pad.top + innerH / 2}
            fontSize="9"
            fill="var(--qgi-text-dim)"
            fontFamily="ui-monospace, monospace"
            transform={`rotate(-90 ${10} ${pad.top + innerH / 2})`}
          >
            z-score
          </text>
        </>
      )}

      {/* Fill under curve */}
      <path d={fillPath} fill={`url(#${fillId})`} stroke="none" />

      {/* Curve */}
      <path
        d={linePath}
        fill="none"
        stroke={color}
        strokeWidth={variant === "detail" ? 2.4 : 1.8}
      />

      {/* End-of-window event dot */}
      <circle
        cx={xScale(points.length - 1)}
        cy={yScale(points[points.length - 1])}
        r={variant === "detail" ? 4 : 2.6}
        fill={color}
      />
      <circle
        cx={xScale(0)}
        cy={yScale(points[0])}
        r={variant === "detail" ? 3 : 2.0}
        fill={color}
        opacity={0.4}
      />

      {/* x-axis tick labels */}
      {showAxes ? (
        <>
          <text
            x={pad.left}
            y={height - 8}
            fontSize="10"
            fill="var(--qgi-text-dim)"
            fontFamily="ui-monospace, monospace"
          >
            t-{windowY}y
          </text>
          <text
            x={pad.left + innerW / 2}
            y={height - 8}
            fontSize="10"
            textAnchor="middle"
            fill="var(--qgi-text-dim)"
            fontFamily="ui-monospace, monospace"
          >
            t-{Math.round(windowY / 2)}y
          </text>
          <text
            x={pad.left + innerW}
            y={height - 8}
            fontSize="10"
            textAnchor="end"
            fill="var(--qgi-text-dim)"
            fontFamily="ui-monospace, monospace"
          >
            event (t-0)
          </text>
        </>
      ) : (
        <>
          <text
            x={pad.left}
            y={height - 2}
            fontSize="8"
            fill="var(--qgi-text-dim)"
            fontFamily="ui-monospace, monospace"
          >
            t-{windowY}y
          </text>
          <text
            x={pad.left + innerW}
            y={height - 2}
            fontSize="8"
            textAnchor="end"
            fill="var(--qgi-text-dim)"
            fontFamily="ui-monospace, monospace"
          >
            t-0
          </text>
        </>
      )}
    </svg>
  );
}
