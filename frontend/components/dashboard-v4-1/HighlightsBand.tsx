/**
 * HighlightsBand — V4.1 rebuild.
 *
 * Changes from V4:
 * - Wrapped in PanelBase (calm slate-blue, aggregator accent).
 * - Dropped the "vintage {vintage}" sub-text from the band header; the
 *   page-level vintage chip now owns that information.
 * - vintage prop kept to avoid a breaking change to callers, but not rendered.
 *
 * Unchanged from V4:
 * - Highlight interface (same shape; imported locally to avoid coupling to V4).
 * - 4-tile responsive auto-fit grid (minmax 260px).
 * - Per-tile family-color left border via familyColor().
 * - Per-tile source_label (Talia-ratified primary nav cue).
 * - Per-tile tier chip (current state; preserve template data as-is).
 * - All per-tile captions (Talia-ratified: "do not rewrite").
 */
import Link from "next/link";
import type { Route } from "next";
import { createElement } from "react";
import type { LucideIcon } from "lucide-react";
import { iconForRecipe } from "@/lib/te-mock/icons";
import { getRecipe } from "@/lib/te-mock/recipes";
import { familyColor } from "@/lib/te-mock/l1-families";
import { PanelBase } from "./PanelBase";

export interface Highlight {
  source: "risk-board" | "compound-risk" | "analogues" | "recipe-tracker";
  source_label: string;
  href: string;
  headline: string;
  caption: string;
  metric: string;
  recipe_id?: string;
  icon?: LucideIcon;
  color?: string;
  tier_label: string;
  tier_color: string;
}

export function HighlightsBand({
  highlights,
  vintage: _vintage,
}: {
  highlights: Highlight[];
  /** Accepted for API compatibility; not rendered here (page-level chip owns it). */
  vintage?: string;
}) {
  return (
    <PanelBase
      title="Today's highlights"
      caption="Latest signal from each surface. Tap a tile to open the full page."
      accent="#5B7E99"
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          gap: "12px",
        }}
      >
        {highlights.map((h, i) => (
          <HighlightTile key={`${h.source}-${i}`} h={h} />
        ))}
      </div>
    </PanelBase>
  );
}

function HighlightTile({ h }: { h: Highlight }) {
  const recipe = h.recipe_id ? getRecipe(h.recipe_id) : undefined;
  // createElement avoids the react-hooks/static-components lint rule that fires
  // on `const Icon = ...; <Icon/>` JSX patterns (same pattern as V4).
  const renderIcon = (size: number) => {
    if (h.recipe_id) {
      return createElement(iconForRecipe(h.recipe_id), { size, strokeWidth: 1.6 });
    }
    if (h.icon) {
      return createElement(h.icon, { size, strokeWidth: 1.6 });
    }
    return <FallbackIcon size={size} />;
  };
  const color = recipe
    ? familyColor(recipe.l1_id, recipe.l1_color)
    : (h.color ?? "var(--qgi-accent)");
  const isWalked = recipe?.status === "walked_no_graduation";

  return (
    <Link
      href={h.href as Route}
      style={{ textDecoration: "none", color: "inherit", display: "block" }}
    >
      <article
        style={{
          background: "var(--qgi-surface)",
          border: "1px solid var(--qgi-border)",
          borderLeft: `3px solid ${color}`,
          borderRadius: "8px",
          padding: "14px 16px",
          display: "flex",
          flexDirection: "column",
          gap: "10px",
          minHeight: "152px",
          cursor: "pointer",
          transition: "border-color 0.15s",
        }}
      >
        {/* Row 1: source label + tier chip */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <span
            style={{
              fontSize: "9.5px",
              letterSpacing: "1.4px",
              fontFamily: "ui-monospace, monospace",
              color: "var(--qgi-text-dim)",
              textTransform: "uppercase",
            }}
          >
            from /{h.source}
          </span>
          <span
            style={{
              fontSize: "9px",
              padding: "2px 7px",
              borderRadius: "3px",
              border: `1px ${isWalked ? "dashed" : "solid"} ${h.tier_color}`,
              color: h.tier_color,
              background: `${h.tier_color}1A`,
              fontFamily: "ui-monospace, monospace",
              letterSpacing: "0.3px",
              whiteSpace: "nowrap",
            }}
          >
            {h.tier_label}
          </span>
        </div>

        {/* Row 2: icon + headline + caption */}
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div
            aria-hidden="true"
            style={{
              width: "40px",
              height: "40px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "var(--qgi-bg)",
              border: `1px solid ${color}`,
              borderRadius: "6px",
              color,
              flexShrink: 0,
            }}
          >
            {renderIcon(22)}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                fontSize: "15px",
                fontWeight: 600,
                lineHeight: 1.2,
                color: "var(--qgi-text)",
              }}
            >
              {h.headline}
            </div>
            <div
              style={{
                fontSize: "11px",
                color: "var(--qgi-text-muted)",
                marginTop: "3px",
                lineHeight: 1.35,
              }}
            >
              {h.caption}
            </div>
          </div>
        </div>

        {/* Row 3: metric + source nav cue */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginTop: "auto",
            paddingTop: "6px",
            borderTop: "1px solid rgba(255,255,255,0.04)",
          }}
        >
          <span
            style={{
              fontFamily: "ui-monospace, monospace",
              fontWeight: 600,
              fontSize: "18px",
              color,
              letterSpacing: "-0.3px",
            }}
          >
            {h.metric}
          </span>
          <span
            style={{
              fontSize: "10.5px",
              color: "var(--qgi-text-muted)",
              letterSpacing: "0.5px",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            open {h.source_label} {"→"}
          </span>
        </div>
      </article>
    </Link>
  );
}

function FallbackIcon({ size = 22 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
    >
      <circle cx="12" cy="12" r="9" />
    </svg>
  );
}
