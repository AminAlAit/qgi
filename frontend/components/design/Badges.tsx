/**
 * Reusable badge components (#126) — TierBadge, ConvergenceBadge, SectorBadge,
 * PpsValue. All consume `lib/design.ts` tokens so every view renders the same
 * V1.5.3 fields the same way.
 */
import type { PatternTier, ConvergenceTier } from "@/lib/dashboard-cache";
import {
  tierColor,
  TIER_LABELS,
  convergenceColor,
  CONVERGENCE_LABELS,
  CONVERGENCE_DOTS,
  sectorColor,
  sectorChipBg,
  ppsColor,
} from "@/lib/design";

// ---------------------------------------------------------------------------
// TierBadge (#128 pattern_tier)
// ---------------------------------------------------------------------------

export function TierBadge({
  tier,
  size = "sm",
}: {
  tier: PatternTier | null | undefined;
  size?: "xs" | "sm" | "md";
}) {
  if (!tier) return null;
  const color = tierColor(tier);
  const fontSize = size === "xs" ? 9 : size === "sm" ? 10 : 11;
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
      title={TIER_LABELS[tier]}
    >
      {tier}
    </span>
  );
}

// ---------------------------------------------------------------------------
// ConvergenceBadge (#133 convergence_tier)
// ---------------------------------------------------------------------------

/**
 * Visual: N filled dots (1-4) on a colored background, labelled with the
 * tier name on hover. Matches the #133 spec: "dot circles for convergence
 * tier (visual badge)".
 */
export function ConvergenceBadge({
  tier,
  nPredictors,
  nRegions,
  compact = false,
}: {
  tier: ConvergenceTier | null | undefined;
  nPredictors?: number | null;
  nRegions?: number | null;
  compact?: boolean;
}) {
  if (!tier) return null;
  const color = convergenceColor(tier);
  const dots = CONVERGENCE_DOTS[tier];

  const dotElements = Array.from({ length: 4 }, (_, i) => (
    <span
      key={i}
      className="inline-block rounded-full"
      style={{
        width: 5,
        height: 5,
        backgroundColor: i < dots ? color : "transparent",
        border: `1px solid ${color}`,
      }}
    />
  ));

  const tooltip =
    nPredictors && nRegions
      ? `${CONVERGENCE_LABELS[tier]}: ${nPredictors} predictor${nPredictors === 1 ? "" : "s"} across ${nRegions} region${nRegions === 1 ? "" : "s"}`
      : CONVERGENCE_LABELS[tier];

  return (
    <span
      className="inline-flex items-center gap-1"
      style={{ fontSize: 9 }}
      title={tooltip}
    >
      <span className="inline-flex items-center gap-[2px]">{dotElements}</span>
      {!compact && (
        <span className="font-data tracking-wider uppercase" style={{ color }}>
          {CONVERGENCE_LABELS[tier].toUpperCase()}
        </span>
      )}
    </span>
  );
}

// ---------------------------------------------------------------------------
// SectorBadge — small inline sector chip
// ---------------------------------------------------------------------------

export function SectorBadge({
  sector,
  size = "sm",
}: {
  sector: string | null | undefined;
  size?: "xs" | "sm";
}) {
  if (!sector) return null;
  const color = sectorColor(sector);
  const bg = sectorChipBg(sector);
  return (
    <span
      className="inline-flex items-center rounded font-data uppercase tracking-wider"
      style={{
        color,
        backgroundColor: bg,
        padding: size === "xs" ? "1px 5px" : "2px 6px",
        fontSize: size === "xs" ? 9 : 10,
      }}
    >
      {sector}
    </span>
  );
}

// ---------------------------------------------------------------------------
// PpsValue — colored 0-100 score display ("Pattern Strength: 73/100")
// ---------------------------------------------------------------------------

export function PpsValue({
  pps,
  showSuffix = true,
  size = "md",
}: {
  pps: number | null | undefined;
  showSuffix?: boolean;
  size?: "sm" | "md" | "lg";
}) {
  if (pps == null || !Number.isFinite(pps)) {
    return (
      <span className="font-data" style={{ color: "var(--qgi-text-dim)" }}>
        —
      </span>
    );
  }
  const color = ppsColor(pps);
  const fontSize = size === "sm" ? 11 : size === "md" ? 14 : 18;
  return (
    <span className="font-data font-semibold" style={{ color, fontSize }}>
      {pps.toFixed(1)}
      {showSuffix && (
        <span
          className="font-normal"
          style={{
            color: "var(--qgi-text-dim)",
            marginLeft: 2,
            fontSize: fontSize * 0.75,
          }}
        >
          /100
        </span>
      )}
    </span>
  );
}
