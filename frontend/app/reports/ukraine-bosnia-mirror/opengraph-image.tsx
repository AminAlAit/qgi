import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt =
  "Ukraine's closest structural twin: Bosnia 1996 · 81% cosine · April 2026 scoring run · QG Intelligence";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const PEERS = [
  { country: "Bosnia and Herzegovina", pct: 81, highlight: true },
  { country: "Oman", pct: 65, highlight: false },
  { country: "Sri Lanka", pct: 65, highlight: false },
  { country: "Türkiye", pct: 65, highlight: false },
  { country: "Uzbekistan", pct: 65, highlight: false },
];

export default function Image() {
  const maxVal = 100;
  const chartW = 540;
  const chartLeft = 410;
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
        Ukraine&apos;s closest structural twin: Bosnia 1996
      </div>
      <div
        style={{
          color: "rgba(167,139,250,0.9)",
          fontSize: 16,
          marginBottom: 28,
          letterSpacing: "0.5px",
        }}
      >
        QG Intelligence · Top-5 cosine peers · April 2026 scoring run
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
          viewBox={`0 0 1080 350`}
          style={{ display: "block" }}
        >
          {PEERS.map((p, i) => {
            const y = i * (barH + barGap) + 12;
            const w = Math.round((p.pct / maxVal) * chartW);
            const fill = p.highlight ? "#a78bfa" : "rgba(167,139,250,0.45)";
            return (
              <g key={p.country}>
                <text
                  x={chartLeft - 14}
                  y={y + barH / 2 + 6}
                  textAnchor="end"
                  fontSize={20}
                  fontWeight={p.highlight ? 600 : 400}
                  fill={p.highlight ? "white" : "rgba(255,255,255,0.7)"}
                >
                  {p.country}
                </text>
                <rect x={chartLeft} y={y} width={w} height={barH} rx={5} fill={fill} />
                <text
                  x={chartLeft + w + 10}
                  y={y + barH / 2 + 7}
                  fontSize={22}
                  fontWeight={600}
                  fill={p.highlight ? "#a78bfa" : "rgba(167,139,250,0.75)"}
                >
                  {p.pct}%
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
        Categorically ahead. 16-percentage-point gap between Ukraine&apos;s #1 peer and
        the next-closest cluster.
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
