/**
 * RecipeContributionBar — ranked horizontal bar list showing which recipes
 * contributed to the current country's analog match, weighted by SHAP-style
 * contribution percentage.
 *
 * This is the "which recipes matched" panel from the spec: for the current
 * country, which canonical trajectory shapes pulled it toward its analogs and
 * by how much. Maps to ledger Feature 5 (Aggregation rule) + Feature 14
 * (driver) at the recipe layer rather than the indicator layer.
 *
 * Status chip on every non-graduated recipe: a recipe that did not hold up
 * contributing 40% must not be confused with a validated 40% contribution.
 *
 * Server component.
 */
import type { RecipeContribution } from "@/lib/te-mock/nearest-analog-data";
import { statusLabel } from "@/lib/te-mock/country-families";
import { RecipeIcon } from "@/components/te-v4-shared/RecipeIcon";
import { getRecipe } from "@/lib/te-mock/recipes";
import { familyColor, NEUTRAL_SLATE } from "@/lib/te-mock/l1-families";

export interface RecipeContributionBarProps {
  contributions: RecipeContribution[];
}

function badgeFor(status: RecipeContribution["status"]): {
  label: string;
  color: string;
  bg: string;
} {
  const { label, tone } = statusLabel(status);
  const color =
    tone === "deployed" ? "#3FBF8F" : tone === "failed" ? "#E68F29" : "#7A8FA0";
  const bg =
    tone === "deployed"
      ? "rgba(63,191,143,0.12)"
      : tone === "failed"
        ? "rgba(230,143,41,0.12)"
        : "rgba(122,143,160,0.12)";
  return { label, color, bg };
}

export function RecipeContributionBar({ contributions }: RecipeContributionBarProps) {
  const sorted = [...contributions].sort(
    (a, b) => b.contribution_pct - a.contribution_pct
  );
  const max = sorted.length ? sorted[0].contribution_pct : 100;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
      {sorted.map((c) => {
        const badge = badgeFor(c.status);
        const widthPct = (c.contribution_pct / max) * 100;
        // P2-1: derive canonical color from recipe catalog, not hardcoded data field.
        // getRecipe() always resolves for any recipe in the contributions data,
        // so the inner fallback uses NEUTRAL_SLATE rather than c.l1_color (the
        // legacy data-field value is intentionally not authoritative; see #134).
        const recipe = getRecipe(c.recipe_id);
        const canonicalColor = familyColor(recipe?.l1_id ?? "", NEUTRAL_SLATE);
        return (
          <div
            key={c.recipe_id}
            style={{
              padding: "10px 12px",
              background: "var(--qgi-bg)",
              border: "1px solid var(--qgi-border)",
              borderRadius: "6px",
              position: "relative",
              overflow: "hidden",
            }}
          >
            {/* Background fill bar */}
            <div
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                bottom: 0,
                width: `${widthPct}%`,
                background: `linear-gradient(to right, ${canonicalColor}22, ${canonicalColor}05)`,
                borderRight: `1px solid ${canonicalColor}33`,
              }}
            />
            <div
              style={{
                position: "relative",
                display: "flex",
                alignItems: "center",
                gap: "10px",
              }}
            >
              <div
                style={{
                  width: "26px",
                  height: "26px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: canonicalColor,
                  flexShrink: 0,
                }}
              >
                <RecipeIcon recipeId={c.recipe_id} size={18} strokeWidth={1.6} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    flexWrap: "wrap",
                  }}
                >
                  <span
                    style={{
                      fontSize: "13px",
                      fontWeight: 600,
                      color: "var(--qgi-text)",
                    }}
                  >
                    {c.recipe_label}
                  </span>
                  {/* 2026-05-30 founder ask: status badge removed. Every
                      contribution row here is by construction a recipe
                      that's in active rotation — the chip carried zero
                      signal. The `badge` variable is intentionally left
                      computed above so the chip can drop back in here
                      if future statuses (e.g. retired) need surfacing. */}
                  <span style={{ display: "none" }}>{badge.label}</span>
                </div>
              </div>
              <div
                style={{
                  fontSize: "16px",
                  fontWeight: 600,
                  color: canonicalColor,
                  fontFamily: "ui-monospace, monospace",
                  flexShrink: 0,
                }}
              >
                {c.contribution_pct}%
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
