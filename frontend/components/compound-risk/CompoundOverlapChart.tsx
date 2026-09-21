import type { CompoundCountry } from "@/lib/te-mock/compound-risk-data";
import { RecipeIcon } from "@/components/te-v4-shared/RecipeIcon";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import { familyColor, familyLabel } from "@/lib/te-mock/l1-families";

interface Props {
  countries: CompoundCountry[];
}

export function CompoundOverlapChart({ countries }: Props) {
  if (countries.length === 0) return null;

  const topCompoundScore = Math.max(...countries.map((c) => c.compound_score), 1);

  return (
    <section data-tour="overlap-chart" style={{ marginTop: "48px" }}>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "12px",
          marginBottom: "14px",
          borderTop: "1px solid var(--qgi-border)",
          paddingTop: "24px",
        }}
      >
        <h2
          style={{
            fontSize: "18px",
            fontWeight: 600,
            margin: 0,
            color: "var(--qgi-text)",
            flex: 1,
          }}
        >
          Where the families stack: top {countries.length}
        </h2>
      </div>
      <p
        style={{
          fontSize: "12px",
          color: "var(--qgi-text-muted)",
          marginBottom: "20px",
          maxWidth: "780px",
          lineHeight: 1.5,
        }}
      >
        Each bar is the country&apos;s compound shape, segmented by threat family. Wider
        segments mean a larger contribution to the compound score. Read horizontally to
        see <em>which families pile up on which country</em>.
      </p>

      <div
        style={{
          background: "var(--qgi-surface)",
          border: "1px solid var(--qgi-border)",
          borderRadius: "8px",
          padding: "20px",
          display: "flex",
          flexDirection: "column",
          gap: "14px",
        }}
      >
        {countries.map((c) => {
          const total = c.lit_recipes.reduce((s, r) => s + r.score, 0);
          return (
            <div
              key={c.iso}
              style={{
                display: "grid",
                gridTemplateColumns: "180px 1fr 70px",
                gap: "14px",
                alignItems: "center",
              }}
            >
              <div
                style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: 0 }}
              >
                <FlagImg emoji={flagFor(c.country)} name={c.country} width={20} />
                <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                  <span
                    style={{
                      fontSize: "13px",
                      fontWeight: 600,
                      color: "var(--qgi-text)",
                    }}
                  >
                    {c.country}
                  </span>
                  <span
                    style={{
                      fontSize: "10px",
                      color: "var(--qgi-text-dim)",
                      fontFamily: "ui-monospace, monospace",
                      letterSpacing: "0.4px",
                    }}
                  >
                    {c.iso}
                  </span>
                </div>
              </div>
              <div
                style={{
                  height: "26px",
                  display: "flex",
                  borderRadius: "4px",
                  overflow: "hidden",
                  border: "1px solid var(--qgi-border)",
                  background: "var(--qgi-bg)",
                  width: `${(c.compound_score / topCompoundScore) * 100}%`,
                  transition: "width 0.2s",
                }}
              >
                {c.lit_recipes.map((r, idx) => {
                  const pct = (r.score / total) * 100;
                  const segColor = familyColor(r.l1_id, r.l1_color);
                  return (
                    <div
                      key={r.recipe_id}
                      title={`${r.label}: ${r.score.toFixed(1)}, family ${r.l1_id}`}
                      style={{
                        width: `${pct}%`,
                        background: `${segColor}66`,
                        borderRight:
                          idx < c.lit_recipes.length - 1
                            ? `1px solid ${segColor}`
                            : "none",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        color: segColor,
                        minWidth: "22px",
                      }}
                    >
                      <RecipeIcon recipeId={r.recipe_id} size={14} strokeWidth={1.8} />
                    </div>
                  );
                })}
              </div>
              <div
                style={{
                  fontSize: "14px",
                  fontWeight: 600,
                  color: "var(--qgi-amber)",
                  fontFamily: "ui-monospace, monospace",
                  textAlign: "right",
                }}
              >
                {c.compound_score.toFixed(1)}
              </div>
            </div>
          );
        })}
      </div>

      {/* Family legend */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", marginTop: "14px" }}>
        {Array.from(
          new Map(
            countries.flatMap((c) =>
              c.lit_recipes.map((r) => [
                r.l1_id,
                {
                  id: r.l1_id,
                  label: familyLabel(r.l1_id, r.l1_label),
                  color: r.l1_color,
                },
              ])
            )
          ).values()
        )
          .sort((a, b) => a.id.localeCompare(b.id))
          .map((f) => {
            const legendColor = familyColor(f.id, f.color);
            return (
              <span
                key={f.id}
                style={{
                  fontSize: "10.5px",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  color: "var(--qgi-text-muted)",
                  fontFamily: "ui-monospace, monospace",
                  letterSpacing: "0.3px",
                }}
              >
                <span
                  style={{
                    width: "10px",
                    height: "10px",
                    background: legendColor,
                    borderRadius: "2px",
                    display: "inline-block",
                  }}
                />
                {f.label}
              </span>
            );
          })}
      </div>
    </section>
  );
}
