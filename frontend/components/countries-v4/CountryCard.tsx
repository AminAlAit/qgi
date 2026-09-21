/**
 * CountryCard — one country tile on /countries-v4.
 *
 * Visual idiom mirrors `components/trends/RecipeCard.tsx`:
 *   - top row: flag emoji + ISO chip
 *   - body: country name + region
 *   - "tier ribbon" replaced by a compound-score chip strip
 *   - bottom: top-lit recipe icon + L1 family color + vintage stamp
 *
 * Honesty: when recipes_lit_graduated < recipes_lit_count, the chip
 * makes the gap visible ("3 lit · 0 graduated").
 */
import Link from "next/link";
import type { Route } from "next";
import { RecipeIcon } from "@/components/te-v4-shared/RecipeIcon";
import type { CountryV4 } from "@/lib/te-mock/countries-v4-data";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";

export function CountryCard({ country }: { country: CountryV4 }) {
  const topRecipe = country.top_recipes[0];
  const isDark = country.recipes_lit_count === 0;

  return (
    <Link
      href={`/countries-v4/${country.iso.toLowerCase()}` as Route}
      style={{ textDecoration: "none", color: "inherit", display: "block" }}
    >
      <article
        style={{
          background: "var(--qgi-surface)",
          border: "1px solid var(--qgi-border)",
          borderRadius: "8px",
          padding: "14px",
          minHeight: "200px",
          display: "flex",
          flexDirection: "column",
          transition: "border-color 0.15s, transform 0.15s",
          cursor: "pointer",
          opacity: isDark ? 0.72 : 1,
        }}
      >
        {/* Top row — flag + ISO chip */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            marginBottom: "10px",
          }}
        >
          <FlagImg emoji={country.flag_emoji} name={country.name} width={30} radius={3} />
          <span
            style={{
              fontSize: "9.5px",
              padding: "2px 7px",
              border: "1px solid var(--qgi-border)",
              color: "var(--qgi-text-dim)",
              borderRadius: "3px",
              fontFamily: "ui-monospace, monospace",
              letterSpacing: "0.5px",
            }}
          >
            {country.iso}
          </span>
        </div>

        {/* Name + region */}
        <div style={{ flex: 1, marginBottom: "10px" }}>
          <div
            style={{
              fontSize: "16px",
              fontWeight: 600,
              lineHeight: 1.2,
              color: "var(--qgi-text)",
              marginBottom: "3px",
            }}
          >
            {country.name}
          </div>
          <div
            style={{
              fontSize: "11px",
              color: "var(--qgi-text-muted)",
              lineHeight: 1.3,
              fontFamily: "ui-monospace, monospace",
              letterSpacing: "0.3px",
            }}
          >
            {country.region}
          </div>
        </div>

        {/* Compound chip strip */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            marginBottom: "10px",
            flexWrap: "wrap",
          }}
        >
          <span
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: "20px",
              fontWeight: 600,
              color:
                country.compound_score > 100 ? "var(--qgi-amber)" : "var(--qgi-text)",
              lineHeight: 1,
            }}
          >
            {country.compound_score.toFixed(1)}
          </span>
          <span
            style={{
              fontSize: "9px",
              letterSpacing: "1px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            COMPOUND
          </span>
        </div>

        {/* L1 family chips for the country's lit families */}
        {country.lit_families.length > 0 && (
          <div
            style={{
              display: "flex",
              gap: "4px",
              flexWrap: "wrap",
              marginBottom: "10px",
            }}
          >
            {country.lit_families.slice(0, 5).map((fam) => (
              <span
                key={fam.l1_id}
                title={fam.l1_label}
                style={{
                  fontSize: "9px",
                  padding: "2px 6px",
                  border: `1px solid ${fam.l1_color}`,
                  color: fam.l1_color,
                  borderRadius: "3px",
                  fontFamily: "ui-monospace, monospace",
                  letterSpacing: "0.4px",
                }}
              >
                {fam.l1_id}
              </span>
            ))}
          </div>
        )}

        {/* Bottom — top recipe icon + lit count */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginTop: "auto",
            paddingTop: "10px",
            borderTop: "1px solid rgba(255,255,255,0.04)",
          }}
        >
          {topRecipe ? (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                fontSize: "10.5px",
                color: topRecipe.l1_color,
                fontFamily: "ui-monospace, monospace",
              }}
            >
              {topRecipe && (
                <RecipeIcon recipeId={topRecipe.recipe_id} size={14} strokeWidth={1.6} />
              )}
              <span style={{ color: "var(--qgi-text-muted)" }}>top:</span>
              <span style={{ fontWeight: 600 }}>{topRecipe.score.toFixed(0)}</span>
            </span>
          ) : (
            <span
              style={{
                fontSize: "10px",
                color: "var(--qgi-text-dim)",
                fontStyle: "italic",
                fontFamily: "ui-monospace, monospace",
              }}
            >
              no recipes lit
            </span>
          )}

          <span
            style={{
              fontSize: "9.5px",
              padding: "2px 7px",
              borderRadius: "10px",
              fontFamily: "ui-monospace, monospace",
              letterSpacing: "0.3px",
              background:
                country.recipes_lit_graduated > 0
                  ? "rgba(63,191,143,0.15)"
                  : "rgba(122,143,160,0.10)",
              color:
                country.recipes_lit_graduated > 0 ? "#3FBF8F" : "var(--qgi-text-muted)",
              border: `1px solid ${country.recipes_lit_graduated > 0 ? "#3FBF8F" : "var(--qgi-border)"}`,
            }}
            title={`${country.recipes_lit_count} recipes lit; ${country.recipes_lit_graduated} graduated. Non-graduated lights are walked-failed or queued.`}
          >
            {country.recipes_lit_count} lit · {country.recipes_lit_graduated} grad
          </span>
        </div>
      </article>
    </Link>
  );
}
