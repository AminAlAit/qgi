import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt =
  "United Kingdom: #1 of 157 on QGI's currency-crisis recipe, nearest analogue its own 1992 ERM exit · QG Intelligence";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function Image() {
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
        position: "relative",
      }}
    >
      <div
        style={{
          color: "white",
          fontSize: 32,
          fontWeight: 700,
          marginBottom: 8,
          letterSpacing: "-0.5px",
        }}
      >
        The UK tops QGI&apos;s currency-crisis leaderboard
      </div>
      <div
        style={{
          color: "rgba(167,139,250,0.9)",
          fontSize: 16,
          marginBottom: 48,
          letterSpacing: "0.5px",
        }}
      >
        QG Intelligence · 2026 scoring run · structural resemblance, not a forecast
      </div>

      <div style={{ display: "flex", flex: 1, alignItems: "center", gap: 64 }}>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <span
            style={{
              color: "#a78bfa",
              fontSize: 130,
              fontWeight: 800,
              lineHeight: 1,
              letterSpacing: "-2px",
            }}
          >
            #1
          </span>
          <span style={{ color: "rgba(255,255,255,0.6)", fontSize: 22, marginTop: 8 }}>
            of 157 countries
          </span>
        </div>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            borderLeft: "1px solid rgba(255,255,255,0.15)",
            paddingLeft: 64,
          }}
        >
          <span
            style={{ color: "white", fontSize: 56, fontWeight: 700, lineHeight: 1.1 }}
          >
            0.975
          </span>
          <span
            style={{
              color: "rgba(255,255,255,0.6)",
              fontSize: 20,
              marginTop: 8,
              maxWidth: 460,
            }}
          >
            cosine resemblance to its own 1992 ERM exit, its closest historical analogue
          </span>
        </div>
      </div>

      <div
        style={{
          color: "rgba(255,255,255,0.7)",
          fontSize: 14,
          marginTop: 12,
          maxWidth: 920,
        }}
      >
        The structural configuration that preceded Black Wednesday, scored highest in the
        world today.
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
