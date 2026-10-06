import type { Metadata } from "next";
import { getAllRecipes, type TrackerRecipe } from "@/lib/te-mock/recipes";
import { RecipeCard } from "@/components/recipes/RecipeCard";
import { familyColor } from "@/lib/te-mock/l1-families";
import { HowToReadButton } from "@/components/te-v4-shared/HowToReadButton";

export const metadata: Metadata = {
  title: "Trends · QG Intelligence",
  description: "The Trend Catalog: every structural-event trend, grouped by category.",
};

const STATUS_ORDER: Record<TrackerRecipe["status"], number> = {
  graduated: 0,
  walked_no_graduation: 1,
  in_progress: 2,
  live_legacy: 3,
  queued: 4,
};

const L1_ORDER = ["A", "B", "C", "D", "E", "F", "G", "H"];

/**
 * Recipes V4.1 gallery — V4.1 UX rules applied 2026-05-29:
 *   #13: blue "RECIPES" eyebrow removed (academic/methodologist signal)
 *   #14: "The recipe catalog" → "The Recipe Catalog" (title case)
 *   #15: intro tightened — no "research program", no "L1"
 *   #16: per-page vintage stamp / demo-pointer caption removed (one stamp
 *        per session lives in the global header per V4.1 §2)
 *
 * Family-section subheaders no longer prefix the family letter glyph
 * ("A · Political Power") — V4.1 §1.2. The letter stays in code as the
 * internal taxonomy key; the user sees the label alone.
 */
export default function RecipesV41GalleryPage() {
  const recipes = getAllRecipes();
  const groups: Record<string, TrackerRecipe[]> = {};
  for (const r of recipes) {
    if (!groups[r.l1_id]) groups[r.l1_id] = [];
    groups[r.l1_id].push(r);
  }
  for (const k of Object.keys(groups)) {
    groups[k].sort(
      (a, b) =>
        STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || a.label.localeCompare(b.label)
    );
  }

  return (
    <div
      style={{ minHeight: "100%", background: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      <div style={{ maxWidth: "1280px", margin: "0 auto", padding: "24px" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            alignItems: "center",
            marginBottom: "16px",
            gap: "8px",
          }}
        >
          <HowToReadButton routeKey="recipes-v4.1" />
        </div>

        {/* Hero — V4.1 §5 / §1.3 / §15: no eyebrow, title case, one-sentence
            subtitle that sells, no "research program" / "L1" / vintage stamp. */}
        <div style={{ marginBottom: "32px" }}>
          <h1
            style={{
              fontSize: "32px",
              fontWeight: 600,
              lineHeight: 1.15,
              margin: "0 0 12px",
            }}
          >
            The Trend Catalog
          </h1>
          <p
            style={{
              color: "var(--qgi-text-muted)",
              fontSize: "15px",
              lineHeight: 1.55,
              maxWidth: "780px",
            }}
          >
            All {recipes.length} structural-event trends, grouped by category. Click any
            to open its full report card.
          </p>
        </div>

        {/* Sections per L1 — V4.1 §1.2: render family label only, no letter glyph */}
        {L1_ORDER.map((l1Id) => {
          const rs = groups[l1Id];
          if (!rs?.length) return null;
          const l1Label = rs[0].l1_label;
          const l1Color = familyColor(rs[0].l1_id, rs[0].l1_color);
          return (
            <section
              key={l1Id}
              data-tour={`family-section-${l1Id}`}
              style={{ marginTop: "32px" }}
            >
              <header
                style={{
                  display: "flex",
                  gap: "16px",
                  alignItems: "stretch",
                  marginBottom: "16px",
                }}
              >
                <div style={{ width: "4px", background: l1Color, borderRadius: "2px" }} />
                <div>
                  <h2
                    style={{
                      fontSize: "18px",
                      fontWeight: 600,
                      margin: 0,
                      color: "var(--qgi-text)",
                    }}
                  >
                    {l1Label}
                  </h2>
                  <div
                    style={{
                      fontSize: "11px",
                      color: "var(--qgi-text-dim)",
                      marginTop: "4px",
                      letterSpacing: "0.3px",
                    }}
                  >
                    {rs.length} trends
                  </div>
                </div>
              </header>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
                  gap: "14px",
                }}
              >
                {rs.map((r) => {
                  const recipeForCard = {
                    ...r,
                    l1_color: familyColor(r.l1_id, r.l1_color),
                  };
                  return (
                    <RecipeCard
                      key={r.recipe_id}
                      recipe={recipeForCard}
                      basePath="/trends"
                      labelStrategy="v4.1"
                    />
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
