/**
 * SensitivityPanel (P5) — per-indicator sensitivity analysis.
 *
 * "What would move this country's score?" — a marginal analysis panel
 * showing which indicators have the most leverage on the score, and how
 * much headroom (distance from threshold) each carries.
 *
 * Data: sensitivity_per_indicator[] baked by score_countries.py (round-2).
 * Each entry: marginal_points_per_unit (leverage), headroom (room to move
 * before the score would change materially), headroom_points (absolute
 * point impact of closing the headroom).
 *
 * Methodology constraint: this is prospective sensitivity, NOT a forecast.
 * Caption and tooltip say so explicitly (Kwame non-negotiable).
 */
import { PanelShell } from "./PanelShell";
import { NEUTRAL_SLATE } from "@/lib/te-mock/l1-families";
import type { SensitivityItem } from "@/lib/te-mock/countries-v4-data";

const SENSITIVITY_TOOLTIP =
  "Marginal analysis: how much the score would shift if each indicator moved " +
  "one unit toward the threshold. This is a model-sensitivity calculation, " +
  "not a prediction of what will happen.";

export function SensitivityPanel({
  accent,
  countryName,
  sensitivity,
}: {
  accent?: string;
  countryName: string;
  sensitivity: SensitivityItem[];
}) {
  const color = accent ?? NEUTRAL_SLATE;

  // Sort by headroom_points desc (highest potential score impact first).
  const rows = [...sensitivity].sort((a, b) => b.headroom_points - a.headroom_points);

  // For the bar track: scale relative to the max marginal leverage.
  const maxMarginal = Math.max(
    1,
    ...rows.map((r) => Math.abs(r.marginal_points_per_unit))
  );

  return (
    <PanelShell
      title="Sensitivity: what would move the score"
      accent={color}
      tooltip={SENSITIVITY_TOOLTIP}
      fullWidth
      caption={`Which indicators have the most leverage on ${countryName}'s score, and how much room remains before each would materially shift it. Model sensitivity only, not a projection.`}
    >
      {rows.length === 0 ? (
        <p
          style={{
            fontSize: "12px",
            color: "var(--qgi-text-dim)",
            fontStyle: "italic",
            margin: 0,
          }}
        >
          Sensitivity analysis available once the country is scored on at least one trend.
        </p>
      ) : (
        <ul
          style={{
            listStyle: "none",
            padding: 0,
            margin: 0,
            display: "flex",
            flexDirection: "column",
            gap: "10px",
          }}
        >
          {rows.map((r) => {
            const barPct = (Math.abs(r.marginal_points_per_unit) / maxMarginal) * 100;
            // Headroom label: how many points would close if this indicator
            // moved to its threshold. Positive = score would increase.
            const headroomSign = r.headroom_points >= 0 ? "+" : "";
            return (
              <li key={r.indicator_code}>
                {/* Row 1: indicator name + metrics */}
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "baseline",
                    gap: "10px",
                    marginBottom: "3px",
                  }}
                >
                  <span
                    style={{
                      fontSize: "12.5px",
                      color: "var(--qgi-text)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                    title={`${r.indicator_name} (${r.indicator_code}) · headroom: ${r.headroom.toFixed(2)} · potential impact: ${headroomSign}${r.headroom_points.toFixed(1)} pts`}
                  >
                    {r.indicator_name}
                  </span>
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "8px",
                      fontFamily: "ui-monospace, monospace",
                      fontSize: "11px",
                      color: "var(--qgi-text-muted)",
                      flexShrink: 0,
                    }}
                  >
                    {/* Marginal leverage */}
                    <span
                      title="Marginal leverage: score points per unit shift"
                      style={{ color }}
                    >
                      {r.marginal_points_per_unit.toFixed(2)} pts/u
                    </span>
                    {/* Headroom impact */}
                    <span
                      title="Potential score impact if headroom is closed"
                      style={{
                        color:
                          r.headroom_points > 0
                            ? "#E68F29"
                            : r.headroom_points < 0
                              ? "#3FBF8F"
                              : "var(--qgi-text-dim)",
                      }}
                    >
                      {headroomSign}
                      {r.headroom_points.toFixed(1)}
                    </span>
                  </span>
                </div>

                {/* Bar track: marginal leverage width */}
                <div
                  style={{
                    height: "6px",
                    borderRadius: "2px",
                    background: "var(--qgi-bg)",
                    border: "1px solid var(--qgi-border)",
                    overflow: "hidden",
                  }}
                  aria-hidden
                >
                  <div
                    style={{
                      width: `${barPct.toFixed(1)}%`,
                      height: "100%",
                      background: color,
                      opacity: 0.7,
                    }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </PanelShell>
  );
}
