"use client";

/**
 * AnalogueOverlayChart — interactive 3-line indicator overlay for the analogue
 * comparison page.
 *
 * Three position-aligned 0..100 series over the trend's canonical window:
 *   - subject (today)              solid, accent
 *   - analogue (its event year)    solid, archival gold
 *   - canonical trend shape (mean) dashed, family color, with a p25..p75 band
 *
 * All three share one x-axis (index 0 = windowYears-1 years before the end;
 * last index = the end). Hovering anywhere shows a guide line, per-line dots,
 * and a readout of each value at that year. Gaps (null) break a line.
 */
import { useEffect, useRef, useState } from "react";

export interface AnalogueOverlayChartProps {
  subject: (number | null)[];
  analogue: (number | null)[];
  canonical: number[] | null;
  canonicalLo: number[] | null;
  canonicalHi: number[] | null;
  windowYears: number;
  subjectName: string;
  analogueName: string;
  analogueYear: number;
  familyColor: string;
}

const ACCENT = "var(--qgi-accent)";
const GOLD = "#C9A66B";
const MUTED = "var(--qgi-text-muted)";
const DIM = "var(--qgi-text-dim)";
const BORDER = "var(--qgi-border)";

const W_PX = 340;
const H_PX = 132;
const PAD = { t: 10, r: 12, b: 22, l: 30 };
const INNER_W = W_PX - PAD.l - PAD.r;
const INNER_H = H_PX - PAD.t - PAD.b;

export function AnalogueOverlayChart({
  subject,
  analogue,
  canonical,
  canonicalLo,
  canonicalHi,
  windowYears,
  subjectName,
  analogueName,
  analogueYear,
  familyColor,
}: AnalogueOverlayChartProps) {
  const n = windowYears;
  const svgRef = useRef<SVGSVGElement | null>(null);
  // Touch-start coords: used to tell a horizontal scrub (suppress page scroll,
  // read the chart) from a vertical swipe (let the page scroll through).
  const touchStartRef = useRef<{ x: number; y: number } | null>(null);
  const [hover, setHover] = useState<number | null>(null);

  const sx = (i: number) => PAD.l + (n <= 1 ? 0 : (i / (n - 1)) * INNER_W);
  const sy = (v: number) => PAD.t + (1 - v / 100) * INNER_H;

  const linePath = (series: (number | null)[]) => {
    let d = "";
    let pen = false;
    series.forEach((v, i) => {
      if (v === null || v === undefined) {
        pen = false;
        return;
      }
      d += `${pen ? "L" : "M"} ${sx(i).toFixed(1)} ${sy(v).toFixed(1)} `;
      pen = true;
    });
    return d.trim();
  };

  const bandPath = () => {
    if (!canonicalLo || !canonicalHi) return "";
    const top = canonicalHi.map((v, i) => `${sx(i).toFixed(1)} ${sy(v).toFixed(1)}`);
    const bot = canonicalLo
      .map((v, i) => `${sx(i).toFixed(1)} ${sy(v).toFixed(1)}`)
      .reverse();
    return `M ${top.join(" L ")} L ${bot.join(" L ")} Z`;
  };

  const lastReal = (s: (number | null)[]) => {
    for (let i = s.length - 1; i >= 0; i--)
      if (s[i] !== null && s[i] !== undefined) return i;
    return -1;
  };

  const resolveIdx = (clientX: number, rect: DOMRect) => {
    const xView = ((clientX - rect.left) / rect.width) * W_PX;
    const idx = Math.round(((xView - PAD.l) / INNER_W) * (n - 1));
    return Math.max(0, Math.min(n - 1, idx));
  };

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return;
    setHover(resolveIdx(e.clientX, svg.getBoundingClientRect()));
  };

  const onTouchStart = (e: React.TouchEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg || !e.touches[0]) return;
    touchStartRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
    setHover(resolveIdx(e.touches[0].clientX, svg.getBoundingClientRect()));
  };

  const onTouchEnd = () => {
    touchStartRef.current = null;
    setHover(null);
  };

  // touchmove must be a NON-passive native listener: React's synthetic
  // onTouchMove is registered passive, so e.preventDefault() there is ignored
  // and the page would scroll while scrubbing. Attach imperatively with
  // { passive: false }. We ONLY preventDefault for a HORIZONTAL scrub (dx > dy)
  // so a vertical swipe that happens to start on the chart still scrolls the
  // page (never traps the page on a small screen).
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const handler = (e: TouchEvent) => {
      if (!e.touches[0]) return;
      const start = touchStartRef.current;
      if (start) {
        const dx = Math.abs(e.touches[0].clientX - start.x);
        const dy = Math.abs(e.touches[0].clientY - start.y);
        // Vertical-dominant gesture → let the page scroll, don't scrub.
        if (dy > dx) return;
      }
      e.preventDefault();
      const rect = svg.getBoundingClientRect();
      const xView = ((e.touches[0].clientX - rect.left) / rect.width) * W_PX;
      const idx = Math.max(
        0,
        Math.min(n - 1, Math.round(((xView - PAD.l) / INNER_W) * (n - 1)))
      );
      setHover(idx);
    };
    svg.addEventListener("touchmove", handler, { passive: false });
    return () => svg.removeEventListener("touchmove", handler);
  }, [n]);

  const yearsBefore = hover === null ? 0 : n - 1 - hover;
  const fmt = (v: number | null | undefined) =>
    v === null || v === undefined ? "no data" : Math.round(v).toString();

  const sEndIdx = lastReal(subject);
  const aEndIdx = lastReal(analogue);

  return (
    <div style={{ position: "relative" }}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W_PX} ${H_PX}`}
        width="100%"
        role="img"
        aria-label="Indicator trajectory overlay"
        style={{ display: "block", cursor: "crosshair" }}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        onTouchStart={onTouchStart}
        onTouchEnd={onTouchEnd}
      >
        {/* gridlines */}
        {[0, 50, 100].map((g) => (
          <line
            key={g}
            x1={PAD.l}
            x2={PAD.l + INNER_W}
            y1={sy(g)}
            y2={sy(g)}
            stroke={BORDER}
            strokeWidth={0.5}
            opacity={0.5}
          />
        ))}

        {/* canonical band */}
        {canonicalLo && canonicalHi && (
          <path d={bandPath()} fill={familyColor} opacity={0.1} />
        )}

        {/* canonical mean (dashed, family color) */}
        {canonical && (
          <path
            d={linePath(canonical)}
            fill="none"
            stroke={familyColor}
            strokeWidth={1.5}
            strokeDasharray="4 3"
            opacity={0.85}
            strokeLinejoin="round"
          />
        )}

        {/* analogue (gold, solid) */}
        <path
          d={linePath(analogue)}
          fill="none"
          stroke={GOLD}
          strokeWidth={1.8}
          opacity={0.9}
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {/* subject (accent, solid, foreground) */}
        <path
          d={linePath(subject)}
          fill="none"
          stroke={ACCENT}
          strokeWidth={2.3}
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {/* end dots */}
        {aEndIdx >= 0 && (
          <circle
            cx={sx(aEndIdx)}
            cy={sy(analogue[aEndIdx] as number)}
            r={2.6}
            fill={GOLD}
          />
        )}
        {sEndIdx >= 0 && (
          <circle
            cx={sx(sEndIdx)}
            cy={sy(subject[sEndIdx] as number)}
            r={2.8}
            fill={ACCENT}
          />
        )}

        {/* hover guide + dots */}
        {hover !== null && (
          <g>
            <line
              x1={sx(hover)}
              x2={sx(hover)}
              y1={PAD.t}
              y2={PAD.t + INNER_H}
              stroke={MUTED}
              strokeWidth={0.8}
              opacity={0.6}
            />
            {canonical && canonical[hover] != null && (
              <circle
                cx={sx(hover)}
                cy={sy(canonical[hover])}
                r={2.4}
                fill={familyColor}
              />
            )}
            {analogue[hover] != null && (
              <circle
                cx={sx(hover)}
                cy={sy(analogue[hover] as number)}
                r={2.6}
                fill={GOLD}
              />
            )}
            {subject[hover] != null && (
              <circle
                cx={sx(hover)}
                cy={sy(subject[hover] as number)}
                r={2.8}
                fill={ACCENT}
              />
            )}
          </g>
        )}

        {/* x-axis end labels */}
        <text
          x={PAD.l}
          y={H_PX - 6}
          fontSize={10}
          fill={DIM}
          fontFamily="ui-monospace, monospace"
        >
          {n - 1} years earlier
        </text>
        <text
          x={PAD.l + INNER_W}
          y={H_PX - 6}
          fontSize={10}
          fill={DIM}
          textAnchor="end"
          fontFamily="ui-monospace, monospace"
        >
          the moment
        </text>
      </svg>

      {/* hover readout */}
      {hover !== null && (
        <div
          style={{
            position: "absolute",
            top: 4,
            left: `${(sx(hover) / W_PX) * 100}%`,
            transform: hover > n / 2 ? "translateX(-104%)" : "translateX(4%)",
            background: "var(--qgi-surface)",
            border: `1px solid ${BORDER}`,
            borderRadius: 6,
            padding: "6px 8px",
            pointerEvents: "none",
            fontSize: 11,
            fontFamily: "ui-monospace, monospace",
            lineHeight: 1.5,
            whiteSpace: "nowrap",
            boxShadow: "0 6px 18px rgba(0,0,0,0.4)",
            zIndex: 2,
          }}
        >
          <div style={{ color: DIM, marginBottom: 2 }}>
            {yearsBefore === 0 ? "run-up end" : `${yearsBefore}y before`}
          </div>
          <Row
            color={ACCENT}
            label={`${subjectName} (today)`}
            value={fmt(subject[hover])}
          />
          <Row
            color={GOLD}
            label={`${analogueName} ${analogueYear}`}
            value={fmt(analogue[hover])}
          />
          {canonical && (
            <Row
              color={familyColor}
              label="trend canonical"
              value={fmt(canonical[hover])}
            />
          )}
        </div>
      )}
    </div>
  );
}

function Row({ color, label, value }: { color: string; label: string; value: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <span
        style={{
          width: 7,
          height: 7,
          borderRadius: "50%",
          background: color,
          flexShrink: 0,
        }}
      />
      <span style={{ color: "var(--qgi-text-muted)" }}>{label}</span>
      <span
        style={{
          marginLeft: "auto",
          color: "var(--qgi-text)",
          fontWeight: 700,
          paddingLeft: 10,
        }}
      >
        {value}
      </span>
    </div>
  );
}
