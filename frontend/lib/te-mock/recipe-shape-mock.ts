/**
 * recipe-shape-mock — per-indicator canonical-shape data feeding
 * PatternAlignmentPanel.
 *
 * V4.1 wire-up (2026-05-29):
 *   - TE sample-10 recipes source from real card.trajectory_alignment data.
 *   - card.trajectory_alignment is optional — if missing, returns [] so the UI
 *     renders the "shape data not yet computed for this vintage" gate.
 *   - foreign_intervention, civil_war_and_insurgency, constitutional_change
 *     keep their hand-authored shape data (cascade-era; no real card).
 */
import type { AlignmentShape } from "@/components/precedents-v4-1/PatternAlignmentPanel";
import { loadAllCards } from "@/lib/te-data-contract/load";

// ─── Synthetic shape generator (used for hand-authored data only) ─────────────

function shape(
  windowYears: number,
  direction: 1 | -1,
  baseline: number,
  curvature: number,
  spread: number,
  seed: number
): AlignmentShape {
  const mean: number[] = [];
  const p25: number[] = [];
  const p75: number[] = [];
  for (let i = 0; i < windowYears; i++) {
    const t = i / Math.max(1, windowYears - 1);
    const m =
      baseline +
      direction * curvature * (0.4 * t + 0.6 * Math.pow(t, 1.6)) +
      0.08 * Math.sin(t * Math.PI * 2 * (1 + (seed % 3) * 0.4) + seed);
    const s = spread * (0.7 + 0.45 * t);
    mean.push(Number(m.toFixed(3)));
    p25.push(Number((m - s).toFixed(3)));
    p75.push(Number((m + s).toFixed(3)));
  }
  return { indicatorCode: "__UNSET__", mean, p25, p75 };
}

// ─── Hand-authored shapes for cascade-era / demo recipes ─────────────────────

const FOREIGN_INTERVENTION_WINDOW = 18;
const foreignInterventionShapes: AlignmentShape[] = [
  {
    ...shape(FOREIGN_INTERVENTION_WINDOW, -1, 0.35, 1.7, 0.45, 1),
    indicatorCode: "RQ.EST",
  },
  {
    ...shape(FOREIGN_INTERVENTION_WINDOW, -1, 0.1, 1.3, 0.55, 2),
    indicatorCode: "v2pepwrgen",
  },
  {
    ...shape(FOREIGN_INTERVENTION_WINDOW, -1, 0.5, 1.9, 0.4, 3),
    indicatorCode: "v2stfisccap",
  },
  {
    ...shape(FOREIGN_INTERVENTION_WINDOW, -1, -0.15, 1.5, 0.5, 4),
    indicatorCode: "v2elintmon",
  },
];

const CIVIL_WAR_WINDOW = 12;
const civilWarShapes: AlignmentShape[] = [
  { ...shape(CIVIL_WAR_WINDOW, -1, 0.25, 1.6, 0.42, 5), indicatorCode: "RQ.EST" },
  { ...shape(CIVIL_WAR_WINDOW, -1, 0.15, 1.4, 0.5, 6), indicatorCode: "v2x_polyarchy" },
  { ...shape(CIVIL_WAR_WINDOW, -1, 0.05, 1.8, 0.55, 7), indicatorCode: "v2psoppaut" },
];

const CONSTITUTIONAL_WINDOW = 6;
const constitutionalChangeShapes: AlignmentShape[] = [
  { ...shape(CONSTITUTIONAL_WINDOW, 1, -0.2, 1.4, 0.35, 8), indicatorCode: "v2lginvstp" },
  { ...shape(CONSTITUTIONAL_WINDOW, -1, 0.1, 1.2, 0.45, 9), indicatorCode: "v2juncind" },
  {
    ...shape(CONSTITUTIONAL_WINDOW, 1, -0.05, 1.0, 0.4, 10),
    indicatorCode: "v2x_polyarchy",
  },
  { ...shape(CONSTITUTIONAL_WINDOW, -1, 0.25, 1.3, 0.38, 11), indicatorCode: "RQ.EST" },
  { ...shape(CONSTITUTIONAL_WINDOW, 1, 0.0, 1.1, 0.42, 12), indicatorCode: "v2csprtcpt" },
];

const HAND_AUTHORED_SHAPES: Record<string, AlignmentShape[]> = {
  foreign_intervention: foreignInterventionShapes,
  civil_war_and_insurgency: civilWarShapes,
  constitutional_change: constitutionalChangeShapes,
};

// ─── TE card-derived shapes ────────────────────────────────────────────────────

/**
 * Build AlignmentShape[] from a card's trajectory_alignment field.
 * Returns [] if trajectory_alignment is absent (optional in v3 contract).
 */
function buildFromCard(recipeId: string): AlignmentShape[] {
  try {
    const allCards = loadAllCards();
    const card = allCards[recipeId];
    if (!card || !card.trajectory_alignment) return [];

    return card.trajectory_alignment.indicators.map((ind) => ({
      indicatorCode: ind.code,
      mean: ind.shape.mean,
      p25: ind.shape.p25,
      p75: ind.shape.p75,
    }));
  } catch {
    return [];
  }
}

// Cache to avoid re-loading on every call
const _shapeCache = new Map<string, AlignmentShape[]>();

/**
 * Get shape data for a recipe.
 *
 * Lookup order:
 *   1. Hand-authored (foreign_intervention, civil_war_and_insurgency, constitutional_change)
 *   2. Real card.trajectory_alignment data (TE sample-10 recipes)
 *   3. [] — component renders "shape data not yet computed for this vintage"
 */
export function getShapeData(recipeId: string): AlignmentShape[] {
  if (HAND_AUTHORED_SHAPES[recipeId]) return HAND_AUTHORED_SHAPES[recipeId];

  if (_shapeCache.has(recipeId)) return _shapeCache.get(recipeId)!;

  const shapes = buildFromCard(recipeId);
  _shapeCache.set(recipeId, shapes);
  return shapes;
}
