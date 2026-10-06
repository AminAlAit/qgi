import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt =
  "Niger #4, Burkina Faso #57: structural divergence inside the AES bloc · April 2026 scoring run · QG Intelligence";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const BARS = [
  { country: "Niger", score: 94, rank: "#4 of 58", highlight: true },
  { country: "Burkina Faso", score: 2, rank: "#57 of 58", highlight: false },
];

export default function Image() {
  const maxVal = 100;
  const chartW = 720;
  const chartLeft = 240;
  const barH = 70;
  const groupGap = 50;

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
          fontSize: 28,
          fontWeight: 700,
          marginBottom: 8,
          letterSpacing: "-0.5px",
        }}
      >
        Two AES juntas, opposite structural paths
      </div>
      <div
        style={{
          color: "rgba(167,139,250,0.9)",
          fontSize: 16,
          marginBottom: 32,
          letterSpacing: "0.5px",
        }}
      >
        QG Intelligence · Multilateral Agreement recipe · April 2026 scoring run
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
          height={360}
          viewBox={`0 0 1080 360`}
          style={{ display: "block" }}
        >
          {BARS.map((b, i) => {
            const y = i * (barH + groupGap) + 30;
            const w = Math.round((b.score / maxVal) * chartW);
            const fill = b.highlight ? "#a78bfa" : "rgba(251,191,36,0.7)";
            const labelColor = b.highlight ? "#a78bfa" : "rgba(251,191,36,0.95)";

            return (
              <g key={b.country}>
                <text
                  x={chartLeft - 16}
                  y={y + barH / 2 + 2}
                  textAnchor="end"
                  fontSize={22}
                  fontWeight={600}
                  fill="white"
                >
                  {b.country}
                </text>
                <text
                  x={chartLeft - 16}
                  y={y + barH / 2 + 26}
                  textAnchor="end"
                  fontSize={14}
                  fill="rgba(255,255,255,0.5)"
                >
                  {b.rank}
                </text>
                <rect
                  x={chartLeft}
                  y={y}
                  width={Math.max(w, 4)}
                  height={barH}
                  rx={6}
                  fill={fill}
                />
                <text
                  x={chartLeft + Math.max(w, 4) + 12}
                  y={y + barH / 2 + 10}
                  fontSize={32}
                  fontWeight={700}
                  fill={labelColor}
                >
                  {b.score}/100
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
          maxWidth: 800,
        }}
      >
        Niger and Burkina Faso are 95% cosine peers at the L1 composite. On the
        Multilateral Agreement recipe they sit at opposite ends of the same 58-country
        cohort.
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
