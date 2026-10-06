/**
 * AnalogsRow — top-3 historical-analog cards for a country's detail page.
 *
 * Visually-compressed cousin of `components/nearest-analog/AnalogCard.tsx`
 * (Daniyar's). This in-page strip skips the full sparkline overlay so we
 * keep the country-hub readable — the user clicks through to the full
 * Nearest-Analog page for the overlays.
 *
 * Honesty: "what happened next" is HISTORICAL FACT about the analog
 * country, not a forecast about the current country. Weak matches
 * (< 70) are flagged.
 */
import Link from "next/link";
import type { Route } from "next";
import { iconForRecipe } from "@/lib/te-mock/icons";
import { getRecipe } from "@/lib/te-mock/recipes";
import type { CountryAnalog } from "@/lib/te-mock/countries-v4-data";
import { RecipeIcon } from "@/components/te-v4-shared/RecipeIcon";

export function AnalogsRow({
  analogs,
  subjectName,
}: {
  analogs: readonly CountryAnalog[];
  subjectName: string;
}) {
  if (analogs.length === 0) {
    return (
      <div
        style={{
          padding: "20px",
          border: "1px dashed var(--qgi-border)",
          borderRadius: "6px",
          textAlign: "center",
          fontSize: "13px",
          color: "var(--qgi-text-muted)",
          fontStyle: "italic",
        }}
      >
        No historical analogues above the match-quality floor for {subjectName} at this
        release.
      </div>
    );
  }

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
        gap: "12px",
      }}
    >
      {analogs.slice(0, 3).map((a, i) => (
        <AnalogCardCompact key={`${a.country}-${a.year}`} analog={a} rank={i + 1} />
      ))}
    </div>
  );
}

function AnalogCardCompact({ analog, rank }: { analog: CountryAnalog; rank: number }) {
  const recipe = getRecipe(analog.primary_recipe_id);
  const l1Color = recipe?.l1_color ?? "#9ab0c4";
  const recipeLabel = recipe?.label ?? analog.primary_recipe_id;

  const zone =
    analog.match_score >= 85 ? "STRONG" : analog.match_score >= 70 ? "MODERATE" : "WEAK";
  const zoneColor =
    zone === "STRONG" ? "#3FBF8F" : zone === "MODERATE" ? "#E6C45E" : "#E68F29";

  return (
    <article
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "8px",
        padding: "14px",
        display: "flex",
        flexDirection: "column",
        gap: "10px",
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Rank ribbon */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: "24px",
          height: "24px",
          background: l1Color,
          color: "var(--qgi-bg)",
          fontFamily: "ui-monospace, monospace",
          fontSize: "11px",
          fontWeight: 700,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          borderBottomRightRadius: "8px",
        }}
        aria-label={`Rank ${rank}`}
      >
        #{rank}
      </div>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          paddingLeft: "28px",
          gap: "8px",
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              fontSize: "15px",
              fontWeight: 600,
              color: "var(--qgi-text)",
              lineHeight: 1.2,
            }}
          >
            {analog.country}
          </div>
          <div
            style={{
              fontSize: "10.5px",
              color: "var(--qgi-text-muted)",
              fontFamily: "ui-monospace, monospace",
              letterSpacing: "0.4px",
              marginTop: "2px",
            }}
          >
            {analog.year} · pre-event
          </div>
        </div>
        <div style={{ textAlign: "right", flexShrink: 0 }}>
          <div
            style={{
              fontSize: "20px",
              fontWeight: 600,
              color: zoneColor,
              fontFamily: "ui-monospace, monospace",
              lineHeight: 1,
            }}
          >
            {analog.match_score.toFixed(1)}
          </div>
          <div
            style={{
              fontSize: "8.5px",
              letterSpacing: "1.2px",
              color: zoneColor,
              fontFamily: "ui-monospace, monospace",
              marginTop: "3px",
              fontWeight: 600,
            }}
          >
            {zone}
          </div>
        </div>
      </div>

      <Link
        href={`/trends/${analog.primary_recipe_id}` as Route}
        style={{
          textDecoration: "none",
          display: "flex",
          alignItems: "center",
          gap: "8px",
          padding: "6px 8px",
          background: "rgba(255,255,255,0.02)",
          border: `1px solid ${l1Color}`,
          borderRadius: "5px",
        }}
      >
        <div
          style={{
            color: l1Color,
            display: "flex",
            alignItems: "center",
          }}
        >
          <RecipeIcon recipeId={analog.primary_recipe_id} size={16} strokeWidth={1.7} />
        </div>
        <div
          style={{
            flex: 1,
            minWidth: 0,
            fontSize: "11px",
            fontWeight: 600,
            color: "var(--qgi-text)",
          }}
        >
          {recipeLabel}
        </div>
      </Link>

      {analog.weak_analog && (
        <div
          style={{
            padding: "6px 8px",
            background: "rgba(230,143,41,0.08)",
            border: "1px solid rgba(230,143,41,0.4)",
            borderRadius: "4px",
            fontSize: "10.5px",
            color: "#E68F29",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.2px",
          }}
        >
          ⚠ Weak analogue (below the 70 floor): interpret with caution.
        </div>
      )}

      <div>
        <div
          style={{
            fontSize: "8.5px",
            letterSpacing: "1.2px",
            color: l1Color,
            fontFamily: "ui-monospace, monospace",
            marginBottom: "4px",
            fontWeight: 600,
            textTransform: "uppercase",
          }}
        >
          What happened next · {analog.country} {analog.year}
        </div>
        <p
          style={{
            fontSize: "11.5px",
            color: "var(--qgi-text)",
            lineHeight: 1.5,
            margin: 0,
          }}
        >
          {analog.what_happened_next}
        </p>
      </div>
    </article>
  );
}
