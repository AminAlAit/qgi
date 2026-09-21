"use client";

/**
 * Indicator taxonomy — the indicators counterpart to TaxonomyHorizontalTree.
 *
 * Same horizontal L→R dendrogram, but the three layers are
 *   provider (World Bank / V-Dem / UCDP / FAOSTAT / …8 total)  →  theme  →
 *   indicator.
 * Default view shows provider → theme; click a theme to reveal its
 * indicators. Hover an indicator to surface how many recipes it feeds.
 *
 * Source: data/indicator-catalog.json — 250 indicators across 8 providers
 * (109 originally ingested + 136 activated from the 250-run bench + 5 top-ups).
 * Rows
 * with recipe_count:0 render as "tracked" (in the catalog, not yet feeding a
 * trend). Provider colour + order come from lib/indicator-providers.
 *
 * Mobile (<640px): replaces the fixed 880px SVG with a vertical accordion
 * list so no content is clipped.
 */
import { useState, useMemo } from "react";
import { useResponsiveLayout } from "@/lib/hooks/useMediaQuery";
import catalog from "@/data/indicator-catalog.json";
import { PROVIDER_COLOR, PROVIDER_ORDER } from "@/lib/indicator-providers";

interface CatalogEntry {
  code: string;
  name: string;
  provider: string;
  theme: string;
  description?: string;
  recipe_count?: number;
  in_play?: boolean;
}

const COL_X = { L1: 24, L2: 250, L3: 500 };
const ROW_HEIGHT = 30;
const PADDING_TOP = 20;
const VIEW_W = 880; // wide enough that long WB indicator names don't collide with the count
const LEAF_COUNT_X = 870; // far-right, right-aligned recipe-usage label
const FONT_FAMILY = "ui-monospace, SFMono-Regular, Menlo, monospace";

function truncate(s: string, n = 46): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

/** Truncate theme labels in the SVG so they don't collide with the count badge
 *  on tablet (768px, where the 880px viewBox scales to ~88% → ~175px available). */
function truncateTheme(s: string, n = 28): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

type Provider = {
  name: string;
  color: string;
  count: number;
  themes: { theme: string; indicators: CatalogEntry[] }[];
};

export default function IndicatorTaxonomyTree() {
  const all = (catalog as { indicators: CatalogEntry[] }).indicators;

  // Group provider → theme → indicators.
  const providers = useMemo<Provider[]>(() => {
    const byProvider = new Map<string, Map<string, CatalogEntry[]>>();
    for (const e of all) {
      if (!byProvider.has(e.provider)) byProvider.set(e.provider, new Map());
      const themes = byProvider.get(e.provider)!;
      if (!themes.has(e.theme)) themes.set(e.theme, []);
      themes.get(e.theme)!.push(e);
    }
    const order = (p: string) => {
      const i = PROVIDER_ORDER.indexOf(p);
      return i === -1 ? 99 : i;
    };
    return [...byProvider.entries()]
      .sort((a, b) => order(a[0]) - order(b[0]))
      .map(([name, themes]) => ({
        name,
        color: PROVIDER_COLOR[name] || "#7B5EE6",
        count: [...themes.values()].reduce((n, arr) => n + arr.length, 0),
        themes: [...themes.entries()]
          .map(([theme, indicators]) => ({
            theme,
            indicators: indicators.sort(
              (x, y) => (y.recipe_count || 0) - (x.recipe_count || 0)
            ),
          }))
          .sort((a, b) => b.indicators.length - a.indicators.length),
      }));
  }, [all]);

  const [expanded, setExpanded] = useState<Set<string>>(new Set()); // "provider::theme"
  const [hovered, setHovered] = useState<string | null>(null);

  // Below 640px, swap the fixed-width SVG dendrogram for a vertical accordion.
  // Combined hook flips mounted + isMobile in one commit so SSR never emits the
  // wide (880px) SVG on a phone and there is no desktop-branch frame post-mount.
  const { mounted, isMobile } = useResponsiveLayout("(max-width: 639px)");

  const layout = useMemo(() => {
    const rows: {
      type: "L1" | "L2" | "L3";
      provider: Provider;
      theme?: string;
      ind?: CatalogEntry;
      x: number;
      y: number;
    }[] = [];
    let cursorY = PADDING_TOP;

    providers.forEach((p) => {
      const start = cursorY;
      p.themes.forEach((t) => {
        const key = `${p.name}::${t.theme}`;
        rows.push({ type: "L2", provider: p, theme: t.theme, x: COL_X.L2, y: cursorY });
        cursorY += ROW_HEIGHT;
        if (expanded.has(key)) {
          t.indicators.forEach((ind) => {
            rows.push({
              type: "L3",
              provider: p,
              theme: t.theme,
              ind,
              x: COL_X.L3,
              y: cursorY,
            });
            cursorY += ROW_HEIGHT * 0.8;
          });
        }
      });
      const end = cursorY;
      const midY = (start + end - ROW_HEIGHT) / 2;
      rows.push({ type: "L1", provider: p, x: COL_X.L1, y: midY });
      cursorY += ROW_HEIGHT * 0.6;
    });
    return { rows, totalHeight: cursorY + 20 };
  }, [providers, expanded]);

  function toggle(key: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const allKeys = providers.flatMap((p) => p.themes.map((t) => `${p.name}::${t.theme}`));

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
          Loading indicator taxonomy…
        </p>
      </div>
    );
  }

  // ── Mobile accordion (< 640 px) ──────────────────────────────────────────
  if (isMobile) {
    return (
      <div
        className="rounded-lg border divide-y divide-[var(--qgi-border)]"
        style={{
          borderColor: "var(--qgi-border)",
          backgroundColor: "var(--qgi-surface)",
        }}
      >
        {providers.map((p) => {
          const provKey = `prov::${p.name}`;
          const isProvOpen = expanded.has(provKey);
          return (
            <div key={p.name} style={{ borderColor: "var(--qgi-border)" }}>
              {/* Provider header */}
              <button
                type="button"
                aria-expanded={isProvOpen}
                onClick={() => toggle(provKey)}
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
                      backgroundColor: p.color,
                      flexShrink: 0,
                    }}
                  />
                  <span
                    className="text-[13px] font-medium"
                    style={{ color: "var(--qgi-text)" }}
                  >
                    {p.name}
                  </span>
                </span>
                <span className="flex items-center gap-2 shrink-0">
                  <span
                    className="text-[11px]"
                    style={{ color: "var(--qgi-text-muted)" }}
                  >
                    {p.count} indicators
                  </span>
                  <span style={{ color: "var(--qgi-text-muted)", fontSize: 11 }}>
                    {isProvOpen ? "▾" : "▸"}
                  </span>
                </span>
              </button>

              {/* Theme list */}
              {isProvOpen && (
                <div
                  className="pb-1"
                  style={{ borderTop: "1px solid var(--qgi-border)" }}
                >
                  {p.themes.map((t) => {
                    const key = `${p.name}::${t.theme}`;
                    const isThemeOpen = expanded.has(key);
                    return (
                      <div key={key}>
                        <button
                          type="button"
                          aria-expanded={isThemeOpen}
                          onClick={() => toggle(key)}
                          className="w-full flex items-center justify-between px-4 py-2 text-left"
                          style={{ fontFamily: FONT_FAMILY }}
                        >
                          <span
                            className="text-[12px]"
                            style={{ color: "var(--qgi-text)" }}
                          >
                            {isThemeOpen ? "▾" : "▸"} {t.theme}
                          </span>
                          <span
                            className="text-[11px] shrink-0 ml-2"
                            style={{ color: "var(--qgi-accent)" }}
                          >
                            {t.indicators.length}
                          </span>
                        </button>
                        {/* Indicator leaves */}
                        {isThemeOpen && (
                          <div className="pl-6 pb-1">
                            {t.indicators.map((ind) => {
                              const fed = (ind.recipe_count || 0) > 0;
                              return (
                                <div
                                  key={ind.code}
                                  className="flex items-start justify-between py-1 px-2 gap-2"
                                >
                                  <span
                                    className="text-[11px] leading-snug"
                                    style={{ color: "var(--qgi-text-muted)" }}
                                  >
                                    · {ind.name}
                                  </span>
                                  <span
                                    className="text-[10px] shrink-0"
                                    style={{ color: "var(--qgi-text-muted)" }}
                                  >
                                    {fed
                                      ? `${ind.recipe_count} trend${ind.recipe_count === 1 ? "" : "s"}`
                                      : "tracked"}
                                  </span>
                                </div>
                              );
                            })}
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
        <div className="px-3 py-2">
          <p className="text-[11px]" style={{ color: "var(--qgi-text-muted)" }}>
            A filled dot (on desktop) means the indicator currently feeds at least one
            trend; &ldquo;tracked&rdquo; means it is monitored but not yet used.
          </p>
        </div>
      </div>
    );
  }

  // ── Desktop / tablet SVG dendrogram (>= 640 px) ──────────────────────────
  return (
    <div
      className="rounded-lg border p-2 overflow-x-auto"
      style={{ borderColor: "var(--qgi-border)", backgroundColor: "var(--qgi-surface)" }}
    >
      <svg
        viewBox={`0 0 ${VIEW_W} ${layout.totalHeight}`}
        width="100%"
        style={{ minWidth: VIEW_W, height: layout.totalHeight, fontFamily: FONT_FAMILY }}
      >
        {/* Connectors provider → theme */}
        {layout.rows
          .filter((r) => r.type === "L2")
          .map((r, i) => {
            const l1 = layout.rows.find(
              (rr) => rr.type === "L1" && rr.provider.name === r.provider.name
            );
            if (!l1) return null;
            const startX = COL_X.L1 + 96;
            const endX = COL_X.L2 - 6;
            const midX = (startX + endX) / 2;
            return (
              <path
                key={`c1-${i}`}
                d={`M ${startX} ${l1.y} C ${midX} ${l1.y} ${midX} ${r.y} ${endX} ${r.y}`}
                fill="none"
                stroke={r.provider.color}
                strokeWidth="1"
                opacity="0.4"
              />
            );
          })}

        {/* Connectors theme → indicator */}
        {layout.rows
          .filter((r) => r.type === "L3")
          .map((r, i) => {
            const l2 = layout.rows.find(
              (rr) =>
                rr.type === "L2" &&
                rr.provider.name === r.provider.name &&
                rr.theme === r.theme
            );
            if (!l2) return null;
            const startX = COL_X.L2 + 196;
            const endX = COL_X.L3 - 6;
            const midX = (startX + endX) / 2;
            return (
              <path
                key={`c2-${i}`}
                d={`M ${startX} ${l2.y} C ${midX} ${l2.y} ${midX} ${r.y} ${endX} ${r.y}`}
                fill="none"
                stroke="#5a6270"
                strokeWidth="0.6"
                opacity="0.4"
              />
            );
          })}

        {/* Provider nodes */}
        {layout.rows
          .filter((r) => r.type === "L1")
          .map((r, i) => (
            <g key={`l1-${i}`}>
              <circle cx={r.x} cy={r.y} r="4" fill={r.provider.color} />
              <text
                x={r.x + 10}
                y={r.y + 4}
                fontSize="12"
                fill="var(--qgi-text)"
                style={{ fontWeight: 500 }}
              >
                {r.provider.name}
              </text>
              <text
                x={r.x + 10}
                y={r.y + 18}
                fontSize="9"
                fill="var(--qgi-text-muted)"
                letterSpacing="0.5"
              >
                {r.provider.count} indicators · {r.provider.themes.length} themes
              </text>
            </g>
          ))}

        {/* Theme nodes — clickable */}
        {layout.rows
          .filter((r) => r.type === "L2")
          .map((r, i) => {
            const key = `${r.provider.name}::${r.theme}`;
            const isOpen = expanded.has(key);
            const count =
              r.provider.themes.find((t) => t.theme === r.theme)?.indicators.length || 0;
            return (
              <g
                key={`l2-${i}`}
                onClick={() => toggle(key)}
                style={{ cursor: "pointer" }}
              >
                <rect
                  x={r.x - 4}
                  y={r.y - 10}
                  width="202"
                  height="22"
                  rx="3"
                  fill="transparent"
                  className="hover:fill-white/5 transition-colors"
                />
                <circle cx={r.x} cy={r.y} r="3" fill={r.provider.color} />
                <text x={r.x + 8} y={r.y + 2} fontSize="11" fill="var(--qgi-text)">
                  {isOpen ? "▾" : "▸"} {truncateTheme(r.theme ?? "")}
                </text>
                <text
                  x={r.x + 190}
                  y={r.y + 2}
                  fontSize="10"
                  textAnchor="end"
                  fill="var(--qgi-accent)"
                >
                  {count}
                </text>
              </g>
            );
          })}

        {/* Indicator leaves */}
        {layout.rows
          .filter((r) => r.type === "L3")
          .map((r, i) => {
            const isHov = hovered === r.ind!.code;
            const fed = (r.ind!.recipe_count || 0) > 0;
            return (
              <g
                key={`l3-${i}`}
                onMouseEnter={() => setHovered(r.ind!.code)}
                onMouseLeave={() => setHovered(null)}
              >
                <circle
                  cx={r.x}
                  cy={r.y}
                  r="2"
                  fill={fed ? r.provider.color : "#5a6270"}
                  opacity={fed ? 0.9 : 0.6}
                />
                <text
                  x={r.x + 8}
                  y={r.y + 2}
                  fontSize="10"
                  fill={isHov ? "var(--qgi-text)" : "var(--qgi-text-muted)"}
                >
                  {truncate(r.ind!.name)}
                </text>
                <text
                  x={LEAF_COUNT_X}
                  y={r.y + 2}
                  fontSize="9"
                  textAnchor="end"
                  fill="var(--qgi-text-muted)"
                >
                  {fed
                    ? `${r.ind!.recipe_count} trend${r.ind!.recipe_count === 1 ? "" : "s"}`
                    : "tracked"}
                </text>
              </g>
            );
          })}
      </svg>

      <div className="mt-3 mb-1 px-2 flex items-center justify-between flex-wrap gap-2">
        <p className="text-[11px]" style={{ color: "var(--qgi-text-muted)" }}>
          A filled dot means the indicator currently feeds at least one trend; a grey dot
          means it is tracked but not yet used by one.
        </p>
        <button
          type="button"
          aria-expanded={expanded.size > 0}
          onClick={() => setExpanded(expanded.size > 0 ? new Set() : new Set(allKeys))}
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
