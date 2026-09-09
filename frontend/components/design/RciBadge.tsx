/**
 * RciBadge (#481) — renders the per-recipe Recipe Confidence tier as an
 * inline chip. Sits next to the recipe label on `/precedents/{slug}` and
 * `/signals/{country}/{slug}` so users can discount low-confidence
 * scores at a glance.
 *
 * Visual language matches `Badges.tsx` (TierBadge, ConvergenceBadge):
 * tracking-wider, font-data, hex-with-alpha-suffix backgrounds.
 *
 * Per founder direction (#482): the badge label is generic
 * ("High confidence" / "Moderate confidence" / etc.) — never references
 * "RCI" or the formula. The tooltip exposes diagnostic numbers (AUC,
 * sample size, missingness flags) but NOT the formula or RCI value, so
 * the public methodology page can frame the same concept in plain terms
 * without revealing the internal weighting.
 *
 * Pure presentational — no "use client" directive — composable into both
 * Server and Client component trees.
 */
import type { RciTier, RecipeConfidenceEntry } from "@/lib/recipe-confidence";
import { TIER_LABEL } from "@/lib/recipe-confidence";

const TIER_COLORS: Record<RciTier, string> = {
  GREEN: "#34d399", // emerald-400 — matches Trade sector tone
  YELLOW: "#fbbf24", // amber-400 — matches Demographic
  RED: "#f87171", // red-400 — matches Military
  INSUFFICIENT: "#7a90a8", // slate-muted — matches the `Other` sector
};

export function RciBadge({
  entry,
  size = "sm",
}: {
  entry: RecipeConfidenceEntry | null | undefined;
  size?: "xs" | "sm" | "md";
}) {
  if (!entry) return null;
  const color = TIER_COLORS[entry.tier];
  const fontSize = size === "xs" ? 9 : size === "sm" ? 10 : 11;
  const label = TIER_LABEL[entry.tier];

  // Tooltip composition — diagnostic context only. Per #482 direction:
  // do NOT include the RCI numeric value or the formula here. Stick to
  // surface-level facts (AUC, n, MNAR count) that any methodology
  // statement on the public page can stand behind.
  const tooltipParts: string[] = [label];
  if (entry.test_auc != null) {
    const ci =
      entry.auc_ci_low != null && entry.auc_ci_high != null
        ? ` (95% CI ${entry.auc_ci_low.toFixed(2)}–${entry.auc_ci_high.toFixed(2)})`
        : "";
    tooltipParts.push(`Holdout AUC ${entry.test_auc.toFixed(2)}${ci}`);
  }
  if (entry.n_total > 0) {
    tooltipParts.push(
      `${entry.n_total.toLocaleString("en-US")} samples (${entry.n_pos} positive)`
    );
  }
  if (entry.n_mnar_flagged > 0) {
    tooltipParts.push(
      `${entry.n_mnar_flagged} indicator${entry.n_mnar_flagged === 1 ? "" : "s"} flagged for missingness bias`
    );
  }
  const tooltip = tooltipParts.join(" · ");

  return (
    <span
      className="inline-flex items-center rounded font-data font-semibold tracking-wider"
      style={{
        color,
        backgroundColor: `${color}18`,
        padding: size === "xs" ? "1px 5px" : "2px 6px",
        fontSize,
        border: `1px solid ${color}40`,
      }}
      title={tooltip}
    >
      {label}
    </span>
  );
}
