/**
 * PrecedentsTimelinePanel — V4.1 "Precedents" section.
 *
 * 2026-06-04 (founder): redesigned from a per-event dot timeline into a
 * year-frequency HISTOGRAM. Each bar is one year; its height is how many
 * verified cases of this trend the corpus holds for that year. Bars are the
 * trend's family color — no green/red, no "+"/"−" markers, no "ADDED" badge.
 * Only the corpus (verified) cases are surfaced; vacated/removed cases are not
 * shown here (green-only, by founder direction). Hovering a bar opens a single
 * popup listing every case that year (flag + country + event title) — one bar,
 * one popup, instead of N dots each with its own popup.
 *
 * Flags via flagcdn (Windows has no regional-indicator glyph table); the emoji
 * is kept as an ARIA/fallback only.
 */
"use client";

import { useState, useRef, type CSSProperties } from "react";
import { iso2For } from "@/lib/te-mock/country-flags";

export interface PrecedentEvent {
  year: number;
  country: string;
  country_iso: string;
  flag_emoji: string;
  action: "added" | "vacated";
  reason: string;
}

export interface PrecedentsTimelinePanelProps {
  familyColor: string;
  events: PrecedentEvent[];
  totalEventsInCorpus: number;
}

export function PrecedentsTimelinePanel({
  familyColor,
  events,
  totalEventsInCorpus,
}: PrecedentsTimelinePanelProps) {
  // Green-only: surface the corpus (verified) cases; vacated cases are dropped.
  const corpus = events.filter((e) => e.action !== "vacated");

  const titleStyle: CSSProperties = {
    fontSize: "15px",
    fontWeight: 600,
    color: familyColor,
    margin: 0,
    letterSpacing: "0.1px",
  };
  const chipStyle: CSSProperties = {
    fontFamily: "ui-monospace, monospace",
    fontSize: "10px",
    letterSpacing: "0.3px",
  };

  const [hoveredYear, setHoveredYear] = useState<number | null>(null);
  // Hover bridge: a short grace delay before hiding lets the cursor cross the
  // gap from a bar into the popup (and stay there to scroll a busy year's list)
  // without the popup vanishing.
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const showYear = (y: number) => {
    if (hideTimer.current) clearTimeout(hideTimer.current);
    setHoveredYear(y);
  };
  const scheduleHide = () => {
    if (hideTimer.current) clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => setHoveredYear(null), 140);
  };
  const cancelHide = () => {
    if (hideTimer.current) clearTimeout(hideTimer.current);
  };

  if (corpus.length === 0) {
    return (
      <section
        aria-labelledby="precedents-panel-heading-empty"
        data-tour="precedents-timeline-panel"
        style={{
          background: "var(--qgi-surface)",
          border: "1px solid var(--qgi-border)",
          borderLeft: `3px solid ${familyColor}`,
          borderRadius: "6px",
          padding: "16px 18px 18px",
          minWidth: "340px",
        }}
      >
        <h2 id="precedents-panel-heading-empty" style={titleStyle}>
          Precedents
        </h2>
        <div
          style={{
            marginTop: "12px",
            padding: "16px 14px",
            border: "1px dashed var(--qgi-border)",
            background: "rgba(255,255,255,0.015)",
            borderRadius: "5px",
            color: "var(--qgi-text-muted)",
            fontSize: "13px",
          }}
        >
          No precedent events for this trend at the current release.
        </div>
      </section>
    );
  }

  // ── Bin by year ──────────────────────────────────────────────────────────
  const byYear = new Map<number, PrecedentEvent[]>();
  for (const ev of corpus) {
    const bucket = byYear.get(ev.year) ?? [];
    bucket.push(ev);
    byYear.set(ev.year, bucket);
  }
  const years = [...byYear.keys()].sort((a, b) => a - b);
  const minYear = years[0];
  const maxYear = years[years.length - 1];
  const span = Math.max(1, maxYear - minYear + 1);
  const maxCount = Math.max(...[...byYear.values()].map((b) => b.length));

  // ── Chart geometry (viewBox units) ───────────────────────────────────────
  const W = 560;
  const chartH = 120;
  const axisLabelH = 20;
  const H = chartH + axisLabelH;
  const padL = 8;
  const padR = 8;
  const innerW = W - padL - padR;
  const colW = innerW / span;
  const barW = Math.min(colW * 0.7, 24);
  const xCenter = (year: number) => padL + (year - minYear + 0.5) * colW;
  const barHeight = (count: number) => (count / maxCount) * (chartH - 8);

  // Year-axis ticks (~7 evenly spaced).
  const tickStep = Math.max(1, Math.ceil(span / 7));
  const ticks: number[] = [];
  for (let y = minYear; y <= maxYear; y += tickStep) ticks.push(y);
  if (ticks[ticks.length - 1] !== maxYear) ticks.push(maxYear);

  const hoveredEvents = hoveredYear != null ? (byYear.get(hoveredYear) ?? []) : [];

  return (
    <section
      aria-labelledby="precedents-panel-heading"
      data-tour="precedents-timeline-panel"
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderLeft: `3px solid ${familyColor}`,
        borderRadius: "6px",
        padding: "16px 18px 18px",
        minWidth: "340px",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "10px",
          marginBottom: "4px",
        }}
      >
        <h2 id="precedents-panel-heading" style={titleStyle}>
          Precedents
        </h2>
        <span style={{ ...chipStyle, color: "var(--qgi-text-dim)" }}>
          verified cases by year
        </span>
      </header>

      <p
        style={{
          fontSize: "12px",
          color: "var(--qgi-text-muted)",
          margin: "2px 0 16px",
          lineHeight: 1.5,
        }}
      >
        These are the real-world events that built this trend: the documented cases its
        shape was learned from, {corpus.length.toLocaleString()} in all from {minYear} to{" "}
        {maxYear}. Each bar is a year; hover it to see that year&apos;s cases.
      </p>

      {/* Histogram + hover popup overlay. The wrapper is position:relative with
          the SVG's aspect ratio so the HTML popup can anchor at a bar's x. */}
      <div
        style={{
          position: "relative",
          width: "100%",
          minWidth: "320px",
          aspectRatio: `${W} / ${H}`,
        }}
      >
        <svg
          width="100%"
          height="100%"
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={`Histogram of ${corpus.length} verified cases by year, ${minYear} to ${maxYear}`}
          style={{ display: "block", position: "absolute", inset: 0 }}
        >
          {/* baseline */}
          <line
            x1={padL}
            x2={W - padR}
            y1={chartH}
            y2={chartH}
            stroke="var(--qgi-border)"
            strokeWidth={1}
          />
          {/* bars */}
          {years.map((year) => {
            const count = byYear.get(year)!.length;
            const h = barHeight(count);
            const x = xCenter(year) - barW / 2;
            const isHovered = hoveredYear === year;
            return (
              <rect
                key={year}
                x={x}
                y={chartH - h}
                width={barW}
                height={h}
                rx={Math.min(2, barW / 2)}
                fill={familyColor}
                opacity={hoveredYear == null ? 0.82 : isHovered ? 1 : 0.3}
                style={{ transition: "opacity 120ms ease" }}
              />
            );
          })}
          {/* year ticks */}
          {ticks.map((y) => (
            <text
              key={`tick-${y}`}
              x={xCenter(y)}
              y={chartH + 14}
              fontSize="9"
              textAnchor="middle"
              fill="var(--qgi-text-dim)"
              fontFamily="ui-monospace, monospace"
            >
              {y}
            </text>
          ))}
        </svg>

        {/* Hover/focus hit-areas: one transparent button per year column,
            covering the full bar height so the whole column is hoverable. */}
        {years.map((year) => {
          const leftPct = ((xCenter(year) - colW / 2) / W) * 100;
          const wPct = (colW / W) * 100;
          const count = byYear.get(year)!.length;
          return (
            <button
              key={`hit-${year}`}
              type="button"
              aria-label={`${year}: ${count} case${count === 1 ? "" : "s"}`}
              onMouseEnter={() => showYear(year)}
              onMouseLeave={scheduleHide}
              onFocus={() => showYear(year)}
              onBlur={scheduleHide}
              style={{
                position: "absolute",
                left: `${leftPct}%`,
                top: 0,
                width: `${wPct}%`,
                height: `${(chartH / H) * 100}%`,
                padding: 0,
                border: "none",
                background: "transparent",
                cursor: "pointer",
                outline: "none",
              }}
            />
          );
        })}

        {/* Single popup, repositioned per hovered year, listing every case. */}
        {hoveredYear != null &&
          hoveredEvents.length > 0 &&
          (() => {
            const xPct = (xCenter(hoveredYear) / W) * 100;
            // Horizontal placement: clamp at the edges so the popup stays on-card.
            let tx = "-50%";
            if (xPct < 26)
              tx = "-8px"; // near left edge: open to the right
            else if (xPct > 74) tx = "calc(-100% + 8px)"; // near right edge: open left
            return (
              <div
                role="tooltip"
                onMouseEnter={cancelHide}
                onMouseLeave={scheduleHide}
                style={{
                  position: "absolute",
                  left: `${xPct}%`,
                  top: 0,
                  transform: `translate(${tx}, calc(-100% - 8px))`,
                  zIndex: 50,
                  minWidth: "230px",
                  maxWidth: "330px",
                  maxHeight: "240px",
                  overflowY: "auto",
                  padding: "9px 11px 10px",
                  background: "var(--qgi-surface-2)",
                  border: "1px solid var(--qgi-border)",
                  borderLeft: `2px solid ${familyColor}`,
                  borderRadius: "5px",
                  boxShadow: "0 4px 16px rgba(0,0,0,0.4)",
                  fontSize: "11px",
                  lineHeight: 1.5,
                  color: "var(--qgi-text)",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "baseline",
                    gap: "8px",
                    marginBottom: "7px",
                    fontFamily: "ui-monospace, monospace",
                  }}
                >
                  <span style={{ color: familyColor, fontWeight: 700, fontSize: "13px" }}>
                    {hoveredYear}
                  </span>
                  <span style={{ color: "var(--qgi-text-dim)", fontSize: "10px" }}>
                    {hoveredEvents.length} case{hoveredEvents.length === 1 ? "" : "s"}
                  </span>
                </div>
                <ul
                  style={{
                    listStyle: "none",
                    margin: 0,
                    padding: 0,
                    display: "flex",
                    flexDirection: "column",
                    gap: "7px",
                  }}
                >
                  {hoveredEvents.map((ev, i) => {
                    // Prefer the event's own ISO-2 (the bake ships a lowercase
                    // 2-letter code); fall back to resolving from the name. This
                    // fixes cases like Panama where the name lookup missed and
                    // the emoji fallback rendered as bare letters on Windows.
                    const iso =
                      ev.country_iso && /^[a-z]{2}$/i.test(ev.country_iso)
                        ? ev.country_iso.toLowerCase()
                        : iso2For(ev.country);
                    return (
                      <li
                        key={`${ev.country_iso}-${i}`}
                        style={{ display: "flex", gap: "7px", alignItems: "flex-start" }}
                      >
                        {iso ? (
                          <img
                            src={`https://flagcdn.com/16x12/${iso}.png`}
                            alt={`${ev.country} flag`}
                            width={16}
                            height={12}
                            style={{
                              borderRadius: "1px",
                              flex: "0 0 16px",
                              marginTop: "2px",
                            }}
                          />
                        ) : (
                          <span
                            aria-hidden="true"
                            style={{ fontSize: "12px", flex: "0 0 16px" }}
                          >
                            {ev.flag_emoji}
                          </span>
                        )}
                        <span style={{ minWidth: 0, lineHeight: 1.45 }}>
                          <span style={{ color: "var(--qgi-text)", fontWeight: 600 }}>
                            {ev.country}
                          </span>
                          {ev.reason ? (
                            <span style={{ color: "var(--qgi-text-muted)" }}>
                              {" "}
                              {ev.reason}
                            </span>
                          ) : null}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          })()}
      </div>

      <footer
        style={{
          marginTop: "14px",
          paddingTop: "10px",
          borderTop: "1px dashed var(--qgi-border)",
          fontFamily: "ui-monospace, monospace",
          fontSize: "10px",
          color: "var(--qgi-text-dim)",
          letterSpacing: "0.3px",
        }}
      >
        {totalEventsInCorpus.toLocaleString()} verified events in this trend&apos;s corpus
        · {minYear}–{maxYear}
      </footer>
    </section>
  );
}
