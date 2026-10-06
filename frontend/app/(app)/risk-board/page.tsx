import type { Metadata } from "next";
import { getAllRecipes } from "@/lib/te-mock/recipes";
import {
  getBoardRecipes,
  getRecipeFullScoreMap,
  getRecipeRow,
} from "@/lib/te-mock/risk-board-data";
import { RecentMovements } from "@/components/risk-board/RecentMovements";
import {
  RiskBoardFilters,
  type RiskBoardRecipeProjection,
} from "@/components/risk-board/RiskBoardFilters";
import { COVERAGE_ROADMAP_THEMES } from "@/lib/hf/trend-taxonomy";
import { familyColor } from "@/lib/te-mock/l1-families";
import { statusLabel } from "@/lib/te-mock/country-families";

export const metadata: Metadata = {
  title: "Risk Board · QG Intelligence",
  description:
    "Present-tense, tier-gated discrimination ranks across the trend catalog. The honest replacement for the retired Signals page.",
};

export default function RiskBoardPage() {
  // Pull rows for the board (the curated set: scored + a representative
  // queued sample) and project to the slim public-safe shape before passing
  // to the client. Raw verdict/stats/status enum are stripped server-side.
  const boardRecipes: RiskBoardRecipeProjection[] = getBoardRecipes().map((r) => {
    const sl = statusLabel(r.status);
    return {
      recipe_id: r.recipe_id,
      label: r.label,
      l1_id: r.l1_id,
      l1_label: r.l1_label,
      l1_color: r.l1_color,
      l2_label: r.l2_label,
      statusLabel: sl.label,
      statusTone: sl.tone,
      // Round-3.5 (2026-05-29): full country→score map per recipe drives
      // the multi-country custom-grid mode. Cascade recipes contribute
      // ~10 entries; TE sample-10 recipes ~150; queued recipes 0.
      // Total payload across the board is ~1.5k entries, manageable as
      // an inline server→client prop.
      scoreByCountry: getRecipeFullScoreMap(r.recipe_id),
    };
  });

  // Aggregate every known country across every visible row — the universe
  // the user can multi-select from. Sorted alphabetically; dedup'd.
  const countryUniverse = (() => {
    const set = new Set<string>();
    for (const recipe of boardRecipes) {
      for (const name of Object.keys(recipe.scoreByCountry)) {
        set.add(name);
      }
    }
    // Also include the top-10 country names from queued recipes' projections
    // when available so the picker doesn't surprise-omit anyone we've ever
    // shown on the board.
    for (const recipe of boardRecipes) {
      const row = getRecipeRow(recipe.recipe_id);
      if (row) for (const c of row.cells) if (c.country !== "—") set.add(c.country);
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  })();

  // Build L1 family meta from the full recipe list so a filter chip exists
  // for every family — even if a family has only queued recipes today.
  // Run each entry through familyColor() so F-family gets its corrected hue.
  const l1Map = new Map<string, { id: string; label: string; color: string }>();
  for (const r of getAllRecipes()) {
    if (!l1Map.has(r.l1_id)) {
      l1Map.set(r.l1_id, {
        id: r.l1_id,
        label: r.l1_label,
        color: familyColor(r.l1_id, r.l1_color),
      });
    }
  }
  const l1Families = Array.from(l1Map.values()).sort((a, b) => a.id.localeCompare(b.id));

  return (
    <div
      style={{ minHeight: "100%", background: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      <div style={{ maxWidth: "1440px", margin: "0 auto", padding: "24px" }}>
        {/* 2026-05-30 — "How to read this page" button removed from Risk
            Board. The new h1 + subtitle ('Where today's country paths
            resemble…' + 3-sentence teaching subtitle) carry the reading
            guidance inline; the popover was redundant. The button stays
            on other surfaces (recipes detail, country detail) where the
            methodology depth still warrants it. */}

        {/* Page hero */}
        <div style={{ marginBottom: "24px" }}>
          <div
            style={{
              color: "var(--qgi-accent)",
              fontSize: "10px",
              letterSpacing: "4px",
              textTransform: "uppercase",
              fontFamily: "ui-monospace, monospace",
              marginBottom: "8px",
            }}
          >
            Risk Board
          </div>
          <h1
            style={{
              fontSize: "32px",
              fontWeight: 600,
              lineHeight: 1.15,
              margin: 0,
            }}
          >
            Where today&apos;s country paths resemble history&apos;s event trends
          </h1>
          {/* HF merge review (2026-06-10): the descriptive paragraph moved
              INTO each tab view so the visible explanation always matches
              the visible grid (the old static copy described trend rows
              while the Topics tab shows country rows). One h1 + one
              tab-appropriate sentence, per V4.1 §5. */}
        </div>

        {/* "Today across the catalog" hero strip removed 2026-05-29 —
            moved to /dashboard in a slim form (TopPairsStrip). The grid
            below is the primary surface here; the dashboard owns the
            teaser. */}

        {/* Filter shell + grid (client component) */}
        {/* "The grid" eyebrow + "Top-10 countries per recipe" h2 removed
            2026-05-30 — redundant with the filter bar that immediately
            announces what this surface is. The grid stands on its own. */}

        {/* Topics->Trends (2026-07-04) + "News Topics" tab dropped (founder
            2026-07-06): the board carries a single view now — the structural
            Trends grid, followed by an honest coverage-roadmap note. The old
            duplicate "News Topics" pane rendered the same trends, so it is gone. */}
        <p
          style={{
            color: "var(--qgi-text-muted)",
            fontSize: "15px",
            lineHeight: 1.6,
            maxWidth: "820px",
            margin: "0 0 16px",
          }}
        >
          Each row is an event trend, a shape reconstructed from past cases. Each cell
          shows how closely a country&apos;s recent path matches that shape. Scan a row
          for today&apos;s closest matches, or pick countries to compare them across the
          catalog.
        </p>
        <div data-tour="risk-board-grid">
          <RiskBoardFilters
            recipes={boardRecipes}
            l1Families={l1Families}
            countryUniverse={countryUniverse}
          />
        </div>
        {/* Recent movements panel (structural, vintage-over-vintage) */}
        <RecentMovements />

        {/* Coverage roadmap (founder 2026-07-06): honest note replacing the old
            "coming soon" teaser columns. Six trends carry a live news reading;
            these themes are tracked but not yet covered. No dates promised. */}
        <section
          style={{
            marginTop: "28px",
            padding: "16px 18px",
            border: "1px solid var(--qgi-border)",
            borderRadius: "8px",
          }}
        >
          <div
            style={{
              color: "var(--qgi-accent)",
              fontSize: "10px",
              letterSpacing: "3px",
              textTransform: "uppercase",
              fontFamily: "ui-monospace, monospace",
              marginBottom: "8px",
            }}
          >
            Coverage roadmap
          </div>
          <p
            style={{
              color: "var(--qgi-text-muted)",
              fontSize: "14px",
              lineHeight: 1.6,
              margin: "0 0 10px",
              maxWidth: "820px",
            }}
          >
            Six trends carry a live news reading today. These themes are tracked and on
            the roadmap, with native feeds still to be built:
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
            {COVERAGE_ROADMAP_THEMES.map((theme) => (
              <span
                key={theme}
                style={{
                  fontSize: "12px",
                  color: "var(--qgi-text-dim)",
                  border: "1px solid var(--qgi-border)",
                  borderRadius: "999px",
                  padding: "3px 10px",
                  fontFamily: "ui-monospace, monospace",
                }}
              >
                {theme}
              </span>
            ))}
          </div>
        </section>

        {/* Cadence footer (single view now, so it lives at page level). */}
        <footer
          style={{
            marginTop: "24px",
            padding: "16px 0",
            borderTop: "1px solid var(--qgi-border)",
            fontSize: "11px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.3px",
          }}
        >
          Scores refresh on each data release. New trends appear as their evidence base
          grows.
        </footer>
      </div>
    </div>
  );
}
