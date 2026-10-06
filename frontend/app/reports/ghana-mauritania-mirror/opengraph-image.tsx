import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt =
  "Ghana vs Mauritania, 99% structural similarity · April 2026 scoring run · QG Intelligence";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// L1 dimensions data for the chart
const L1_DIMENSIONS = [
  { id: "A", ghana: 1.66, mauritania: 1.05, active: true },
  { id: "B", ghana: 0, mauritania: 0, active: false },
  { id: "C", ghana: 0, mauritania: 0, active: false },
  { id: "D", ghana: 1.01, mauritania: 0.64, active: true },
  { id: "E", ghana: 0.24, mauritania: 0.18, active: false },
  { id: "F", ghana: 0.5, mauritania: 0.5, active: true },
  { id: "G", ghana: 0, mauritania: 0.32, active: false },
  { id: "H", ghana: 0, mauritania: 0.03, active: false },
];

export default function Image() {
  const maxVal = 2.0;
  const chartW = 800;
  const chartH = 280;
  const barW = 36;
  const barGap = 4;
  const groupGap = 20;
  const offsetX = 30;

  return new ImageResponse(
    <div
      style={{
        width: 1200,
        height: 630,
        backgroundColor: "#0f1923",
        display: "flex",
        flexDirection: "column",
        padding: "40px 60px",
        fontFamily: "sans-serif",
      }}
    >
      {/* Header callout */}
      <div
        style={{
          color: "white",
          fontSize: 28,
          fontWeight: 700,
          marginBottom: 8,
          letterSpacing: "-0.5px",
        }}
      >
        Ghana ↔ Mauritania · 99% structural similarity · April 2026 scoring run
      </div>
      <div
        style={{
          color: "rgba(167,139,250,0.9)",
          fontSize: 16,
          marginBottom: 32,
          letterSpacing: "0.5px",
        }}
      >
        QG Intelligence · Per-dimension L1 risk profile comparison
      </div>

      {/* Chart area */}
      <div
        style={{ display: "flex", flex: 1, alignItems: "flex-end", position: "relative" }}
      >
        <svg
          width={chartW}
          height={chartH}
          viewBox={`0 0 ${chartW} ${chartH}`}
          style={{ display: "block" }}
        >
          {L1_DIMENSIONS.map((dim, i) => {
            const x = offsetX + i * (barW * 2 + barGap + groupGap);
            const ghanaH = Math.round((dim.ghana / maxVal) * (chartH - 40));
            const mauH = Math.round((dim.mauritania / maxVal) * (chartH - 40));
            const base = chartH - 30;

            return (
              <g key={dim.id}>
                <rect
                  x={x}
                  y={base - ghanaH}
                  width={barW}
                  height={ghanaH || 2}
                  rx={3}
                  fill={dim.active ? "#a78bfa" : "rgba(167,139,250,0.35)"}
                />
                <rect
                  x={x + barW + barGap}
                  y={base - mauH}
                  width={barW}
                  height={mauH || 2}
                  rx={3}
                  fill={dim.active ? "#fbbf24" : "rgba(251,191,36,0.3)"}
                />
                <text
                  x={x + barW}
                  y={base + 16}
                  textAnchor="middle"
                  fontSize="14"
                  fontWeight={dim.active ? "700" : "400"}
                  fill={dim.active ? "white" : "rgba(255,255,255,0.4)"}
                >
                  {dim.id}
                </text>
              </g>
            );
          })}
        </svg>

        {/* Legend */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 8,
            marginLeft: 24,
            marginBottom: 30,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div
              style={{
                width: 14,
                height: 14,
                backgroundColor: "#a78bfa",
                borderRadius: 2,
              }}
            />
            <span style={{ color: "white", fontSize: 14 }}>Ghana</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div
              style={{
                width: 14,
                height: 14,
                backgroundColor: "#fbbf24",
                borderRadius: 2,
              }}
            />
            <span style={{ color: "white", fontSize: 14 }}>Mauritania</span>
          </div>
        </div>
      </div>

      {/* QG Intelligence corner watermark — bottom-right */}
      <div
        style={{
          position: "absolute",
          bottom: 28,
          right: 48,
          display: "flex",
          alignItems: "baseline",
          gap: 4,
        }}
      >
        <span
          style={{
            color: "#38bdf8",
            fontSize: 18,
            fontWeight: 700,
            letterSpacing: 3,
          }}
        >
          QG
        </span>
        <span
          style={{
            color: "rgba(148,176,196,0.6)",
            fontSize: 11,
            fontWeight: 500,
            letterSpacing: 2,
            textTransform: "uppercase",
          }}
        >
          Intelligence
        </span>
      </div>
    </div>,
    {
      ...size,
    }
  );
}
