/**
 * Top-of-page hero strip: "today's top {country × recipe} pairs across the
 * catalog." A single ranked list — the present-tense version of what the
 * retired Signals page tried (and failed) to do.
 *
 * Per the site-architecture spec §2.A: present tense only, tier-gated,
 * vintage-stamped, NO forward verbs.
 */
import Link from "next/link";
import type { Route } from "next";
import { ArrowUp, ArrowDown, Minus } from "lucide-react";
import { RecipeIcon } from "@/components/te-v4-shared/RecipeIcon";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import { getAllRecipes } from "@/lib/te-mock/recipes";
import { getTopPairs, zoneFor, type BoardPair } from "@/lib/te-mock/risk-board-data";
import { familyColor } from "@/lib/te-mock/l1-families";

export function RiskBoardHero({
  vintage: _vintage,
}: {
  /** @deprecated V4.1 §2 — vintage stamp removed. Prop kept for back-compat. */
  vintage?: string;
}) {
  const pairs = getTopPairs();
  const recipes = new Map(getAllRecipes().map((r) => [r.recipe_id, r]));

  return (
    <section
      data-tour="risk-board-hero-strip"
      style={{
        borderTop: "1px solid var(--qgi-border)",
        borderBottom: "1px solid var(--qgi-border)",
        background: "var(--qgi-surface)",
        padding: "20px 0",
        marginBottom: "24px",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          marginBottom: "14px",
        }}
      >
        <div>
          <div
            style={{
              fontSize: "10px",
              letterSpacing: "2.5px",
              textTransform: "uppercase",
              color: "var(--qgi-accent)",
              fontFamily: "ui-monospace, monospace",
              marginBottom: "4px",
            }}
          >
            Today across the catalog
          </div>
          <h2
            style={{
              fontSize: "20px",
              fontWeight: 600,
              margin: 0,
              color: "var(--qgi-text)",
            }}
          >
            Top {pairs.length} country × trend pairs
          </h2>
        </div>
        {/* V4.1 §2: per-panel vintage stamp removed — one stamp in global header. */}
      </div>

      <ol
        style={{
          listStyle: "none",
          padding: 0,
          margin: 0,
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
          gap: "8px",
        }}
      >
        {pairs.map((pair, idx) => (
          <HeroRow
            key={`${pair.country}-${pair.recipe_id}`}
            pair={pair}
            rank={idx + 1}
            recipes={recipes}
          />
        ))}
      </ol>
    </section>
  );
}

function HeroRow({
  pair,
  rank,
  recipes,
}: {
  pair: BoardPair;
  rank: number;
  recipes: Map<string, ReturnType<typeof getAllRecipes>[number]>;
}) {
  const recipe = recipes.get(pair.recipe_id);
  if (!recipe) return null;
  const zone = zoneFor(pair.score);
  const zoneColor =
    zone === "HIGH"
      ? "#E64545"
      : zone === "MODERATE"
        ? "#E68F29"
        : "var(--qgi-text-muted)";
  const displayColor = familyColor(recipe.l1_id, recipe.l1_color);

  return (
    <li>
      <Link
        href={`/trends/${pair.recipe_id}` as Route}
        style={{ textDecoration: "none", color: "inherit", display: "block" }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "10px",
            padding: "10px 12px",
            background: "var(--qgi-bg)",
            border: "1px solid var(--qgi-border)",
            borderRadius: "6px",
            borderLeft: `3px solid ${displayColor}`,
          }}
        >
          {/* Rank */}
          <div
            style={{
              width: "26px",
              fontSize: "11px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
              textAlign: "right",
              flexShrink: 0,
            }}
          >
            {String(rank).padStart(2, "0")}
          </div>

          {/* Recipe icon */}
          <div
            style={{
              width: "32px",
              height: "32px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: displayColor,
              flexShrink: 0,
            }}
          >
            <RecipeIcon recipeId={pair.recipe_id} size={18} strokeWidth={1.6} />
          </div>

          {/* Text */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                fontSize: "13px",
                fontWeight: 600,
                color: "var(--qgi-text)",
                overflow: "hidden",
                minWidth: 0,
              }}
            >
              <FlagImg
                emoji={flagFor(pair.country)}
                name={pair.country}
                width={16}
                radius={2}
              />
              <span
                style={{
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {pair.country}
              </span>
            </div>
            <div
              style={{
                fontSize: "10.5px",
                color: "var(--qgi-text-muted)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {recipe.label}
            </div>
          </div>

          {/* Score + zone */}
          <div style={{ textAlign: "right", flexShrink: 0, minWidth: "62px" }}>
            <div
              style={{
                fontSize: "18px",
                fontWeight: 600,
                color: displayColor,
                fontFamily: "ui-monospace, monospace",
                lineHeight: 1,
              }}
            >
              {pair.score.toFixed(1)}
            </div>
            <div
              style={{
                fontSize: "9px",
                letterSpacing: "1px",
                color: zoneColor,
                fontFamily: "ui-monospace, monospace",
                marginTop: "3px",
              }}
            >
              {zone}
            </div>
          </div>

          {/* Rank delta indicator */}
          <RankDelta delta={pair.rank_delta_q} />
        </div>
      </Link>
    </li>
  );
}

function RankDelta({ delta }: { delta: number | null }) {
  if (delta === null) {
    return <div style={{ width: "32px" }} />;
  }
  if (delta === 0) {
    return (
      <div
        title="No rank shift since last quarter"
        style={{
          width: "32px",
          color: "var(--qgi-text-dim)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Minus size={14} strokeWidth={1.8} />
      </div>
    );
  }
  if (delta < 0) {
    return (
      <div
        title={`Moved up ${Math.abs(delta)} rank(s) since last quarter`}
        style={{
          width: "32px",
          color: "#E64545",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: "2px",
        }}
      >
        <ArrowUp size={14} strokeWidth={2} />
        <span style={{ fontFamily: "ui-monospace, monospace", fontSize: "11px" }}>
          {Math.abs(delta)}
        </span>
      </div>
    );
  }
  return (
    <div
      title={`Moved down ${delta} rank(s) since last quarter`}
      style={{
        width: "32px",
        color: "#3FBF8F",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: "2px",
      }}
    >
      <ArrowDown size={14} strokeWidth={2} />
      <span style={{ fontFamily: "ui-monospace, monospace", fontSize: "11px" }}>
        {delta}
      </span>
    </div>
  );
}
