/**
 * PageLayout — V4.1 page-level frame.
 *
 * Header strip: recipe icon + status chip + H1 + recipe-id subtitle +
 * definition lede paragraph (per #155 — Definition is anchoring context,
 * not a panel-tile equal to charts) + optional demo disclosure. Below:
 * dashboard-style panel grid (CSS Grid auto-fit minmax(340px, 1fr)).
 *
 * 2026-05-27 polish (#164 — Sofia): grid now uses `grid-auto-flow: row dense`
 * + `grid-auto-rows: minmax(0, auto)`, and exports a `<TallSlot>` wrapper
 * the page uses to mark naturally-tall panels (Countries, ScoreDistribution,
 * IndicatorSet, PatternAlignment) with `grid-row: span 2`. The dense flow
 * + variable row spans removes the empty-band gaps that the old
 * row-aligned `auto-fit` grid forced under short panels.
 */
import Link from "next/link";
import type { Route } from "next";
import type { ReactNode } from "react";
import { RecipeIcon } from "@/components/te-v4-shared/RecipeIcon";

// 2026-05-28: TallSlot removed. It wrapped chart panels in a span-2 grid
// item, which STOLE grid-item status from the ExpandableShell inside it —
// so ExpandableShell's `gridColumn: 1 / -1` expand silently no-op'd on every
// panel except the one not wrapped in TallSlot. Panels are now direct grid
// items (content-sized rows), so expand works everywhere.

interface RecipeSummary {
  recipe_id: string;
  label: string;
  l1_id: string;
  l1_label: string;
  l1_color: string;
  l2_label: string;
}

interface Props {
  recipe: RecipeSummary;
  statusChip?: ReactNode;
  subtitle?: string;
  /**
   * Definition lede paragraph (#155). Rendered under the H1 + subtitle as
   * a 15px line, max-width 720px, primary text color.
   */
  definition?: string;
  demoDisclosure?: ReactNode;
  /** Slot rendered on the right side of the breadcrumb strip (e.g. HowToReadButton). */
  headerRightSlot?: ReactNode;
  children: ReactNode;
}

export function PageLayout({
  recipe,
  statusChip,
  subtitle,
  definition,
  demoDisclosure,
  headerRightSlot,
  children,
}: Props) {
  return (
    <div
      style={{ minHeight: "100%", background: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      {/* Header strip */}
      <div
        style={{
          borderBottom: "1px solid var(--qgi-border)",
          background: "var(--qgi-surface)",
        }}
      >
        <div style={{ maxWidth: "1280px", margin: "0 auto", padding: "20px 24px 24px" }}>
          {/* Breadcrumb + mockup banner */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "16px",
              gap: "16px",
              flexWrap: "wrap",
            }}
          >
            <nav
              aria-label="Breadcrumb"
              style={{
                fontSize: "11px",
                letterSpacing: "0.3px",
                color: "var(--qgi-text-dim)",
                fontFamily: "ui-monospace, monospace",
              }}
            >
              <Link
                href={"/trends" as Route}
                style={{ color: "var(--qgi-text-muted)", textDecoration: "none" }}
              >
                ← Trends
              </Link>
              <span style={{ margin: "0 8px", opacity: 0.5 }}>/</span>
              {/* V4.1 §1.2: family rendered as label only — no letter glyph. */}
              <span style={{ color: recipe.l1_color }}>{recipe.l1_label}</span>
              <span style={{ margin: "0 8px", opacity: 0.5 }}>/</span>
              <span>{recipe.l2_label}</span>
            </nav>
            {/* 2026-05-27 (#159): MOCKUP · V4.1 chip removed — internal versioning */}
            {headerRightSlot}
          </div>

          <div style={{ display: "flex", gap: "20px", alignItems: "flex-start" }}>
            <div
              style={{
                width: "88px",
                height: "88px",
                background: "var(--qgi-bg)",
                border: `1px solid ${recipe.l1_color}`,
                borderRadius: "10px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: recipe.l1_color,
                flexShrink: 0,
              }}
            >
              <RecipeIcon recipeId={recipe.recipe_id} size={52} strokeWidth={1.5} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              {/* 2026-05-30: status chip ("In play" etc.) removed from the
                  recipe header per founder ask — every recipe rendered here
                  is in active rotation by construction, so the chip carried
                  zero signal. The slot is still wired (statusChip is now
                  optional) so future chip styles can drop back in here
                  without re-plumbing PageLayout. */}
              {statusChip && (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "10px",
                    marginBottom: "10px",
                    flexWrap: "wrap",
                  }}
                >
                  {statusChip}
                </div>
              )}
              <h1
                style={{
                  fontSize: "30px",
                  fontWeight: 600,
                  lineHeight: 1.15,
                  margin: "0 0 8px",
                  color: "var(--qgi-text)",
                }}
              >
                {recipe.label}
              </h1>
              {subtitle && (
                <p
                  style={{
                    color: "var(--qgi-text-muted)",
                    fontSize: "13px",
                    margin: 0,
                    lineHeight: 1.5,
                  }}
                >
                  {/* 2026-05-27 (#159): Recipe ID slug exposure removed */}
                  {subtitle}
                </p>
              )}
              {definition && (
                <p
                  data-tour="definition-lede"
                  style={{
                    marginTop: "16px",
                    marginBottom: 0,
                    maxWidth: "720px",
                    fontSize: "15px",
                    lineHeight: 1.65,
                    color: "var(--qgi-text)",
                  }}
                >
                  {definition}
                </p>
              )}
              {demoDisclosure && (
                <div style={{ marginTop: "16px" }}>{demoDisclosure}</div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Panel grid — content-sized rows, top-aligned. Each panel renders at
          its natural height (no fixed-row stretch → no internal empty space,
          and a full-width child like the cross-link footer stays slim instead
          of being forced to a tall track). ExpandableShell panels are direct
          grid items so their `gridColumn: 1 / -1` expand works; the full-width
          item claims a fresh row without overlapping its neighbor. */}
      <div style={{ maxWidth: "1280px", margin: "0 auto", padding: "24px 24px 64px" }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(min(340px, 100%), 1fr))",
            gridAutoRows: "auto",
            gap: "16px",
            // stretch so same-row panels equalize height — clean aligned edges
            // (panel borders contain any internal slack), no ragged inter-row
            // gaps. Expanded ExpandableShell items take gridColumn 1 / -1 and
            // claim their own row, so stretch never distorts them.
            alignItems: "stretch",
          }}
        >
          {children}
        </div>
      </div>
    </div>
  );
}
