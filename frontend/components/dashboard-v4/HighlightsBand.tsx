import Link from "next/link";
import type { Route } from "next";
import { createElement } from "react";
import type { LucideIcon } from "lucide-react";
import { iconForRecipe } from "@/lib/te-mock/icons";
import { getRecipe } from "@/lib/te-mock/recipes";
import { familyColor } from "@/lib/te-mock/l1-families";

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
  vintage,
}: {
  highlights: Highlight[];
  vintage: string;
}) {
  return (
    <section style={{ marginBottom: "32px" }}>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "12px",
          marginBottom: "12px",
        }}
      >
        <span
          style={{
            fontSize: "10px",
            letterSpacing: "1.5px",
            fontFamily: "ui-monospace, monospace",
            color: "var(--qgi-text-dim)",
          }}
        >
          §01
        </span>
        <h2
          style={{
            fontSize: "16px",
            fontWeight: 600,
            margin: 0,
            color: "var(--qgi-text)",
            flex: 1,
          }}
        >
          Today&apos;s highlights
        </h2>
        <span
          style={{
            fontSize: "10px",
            color: "var(--qgi-text-muted)",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.3px",
          }}
        >
          one tile per surface · release {vintage}
        </span>
      </div>
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
    </section>
  );
}

function HighlightTile({ h }: { h: Highlight }) {
  const recipe = h.recipe_id ? getRecipe(h.recipe_id) : undefined;
  // Render via createElement to avoid the `react-hooks/static-components`
  // rule that fires on `const Icon = ...; <Icon/>` JSX patterns.
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
            open {h.source_label} →
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
