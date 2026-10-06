import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt =
  "India and Pakistan: 99% structural mirror · April 2026 scoring run · QG Intelligence";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const DIMS = [
  { name: "Conflict & Political Violence", pct: 45 },
  { name: "Political Power & Regime", pct: 17 },
  { name: "State Authority & Governance", pct: 11 },
  { name: "Economic & Financial Stress", pct: 11 },
  { name: "Social Mobilisation & Civil Society", pct: 10 },
  { name: "Diplomatic & Geopolitical", pct: 6 },
];

export default function Image() {
  const maxVal = 50;
  const chartW = 540;
  const chartLeft = 410;
  const barH = 38;
  const barGap = 8;

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
      <div
        style={{
          color: "white",
          fontSize: 30,
          fontWeight: 700,
          marginBottom: 8,
          letterSpacing: "-0.5px",
        }}
      >
        India and Pakistan are 99% the same risk
      </div>
      <div
        style={{
          color: "rgba(167,139,250,0.9)",
          fontSize: 16,
          marginBottom: 28,
          letterSpacing: "0.5px",
        }}
      >
        QG Intelligence · Cosine decomposition · April 2026 scoring run
      </div>

      <div
        style={{
          display: "flex",
          flex: 1,
          alignItems: "flex-start",
          position: "relative",
        }}
      >
        <svg
          width={1080}
          height={340}
          viewBox={`0 0 1080 340`}
          style={{ display: "block" }}
        >
          {DIMS.map((d, i) => {
            const y = i * (barH + barGap) + 10;
            const w = Math.round((d.pct / maxVal) * chartW);
            const isPrimary = d.pct >= 17;
            return (
              <g key={d.name}>
                <text
                  x={chartLeft - 14}
                  y={y + barH / 2 + 6}
                  textAnchor="end"
                  fontSize={18}
                  fontWeight={isPrimary ? 600 : 400}
                  fill={isPrimary ? "white" : "rgba(255,255,255,0.7)"}
                >
                  {d.name}
                </text>
                <rect
                  x={chartLeft}
                  y={y}
                  width={w}
                  height={barH}
                  rx={4}
                  fill={isPrimary ? "#a78bfa" : "rgba(167,139,250,0.55)"}
                />
                <text
                  x={chartLeft + w + 10}
                  y={y + barH / 2 + 6}
                  fontSize={22}
                  fontWeight={600}
                  fill="#a78bfa"
                >
                  {d.pct}%
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div
        style={{
          color: "rgba(255,255,255,0.7)",
          fontSize: 14,
          marginTop: 12,
          maxWidth: 920,
        }}
      >
        Each other&apos;s #1 structural peer in a 156-country cohort. Share of the 99%
        cosine match, decomposed across 6 of 8 L1 dimensions.
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
