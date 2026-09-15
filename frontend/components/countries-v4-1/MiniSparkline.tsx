/**
 * MiniSparkline — a tiny inline-SVG line chart for movement / rank history.
 *
 * The line ALWAYS terminates at the last data point with a small end dot
 * and NEVER extends past it: no dotted continuation, no future shading, no
 * right-pointing arrowhead. This is a hard methodology guardrail (Kwame) —
 * these charts are retrospective, and the visual must end, not point, so a
 * reader cannot mistake recent movement for a forecast.
 */
export function MiniSparkline({
  values,
  color,
  width = 120,
  height = 30,
  min = 0,
  max = 100,
}: {
  values: number[];
  color: string;
  width?: number;
  height?: number;
  min?: number;
  max?: number;
}) {
  if (!values || values.length === 0) {
    return <span style={{ display: "inline-block", width, height }} aria-hidden />;
  }
  const pad = 3;
  const innerW = width - pad * 2;
  const innerH = height - pad * 2;
  const span = Math.max(1, max - min);
  const n = values.length;
  // A single point centers (and renders as the end dot); >=2 points span the
  // width. (n===1 at the left edge would otherwise render an invisible line.)
  const x = (i: number) => pad + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const y = (v: number) =>
    pad + innerH - ((Math.max(min, Math.min(max, v)) - min) / span) * innerH;

  const points = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const lastX = x(n - 1);
  const lastY = y(values[n - 1]);

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Retrospective trend, ending at the latest reading"
      style={{ display: "block", overflow: "visible" }}
    >
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={1.6}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* End dot = "today". The line stops here on purpose. */}
      <circle cx={lastX} cy={lastY} r={2.4} fill={color} />
    </svg>
  );
}
