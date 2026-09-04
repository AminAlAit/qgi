import type { CSSProperties } from "react";

/**
 * Shared OG-card frame for QG Intelligence social previews.
 *
 * Renders to a 1200x630 PNG via next/og ImageResponse. Pure HTML/CSS divs
 * (no SVG <text>) so Satori renders cleanly in dev + edge runtime.
 *
 * Each page that needs a custom OG (landing, /about, /reports, /methodology,
 * /blog, individual blog posts) calls OgFrame with its own eyebrow + title +
 * tagline. The frame keeps brand wordmark + accent rule consistent across the
 * whole public surface.
 */

const NAVY = "#0f1923";
// canonical dark-mode --qgi-accent (electric blue); was '#a78bfa' violet — wrong
const ACCENT = "#38bdf8";
const TEXT = "#f5f5f5";
// canonical dark-mode --qgi-text-muted (steel); was '#94a3b8'
const MUTED = "#9ab0c4";
const DIM = "#64748b";

export type OgFrameProps = {
  /** Tiny uppercase label above the title (e.g. "About", "Methodology", "Blog · Recipe Tracker"). */
  eyebrow: string;
  /** Main display title. 2-3 short lines max. */
  title: string;
  /** One-sentence supporting line below the title. */
  tagline?: string;
  /** Optional right-side metric block (e.g. "150+ COUNTRIES · 104 INDICATORS"). */
  rightStat?: { value: string; label: string };
};

export function OgFrame({ eyebrow, title, tagline, rightStat }: OgFrameProps) {
  const root: CSSProperties = {
    width: 1200,
    height: 630,
    backgroundColor: NAVY,
    display: "flex",
    flexDirection: "column",
    padding: "60px 70px",
    fontFamily: "sans-serif",
    position: "relative",
  };

  return (
    <div style={root}>
      {/* Left accent bar */}
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          bottom: 0,
          width: 8,
          backgroundColor: ACCENT,
          display: "flex",
        }}
      />

      {/* Brand wordmark */}
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: 8,
          marginBottom: 40,
        }}
      >
        <span
          style={{
            color: ACCENT,
            fontSize: 22,
            fontWeight: 700,
            letterSpacing: 4,
          }}
        >
          QG
        </span>
        <span
          style={{
            color: MUTED,
            fontSize: 13,
            fontWeight: 500,
            letterSpacing: 3,
            textTransform: "uppercase",
          }}
        >
          Intelligence
        </span>
      </div>

      {/* Eyebrow */}
      <div
        style={{
          color: ACCENT,
          fontSize: 16,
          fontWeight: 600,
          letterSpacing: 4,
          textTransform: "uppercase",
          marginBottom: 24,
          display: "flex",
        }}
      >
        {eyebrow}
      </div>

      {/* Title */}
      <div
        style={{
          color: TEXT,
          fontSize: 56,
          fontWeight: 700,
          lineHeight: 1.1,
          letterSpacing: -1,
          marginBottom: 24,
          maxWidth: rightStat ? 760 : 1060,
          display: "flex",
        }}
      >
        {title}
      </div>

      {/* Tagline */}
      {tagline && (
        <div
          style={{
            color: MUTED,
            fontSize: 24,
            lineHeight: 1.45,
            maxWidth: rightStat ? 760 : 1000,
            display: "flex",
          }}
        >
          {tagline}
        </div>
      )}

      {/* Right-side stat block (optional) */}
      {rightStat && (
        <div
          style={{
            position: "absolute",
            right: 70,
            top: 140,
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-end",
          }}
        >
          <div
            style={{
              color: ACCENT,
              fontSize: 96,
              fontWeight: 800,
              lineHeight: 1,
              letterSpacing: -3,
              display: "flex",
            }}
          >
            {rightStat.value}
          </div>
          <div
            style={{
              color: MUTED,
              fontSize: 14,
              letterSpacing: 3,
              textTransform: "uppercase",
              marginTop: 8,
              display: "flex",
            }}
          >
            {rightStat.label}
          </div>
        </div>
      )}

      {/* Footer line */}
      <div
        style={{
          position: "absolute",
          left: 70,
          right: 70,
          bottom: 50,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          borderTop: `1px solid ${DIM}`,
          paddingTop: 20,
        }}
      >
        <div
          style={{
            color: MUTED,
            fontSize: 14,
            letterSpacing: 2,
            textTransform: "uppercase",
            display: "flex",
          }}
        >
          qgintelligence.com
        </div>
        <div
          style={{
            color: DIM,
            fontSize: 14,
            letterSpacing: 2,
            display: "flex",
          }}
        >
          Read against history
        </div>
      </div>
    </div>
  );
}

export const OG_SIZE = { width: 1200, height: 630 } as const;
export const OG_CONTENT_TYPE = "image/png" as const;
