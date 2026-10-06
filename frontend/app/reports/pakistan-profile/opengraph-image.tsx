import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt =
  "Pakistan: top across five structural models at once · QGI te-fleet-run-2 · QG Intelligence";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const MODELS = [
  { label: "Labor Action", pct: 96, highlight: true },
  { label: "Religious & Social", pct: 94, highlight: false },
  { label: "Political Repression", pct: 91, highlight: false },
  { label: "Foreign Intervention", pct: 89, highlight: false },
  { label: "Democratic Transition", pct: 80, highlight: false },
];

export default function Image() {
  const chartW = 500;
  const chartLeft = 480;
  const barH = 44;
  const barGap = 10;

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
        Pakistan: five structural models fire at once
      </div>
      <div
        style={{
          color: "rgba(167,139,250,0.9)",
          fontSize: 16,
          marginBottom: 28,
          letterSpacing: "0.5px",
        }}
      >
        QG Intelligence · te-fleet-run-2 · June 2026 scoring run
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
          height={350}
          viewBox="0 0 1080 350"
          style={{ display: "block" }}
        >
          {MODELS.map((m, i) => {
            const y = i * (barH + barGap) + 12;
            const w = Math.round((m.pct / 100) * chartW);
            const fill = m.highlight ? "#a78bfa" : "rgba(167,139,250,0.45)";
            return (
              <g key={m.label}>
                <text
                  x={chartLeft - 14}
                  y={y + barH / 2 + 6}
                  textAnchor="end"
                  fontSize={20}
                  fontWeight={m.highlight ? 600 : 400}
                  fill={m.highlight ? "white" : "rgba(255,255,255,0.7)"}
                >
                  {m.label}
                </text>
                <rect x={chartLeft} y={y} width={w} height={barH} rx={5} fill={fill} />
                <text
                  x={chartLeft + w + 10}
                  y={y + barH / 2 + 7}
                  fontSize={22}
                  fontWeight={600}
                  fill={m.highlight ? "#a78bfa" : "rgba(167,139,250,0.75)"}
                >
                  {m.pct}
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
        Top 8 to 20 globally on all five at once. Nearest self-analogue: Pakistan 2011
        (0.97 cosine).
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
