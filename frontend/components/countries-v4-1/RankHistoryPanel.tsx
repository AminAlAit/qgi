/**
 * RankHistoryPanel (P4) — where the country has sat in the score
 * distribution over the last 12 quarters, for its most-lit recipes.
 * Full-width, neutral/structural accent.
 *
 * Round-2 (2026-05-30): momentum_scores_by_year (4 years, 2023-2026) is now
 * live from the bake. We render a 4-point score trajectory per recipe when
 * year_scores is populated, with a momentum_label annotation (rising/falling/
 * flat/suppressed). rank_history (12-quarter cross-vintage rollup) stays empty
 * at vintage-1; it will populate once vintage-2 lands.
 *
 * Retrospective only (Kwame): the caption says so, and every sparkline ends
 * at the latest reading with no forward extrapolation (MiniSparkline
 * enforces the terminating end dot).
 */
import type { CSSProperties } from "react";
import { PanelShell } from "./PanelShell";
import { MiniSparkline } from "./MiniSparkline";
import { RecipeIcon } from "@/components/te-v4-shared/RecipeIcon";
import { familyColor, NEUTRAL_SLATE } from "@/lib/te-mock/l1-families";
import type { CountryV4 } from "@/lib/te-mock/countries-v4-data";

/** Colour for the momentum_label badge (rising/falling/flat/suppressed). */
function labelStyle(label: string | null): CSSProperties {
  switch (label) {
    case "rising":
      return { color: "#E68F29", borderColor: "#E68F2966" };
    case "falling":
      return { color: "#3FBF8F", borderColor: "#3FBF8F66" };
    case "suppressed":
      return { color: "#A0AEC0", borderColor: "#A0AEC066" };
    default: // flat or null
      return { color: "var(--qgi-text-dim)", borderColor: "var(--qgi-border)" };
  }
}

export function RankHistoryPanel({ country }: { country: CountryV4 }) {
  // recipe_id → l1_id, so we can apply the family display palette (the
  // momentum records only carry the raw tracker color, not the family id).
  const l1ById = new Map(country.top_recipes.map((r) => [r.recipe_id, r.l1_id]));

  // Round-2: prefer year_scores (4-year bake data) over rank_history (12-quarter
  // cross-vintage rollup which is empty at vintage-1).
  const hasYearScores = country.momentum.some(
    (m) => m.year_scores && Object.keys(m.year_scores).length >= 2
  );
  const hasHistory =
    hasYearScores || country.momentum.some((m) => m.rank_history.length > 0);

  return (
    <PanelShell
      title="Score trajectory (multi-year)"
      accent={NEUTRAL_SLATE}
      fullWidth
      dataTour="rank-history-panel"
      caption={`How ${country.name}'s risk scores have moved across years for its most-lit trends. Past movement only, not a projection.`}
    >
      {!hasHistory ? (
        <p
          style={{
            fontSize: "12px",
            color: "var(--qgi-text-dim)",
            fontStyle: "italic",
            margin: 0,
          }}
        >
          Score trajectory will appear once the country is scored on at least two years.
          This is the first bake for these trends.
        </p>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))",
            gap: "16px",
          }}
        >
          {country.momentum.map((m) => {
            const color = familyColor(l1ById.get(m.recipe_id) ?? "", m.l1_color);

            // Round-2: use year_scores when available; fall back to rank_history.
            const useYearScores = m.year_scores && Object.keys(m.year_scores).length >= 2;
            let sparkValues: number[];
            let yearLabels: string[] | null = null;
            let latestScore: number;

            if (useYearScores) {
              // Sort years ascending (2023→2026) and extract ordered values.
              const sortedYears = Object.keys(m.year_scores).sort();
              sparkValues = sortedYears.map((y) => m.year_scores[y]);
              yearLabels = sortedYears;
              latestScore = sparkValues[sparkValues.length - 1];
            } else {
              sparkValues = m.rank_history;
              latestScore = m.rank_history[m.rank_history.length - 1] ?? 0;
            }

            const lblStyle = labelStyle(m.momentum_label);

            return (
              <div
                key={m.recipe_id}
                style={{
                  border: "1px solid var(--qgi-border)",
                  background: "var(--qgi-bg)",
                  borderRadius: "6px",
                  padding: "12px",
                }}
              >
                {/* Header row: icon · label · current score */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    marginBottom: "8px",
                  }}
                >
                  <span
                    title={`${m.label} (${l1ById.get(m.recipe_id) ?? "?"} family)`}
                    aria-label={`${m.label} trend icon`}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      width: "22px",
                      height: "22px",
                      border: `1px solid ${color}99`,
                      borderRadius: "3px",
                      color,
                      background: `${color}14`,
                      flexShrink: 0,
                    }}
                  >
                    <RecipeIcon recipeId={m.recipe_id} size={14} strokeWidth={1.8} />
                  </span>
                  <span
                    style={{
                      fontSize: "12px",
                      color: "var(--qgi-text)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      flex: 1,
                    }}
                    title={m.label}
                  >
                    {m.label}
                  </span>
                  <span
                    style={{
                      fontFamily: "ui-monospace, monospace",
                      fontSize: "13px",
                      fontWeight: 700,
                      color: "var(--qgi-text)",
                    }}
                  >
                    {latestScore.toFixed(0)}
                  </span>
                </div>

                {/* Sparkline */}
                <MiniSparkline
                  values={sparkValues}
                  color={color}
                  width={206}
                  height={36}
                />

                {/* Year axis labels for year_scores mode */}
                {yearLabels && yearLabels.length >= 2 && (
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      marginTop: "3px",
                    }}
                  >
                    <span
                      style={{
                        fontSize: "9px",
                        fontFamily: "ui-monospace, monospace",
                        color: "var(--qgi-text-dim)",
                      }}
                    >
                      {yearLabels[0]}
                    </span>
                    <span
                      style={{
                        fontSize: "9px",
                        fontFamily: "ui-monospace, monospace",
                        color: "var(--qgi-text-dim)",
                      }}
                    >
                      {yearLabels[yearLabels.length - 1]}
                    </span>
                  </div>
                )}

                {/* Round-2: momentum_label badge */}
                {m.momentum_label && (
                  <div style={{ marginTop: "6px" }}>
                    <span
                      style={{
                        display: "inline-block",
                        fontSize: "9.5px",
                        fontFamily: "ui-monospace, monospace",
                        letterSpacing: "0.4px",
                        textTransform: "uppercase",
                        padding: "2px 5px",
                        borderRadius: "3px",
                        border: `1px solid ${lblStyle.borderColor}`,
                        color: lblStyle.color,
                      }}
                      title={`Momentum direction: ${m.momentum_label}`}
                    >
                      {m.momentum_label}
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </PanelShell>
  );
}
