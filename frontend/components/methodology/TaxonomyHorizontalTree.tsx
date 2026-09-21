"use client";

/**
 * Horizontal L→R dendrogram (#522, simplified 2026-04-29).
 *
 * Default view: 8 master groups (left) → 52 sub-categories (right). Layer 3
 * (71 leaf categories) is hidden by default; click a sub-category to expand
 * its layer-3 children. Click again to collapse.
 *
 * Pure SVG — no echarts. Editorial / QGI-elegant. Hover shows event count.
 *
 * Mobile (<640px): replaces the SVG with a vertical accordion list so no
 * content is clipped by the fixed 760px minWidth.
 */
import { useState, useMemo } from "react";
import { useResponsiveLayout } from "@/lib/hooks/useMediaQuery";
import taxonomy from "@/data/taxonomy-with-counts.json";

type Layer1 = {
  id: string;
  label: string;
  display_label?: string;
  color_hint?: string;
  event_count?: number;
  layer2: {
    id: string;
    label: string;
    event_count?: number;
    layer3: string[];
  }[];
};

function prettyL3(s: string): string {
  return s
    .split("_")
    .map((w) => (w.length <= 2 ? w : w[0].toUpperCase() + w.slice(1)))
    .join(" ");
}

// Layout constants
const COL_X = { L1: 24, L2: 280, L3: 540 };
const ROW_HEIGHT = 30; // vertical spacing between L2 nodes
const PADDING_TOP = 20;
const FONT_FAMILY = "ui-monospace, SFMono-Regular, Menlo, monospace";

export default function TaxonomyHorizontalTree() {
  const data = taxonomy as {
    layer1: Layer1[];
    layer3_counts: Record<string, number>;
    summary: { layer1_count: number; layer2_count: number; layer3_count: number };
  };
  const [expanded, setExpanded] = useState<Set<string>>(new Set()); // L2 ids that have L3 visible
  const [hoveredL3, setHoveredL3] = useState<string | null>(null);
  const [mobileOpen, setMobileOpen] = useState<Set<string>>(new Set()); // L1 ids open (mobile accordion)

  // Below 640px, swap the fixed-width SVG dendrogram for a vertical accordion.
  // Combined hook flips mounted + isMobile in one commit, so the server never
  // emits the wide (760px) SVG on a phone (which would flash a horizontal
  // scrollbar) and there is no desktop-branch frame after mount.
  const { mounted, isMobile } = useResponsiveLayout("(max-width: 639px)");

  // Compute the layout: every L1 group occupies a vertical span equal to its L2 children
  // (plus expanded L3 children if any).
  const layout = useMemo(() => {
    const rows: {
      type: "L1" | "L2" | "L3";
      l1: Layer1;
      l2?: Layer1["layer2"][number];
      l3?: string;
      x: number;
      y: number;
      count: number;
    }[] = [];
    let cursorY = PADDING_TOP;

    data.layer1.forEach((l1) => {
      const l1Start = cursorY;
      l1.layer2.forEach((l2) => {
        const l2Y = cursorY;
        rows.push({
          type: "L2",
          l1,
          l2,
          x: COL_X.L2,
          y: l2Y,
          count: l2.event_count || 0,
        });
        cursorY += ROW_HEIGHT;

        if (expanded.has(l2.id)) {
          l2.layer3.forEach((cat) => {
            rows.push({
              type: "L3",
              l1,
              l2,
              l3: cat,
              x: COL_X.L3,
              y: cursorY,
              count: data.layer3_counts[cat] || 0,
            });
            cursorY += ROW_HEIGHT * 0.8;
          });
        }
      });
      // Place L1 label at the vertical midpoint of its children block
      const l1End = cursorY;
      const l1Y = (l1Start + l1End - ROW_HEIGHT) / 2;
      rows.push({ type: "L1", l1, x: COL_X.L1, y: l1Y, count: l1.event_count || 0 });
      cursorY += ROW_HEIGHT * 0.5; // group spacing
    });

    return { rows, totalHeight: cursorY + 20 };
  }, [data, expanded]);

  function toggle(l2id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(l2id)) next.delete(l2id);
      else next.add(l2id);
      return next;
    });
  }

  // ── Mobile accordion (< 640 px) ──────────────────────────────────────────
  function toggleL1Mobile(id: string) {
    setMobileOpen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  function toggleL2Mobile(l2id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(l2id)) next.delete(l2id);
      else next.add(l2id);
      return next;
    });
  }

  if (!mounted) {
    return (
      <div
        className="rounded-lg border"
        style={{
          borderColor: "var(--qgi-border)",
          backgroundColor: "var(--qgi-surface)",
          minHeight: 240,
        }}
      >
        <p role="status" aria-live="polite" className="sr-only">
          Loading taxonomy…
        </p>
      </div>
    );
  }

  if (isMobile) {
    return (
      <div>
        <p className="text-sm mb-4 leading-relaxed" style={{ color: "var(--qgi-text)" }}>
          Every verified event is mapped to one of {data.summary.layer3_count} canonical
          leaf categories, organised in {data.summary.layer1_count} master groups and{" "}
          {data.summary.layer2_count} sub-categories. Tap a group to expand.
        </p>
        <div
          className="rounded-lg border divide-y divide-[var(--qgi-border)]"
          style={{
            borderColor: "var(--qgi-border)",
            backgroundColor: "var(--qgi-surface)",
          }}
        >
          {data.layer1.map((l1) => {
            const isOpen = mobileOpen.has(l1.id);
            return (
              <div key={l1.id} style={{ borderColor: "var(--qgi-border)" }}>
                {/* L1 header */}
                <button
                  type="button"
                  aria-expanded={isOpen}
                  onClick={() => toggleL1Mobile(l1.id)}
                  className="w-full flex items-center justify-between px-3 py-2.5 text-left"
                  style={{ fontFamily: FONT_FAMILY }}
                >
                  <span className="flex items-center gap-2">
                    <span
                      style={{
                        display: "inline-block",
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        backgroundColor: l1.color_hint || "#7B5EE6",
                        flexShrink: 0,
                      }}
                    />
                    <span
                      className="text-[13px] font-medium"
                      style={{ color: "var(--qgi-text)" }}
                    >
                      {l1.display_label || l1.label}
                    </span>
                  </span>
                  <span className="flex items-center gap-2 shrink-0">
                    <span
                      className="text-[11px]"
                      style={{ color: "var(--qgi-text-muted)" }}
                    >
                      {(l1.event_count || 0).toLocaleString()} events
                    </span>
                    <span style={{ color: "var(--qgi-text-muted)", fontSize: 11 }}>
                      {isOpen ? "▾" : "▸"}
                    </span>
                  </span>
                </button>

                {/* L2 list */}
                {isOpen && (
                  <div
                    className="pb-1"
                    style={{ borderTop: "1px solid var(--qgi-border)" }}
                  >
                    {l1.layer2.map((l2) => {
                      const l2Open = expanded.has(l2.id);
                      return (
                        <div key={l2.id}>
                          <button
                            type="button"
                            aria-expanded={l2Open}
                            onClick={() => toggleL2Mobile(l2.id)}
                            className="w-full flex items-center justify-between px-4 py-2 text-left"
                            style={{ fontFamily: FONT_FAMILY }}
                          >
                            <span
                              className="text-[12px]"
                              style={{ color: "var(--qgi-text)" }}
                            >
                              {l2Open ? "▾" : "▸"} {l2.label}
                            </span>
                            <span
                              className="text-[11px] shrink-0 ml-2"
                              style={{ color: "var(--qgi-accent)" }}
                            >
                              {(l2.event_count || 0).toLocaleString()}
                            </span>
                          </button>
                          {/* L3 leaves */}
                          {l2Open && (
                            <div className="pl-6 pb-1">
                              {l2.layer3.map((cat) => (
                                <div
                                  key={cat}
                                  className="flex items-center justify-between py-1 px-2"
                                >
                                  <span
                                    className="text-[11px]"
                                    style={{ color: "var(--qgi-text-muted)" }}
                                  >
                                    · {prettyL3(cat)}
                                  </span>
                                  <span
                                    className="text-[10px] shrink-0 ml-2"
                                    style={{ color: "var(--qgi-text-muted)" }}
                                  >
                                    {(data.layer3_counts[cat] || 0).toLocaleString()}
                                  </span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
        <p className="text-[11px] mt-3" style={{ color: "var(--qgi-text-muted)" }}>
          Counts are verified events only. Categories with zero events have not yet had
          any verified events curated against them.
        </p>
      </div>
    );
  }

  // ── Desktop / tablet SVG dendrogram (>= 640 px) ──────────────────────────
  return (
    <div>
      <p
        className="text-sm mb-6 leading-relaxed max-w-2xl"
        style={{ color: "var(--qgi-text)" }}
      >
        Every verified event is mapped to one of {data.summary.layer3_count} canonical
        leaf categories, organised in {data.summary.layer1_count} master groups and{" "}
        {data.summary.layer2_count} sub-categories. Click a sub-category to reveal its
        leaf-level types.
      </p>

      <div
        className="rounded-lg border p-2 overflow-x-auto"
        style={{
          borderColor: "var(--qgi-border)",
          backgroundColor: "var(--qgi-surface)",
        }}
      >
        <svg
          viewBox={`0 0 760 ${layout.totalHeight}`}
          width="100%"
          style={{ minWidth: 760, height: layout.totalHeight, fontFamily: FONT_FAMILY }}
        >
          {/* Connectors L1 → L2 */}
          {layout.rows
            .filter((r) => r.type === "L2")
            .map((r, i) => {
              const l1Row = layout.rows.find(
                (rr) => rr.type === "L1" && rr.l1.id === r.l1.id
              );
              if (!l1Row) return null;
              const startX = COL_X.L1 + 100;
              const endX = COL_X.L2 - 6;
              const startY = l1Row.y;
              const endY = r.y;
              const midX = (startX + endX) / 2;
              return (
                <path
                  key={`l1l2-${i}`}
                  d={`M ${startX} ${startY} C ${midX} ${startY} ${midX} ${endY} ${endX} ${endY}`}
                  fill="none"
                  stroke={r.l1.color_hint || "#7B5EE6"}
                  strokeWidth="1"
                  opacity="0.4"
                />
              );
            })}

          {/* Connectors L2 → L3 (only for expanded L2 rows) */}
          {layout.rows
            .filter((r) => r.type === "L3")
            .map((r, i) => {
              const l2Row = layout.rows.find(
                (rr) => rr.type === "L2" && rr.l2?.id === r.l2?.id
              );
              if (!l2Row) return null;
              const startX = COL_X.L2 + 180;
              const endX = COL_X.L3 - 6;
              const startY = l2Row.y;
              const endY = r.y;
              const midX = (startX + endX) / 2;
              return (
                <path
                  key={`l2l3-${i}`}
                  d={`M ${startX} ${startY} C ${midX} ${startY} ${midX} ${endY} ${endX} ${endY}`}
                  fill="none"
                  stroke="#5a6270"
                  strokeWidth="0.6"
                  opacity="0.4"
                />
              );
            })}

          {/* Layer 1 nodes (master groups) */}
          {layout.rows
            .filter((r) => r.type === "L1")
            .map((r, i) => (
              <g key={`l1-${i}`}>
                <circle cx={r.x} cy={r.y} r="4" fill={r.l1.color_hint || "#7B5EE6"} />
                <text
                  x={r.x + 10}
                  y={r.y + 4}
                  fontSize="12"
                  fill="var(--qgi-text)"
                  style={{ fontWeight: 500 }}
                >
                  {r.l1.display_label || r.l1.label}
                </text>
                <text
                  x={r.x + 10}
                  y={r.y + 18}
                  fontSize="9"
                  fill="var(--qgi-text-muted)"
                  letterSpacing="0.5"
                >
                  {r.count.toLocaleString()} events · {r.l1.layer2.length} sub
                </text>
              </g>
            ))}

          {/* Layer 2 nodes (sub-categories) — clickable */}
          {layout.rows
            .filter((r) => r.type === "L2")
            .map((r, i) => {
              const isExpanded = expanded.has(r.l2!.id);
              return (
                <g
                  key={`l2-${i}`}
                  onClick={() => toggle(r.l2!.id)}
                  style={{ cursor: "pointer" }}
                >
                  <rect
                    x={r.x - 4}
                    y={r.y - 10}
                    width="186"
                    height="22"
                    rx="3"
                    fill="transparent"
                    className="hover:fill-white/5 transition-colors"
                  />
                  <circle cx={r.x} cy={r.y} r="3" fill={r.l1.color_hint || "#7B5EE6"} />
                  <text x={r.x + 8} y={r.y + 2} fontSize="11" fill="var(--qgi-text)">
                    {isExpanded ? "▾" : "▸"} {r.l2!.label}
                  </text>
                  <text
                    x={r.x + 174}
                    y={r.y + 2}
                    fontSize="10"
                    textAnchor="end"
                    fill="var(--qgi-accent)"
                  >
                    {r.count.toLocaleString()}
                  </text>
                </g>
              );
            })}

          {/* Layer 3 leaves — visible only when expanded */}
          {layout.rows
            .filter((r) => r.type === "L3")
            .map((r, i) => (
              <g
                key={`l3-${i}`}
                onMouseEnter={() => setHoveredL3(r.l3!)}
                onMouseLeave={() => setHoveredL3(null)}
              >
                <circle cx={r.x} cy={r.y} r="2" fill="#5a6270" />
                <text
                  x={r.x + 8}
                  y={r.y + 2}
                  fontSize="10"
                  fill={hoveredL3 === r.l3 ? "var(--qgi-text)" : "var(--qgi-text-muted)"}
                >
                  {prettyL3(r.l3!)}
                </text>
                <text
                  x={r.x + 174}
                  y={r.y + 2}
                  fontSize="9"
                  textAnchor="end"
                  fill="var(--qgi-text-muted)"
                >
                  {r.count.toLocaleString()}
                </text>
              </g>
            ))}
        </svg>
      </div>

      <div className="mt-4 flex items-center justify-between flex-wrap gap-2">
        <p className="text-[11px]" style={{ color: "var(--qgi-text-muted)" }}>
          Counts are verified events only. Categories with zero events have not yet had
          any verified events curated against them.
        </p>
        <button
          type="button"
          aria-expanded={expanded.size > 0}
          onClick={() => {
            const allL2Ids = data.layer1.flatMap((l1) => l1.layer2.map((l2) => l2.id));
            const allExpanded = expanded.size === allL2Ids.length;
            setExpanded(allExpanded ? new Set() : new Set(allL2Ids));
          }}
          className="text-[11px] tracking-wider uppercase px-3 py-1.5 rounded transition-colors hover:bg-white/5"
          style={{
            color: "var(--qgi-text-muted)",
            border: "1px solid var(--qgi-border)",
          }}
        >
          {expanded.size > 0 ? "Collapse all" : "Expand all"}
        </button>
      </div>
    </div>
  );
}
