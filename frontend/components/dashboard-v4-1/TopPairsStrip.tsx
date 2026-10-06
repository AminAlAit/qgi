/**
 * TopPairsStrip — Dashboard right-rail "story tape" of top country-recipe
 * pairs ranked by confidence.
 *
 * 2026-05-30 — restructured from a 2-column horizontal strip into a single-
 * column vertical rail. The component now sits in a sticky right-side column
 * on the dashboard, holding up to 20 hand-curated pairs (data contract:
 * `data/curated-top-pairs.json` produced by a parallel curation agent;
 * graceful fallback to getTopPairs() when the curated drop is absent).
 *
 * Rail design rationale (Sard mini-majles, 2026-05-30):
 *   - Position: sticky (scrolls until pinned), not fixed. Preserves natural
 *     scroll rhythm; works at any page length.
 *   - Width: 320px (set by parent grid). One-line row layout: rank · flag ·
 *     country · recipe · score. Rationale (when present) renders on a
 *     second line, dim.
 *   - Cap: all 20 visible with internal scroll on max-height. The rail IS
 *     the story tape; hiding rows behind a "Show all" defeats the
 *     peripheral-scan affordance.
 *   - Header: "Top 20 today" with one-line caption. Calm slate so the rail
 *     stays quieter than the family-color insight plots.
 *   - Visual weight: family-color left border on each row (the only color
 *     tie-back to the rest of the dashboard idiom); score uses the shared
 *     lerp + glow helper.
 */
import Link from "next/link";
import type { Route } from "next";
import { PanelBase } from "./PanelBase";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { RecipeIcon } from "@/components/te-v4-shared/RecipeIcon";
import { flagFor } from "@/lib/te-mock/country-flags";
import { getAllRecipes } from "@/lib/te-mock/recipes";
import {
  getCuratedTopPairs,
  getTopPairs,
  type BoardPair,
  type CuratedBoardPair,
} from "@/lib/te-mock/risk-board-data";
import { familyColor } from "@/lib/te-mock/l1-families";
import { MUTED_GRAY, confidenceT, lerpHexToRgb, confidenceGlow } from "@/lib/color-lerp";

interface Props {
  /**
   * Max pairs to show. Default 20 — matches the curated drop size.
   * The rail's internal scroll absorbs whatever fits in the viewport.
   */
  limit?: number;
}

export function TopPairsStrip({ limit = 20 }: Props) {
  // Curated 20-pair list is the canonical source. Fall back to the legacy
  // getTopPairs() merge when the curated drop is not yet present, so the
  // surface never renders empty during the parallel-agent landing window.
  const curated = getCuratedTopPairs();
  const pairs: Array<CuratedBoardPair | (BoardPair & { rank: number })> =
    curated.length > 0
      ? curated.slice(0, limit)
      : getTopPairs()
          .slice(0, limit)
          .map((p, i) => ({ ...p, rank: i + 1 }));

  const recipes = new Map(getAllRecipes().map((r) => [r.recipe_id, r]));
  const countLabel = pairs.length;

  // Visual-density count for accessibility-only; not surfaced in the
  // header (founder asked the header to read just "Highlights").
  void countLabel;

  return (
    <PanelBase
      title="Highlights"
      rightSlot={
        <Link
          href={"/risk-board" as Route}
          style={{
            fontSize: "10.5px",
            letterSpacing: "0.4px",
            color: "var(--qgi-accent)",
            fontFamily: "ui-monospace, monospace",
            textDecoration: "none",
            whiteSpace: "nowrap",
          }}
        >
          Open Risk Board →
        </Link>
      }
    >
      {/* 2026-05-30: rail is non-sticky + non-scrolling. The full list
          flows with the page; overflow is dictated by the page's normal
          scroll, not an internal scrollbar. */}
      <ol
        style={{
          listStyle: "none",
          padding: 0,
          margin: 0,
          display: "flex",
          flexDirection: "column",
          gap: "6px",
        }}
      >
        {pairs.map((pair) => {
          const recipe = recipes.get(pair.recipe_id);
          if (!recipe) return null;
          return (
            <PairRow
              key={`${pair.country}-${pair.recipe_id}-${pair.rank}`}
              pair={pair}
              recipeId={pair.recipe_id}
              recipeLabel={recipe.label}
              recipeFamilyColor={familyColor(recipe.l1_id, recipe.l1_color)}
            />
          );
        })}
      </ol>
    </PanelBase>
  );
}

function PairRow({
  pair,
  recipeId,
  recipeLabel,
  recipeFamilyColor,
}: {
  pair: CuratedBoardPair | (BoardPair & { rank: number });
  recipeId: string;
  recipeLabel: string;
  recipeFamilyColor: string;
}) {
  const pct = Math.round(pair.score);
  const cT = confidenceT(pair.score);
  const pctColor = lerpHexToRgb(MUTED_GRAY, recipeFamilyColor, cT);
  const pctGlow = confidenceGlow(recipeFamilyColor, cT);
  const rationale = "rationale" in pair ? pair.rationale : undefined;
  // Card reads as a sentence:
  //   [recipe icon · family color] Recipe Label … score%
  //   [flag] Country  (one indent under the icon column)
  // Recipe-first per Lea: the dashboard's question is "which shapes are
  // matching"; the country is the predicate of the sentence, not the
  // subject. Icon + family color give the recipe-identity glance Ingrid
  // wanted. Rank numbers dropped per Yuki (founder concurred).

  return (
    <li>
      <Link
        href={`/trends/${recipeId}` as Route}
        style={{ textDecoration: "none", color: "inherit", display: "block" }}
        title={rationale}
      >
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "3px",
            padding: "8px 10px",
            background: "var(--qgi-bg)",
            border: "1px solid var(--qgi-border)",
            borderLeft: `2px solid ${recipeFamilyColor}`,
            borderRadius: "4px",
          }}
        >
          {/* Row 1: recipe icon · recipe label · score */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              minHeight: "20px",
            }}
          >
            <span
              aria-hidden="true"
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                color: recipeFamilyColor,
                flexShrink: 0,
                width: "18px",
                height: "18px",
              }}
            >
              <RecipeIcon recipeId={recipeId} size={16} strokeWidth={1.7} />
            </span>

            <span
              style={{
                flex: 1,
                minWidth: 0,
                fontSize: "12px",
                fontWeight: 600,
                color: "var(--qgi-text)",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
                lineHeight: 1.2,
              }}
            >
              {recipeLabel}
            </span>

            <span
              style={{
                fontSize: "14px",
                fontWeight: 700,
                fontFamily: "ui-monospace, monospace",
                letterSpacing: "-0.3px",
                color: pctColor,
                textShadow: pctGlow || undefined,
                flexShrink: 0,
                transition: "text-shadow 180ms ease-out, color 180ms",
                minWidth: "32px",
                textAlign: "right",
              }}
              title={`${pct}% match: this country's recent path matches the trend's canonical shape.`}
            >
              {pct}%
            </span>
          </div>

          {/* Row 2: flag · country (indented under the icon) */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              paddingLeft: "26px",
              fontSize: "11px",
              color: "var(--qgi-text-muted)",
              lineHeight: 1.25,
            }}
          >
            <FlagImg
              emoji={flagFor(pair.country)}
              name={pair.country}
              width={14}
              radius={2}
            />
            <span
              style={{
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
                flex: 1,
                minWidth: 0,
                color: "var(--qgi-text)",
                fontWeight: 500,
              }}
            >
              {pair.country}
            </span>
          </div>
        </div>
      </Link>
    </li>
  );
}
