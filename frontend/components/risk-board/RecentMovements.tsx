/**
 * "What just shifted" : recent rank-shift events across the board.
 *
 * Per the honesty contract, every movement is framed as a rank shift
 * / decile movement, NEVER as a probability change.
 *
 * 2026-05-26 schema-align (R&D reply docs-specs #169 §Q3): movements are
 * vintage-over-vintage (~quarterly), not 30-day. Scores only change when
 * a recipe is re-scored on a new data vintage, so a 30-day window would almost
 * always be empty. Field is `delta_quarters` + `vs_vintage`.
 *
 * At vintage 1, the feed is empty by construction (no prior bake to
 * diff against). The component renders <HistoryAccumulatingGate />
 * instead of an empty list.
 */
import Link from "next/link";
import type { Route } from "next";
import { ArrowUp, ArrowDown, Equal, Calendar } from "lucide-react";
import { RecipeIcon } from "@/components/te-v4-shared/RecipeIcon";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import { getAllRecipes } from "@/lib/te-mock/recipes";
import {
  BOARD_VINTAGE,
  getRecentMovements,
  type RankMovement,
} from "@/lib/te-mock/risk-board-data";
import { HistoryAccumulatingGate } from "@/components/te-v4-shared/HistoryAccumulatingGate";
import { familyColor } from "@/lib/te-mock/l1-families";

export function RecentMovements() {
  const events = getRecentMovements();
  const recipes = new Map(getAllRecipes().map((r) => [r.recipe_id, r]));

  // 2026-05-30 polish — when no movements exist (vintage 1 — no prior
  // bake to diff), render a minimal one-line "Quarterly shifts will
  // appear here from the next refresh." line instead of the previous
  // 5-line block of methodology hedge. The full hedge content moves
  // to the section's title attribute for the curious reader.
  if (events.length === 0) {
    return (
      <section
        data-tour="recent-movements"
        style={{
          marginTop: "32px",
          padding: "18px 22px",
          border: "1px solid var(--qgi-border)",
          background: "var(--qgi-surface)",
          borderRadius: "8px",
          display: "flex",
          alignItems: "center",
          gap: "12px",
        }}
        title="Quarterly rank shifts begin at release 2 (the next bake). Release 1 has no prior reading to diff against."
      >
        <Calendar size={14} strokeWidth={1.7} color="var(--qgi-text-dim)" />
        <span
          style={{
            fontSize: "12.5px",
            color: "var(--qgi-text-muted)",
            lineHeight: 1.4,
          }}
        >
          <strong style={{ color: "var(--qgi-text)", fontWeight: 600 }}>
            Quarterly shifts
          </strong>{" "}
          appear here from the next refresh.
        </span>
      </section>
    );
  }

  return (
    <section
      data-tour="recent-movements"
      style={{
        marginTop: "32px",
        padding: "20px",
        border: "1px solid var(--qgi-border)",
        background: "var(--qgi-surface)",
        borderRadius: "8px",
      }}
    >
      <header
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
            Since last quarter
          </div>
          <h2
            style={{
              fontSize: "18px",
              fontWeight: 600,
              margin: 0,
              color: "var(--qgi-text)",
            }}
          >
            What just shifted
          </h2>
        </div>
        <span
          style={{
            fontSize: "10px",
            letterSpacing: "1px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          rank shifts only · no probability change implied
        </span>
      </header>

      {events.length === 0 ? (
        // unreachable — early return above; kept for legacy safety
        <HistoryAccumulatingGate
          vintage={BOARD_VINTAGE}
          label="Release-over-release rank shifts"
        />
      ) : (
        <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {events.map((ev, i) => {
            const recipe = recipes.get(ev.recipe_id);
            if (!recipe) return null;
            return (
              <MovementRow
                key={`${ev.country}-${ev.recipe_id}-${ev.vs_vintage}`}
                ev={ev}
                recipeLabel={recipe.label}
                familyColor={familyColor(recipe.l1_id, recipe.l1_color)}
                isLast={i === events.length - 1}
              />
            );
          })}
        </ol>
      )}
    </section>
  );
}

function MovementRow({
  ev,
  recipeLabel,
  familyColor,
  isLast,
}: {
  ev: RankMovement;
  recipeLabel: string;
  familyColor: string;
  isLast: boolean;
}) {
  const delta = ev.new_rank - ev.prior_rank; // negative = improved (moved up the leaderboard)
  const moved = delta !== 0;

  const DeltaIcon = !moved ? Equal : delta < 0 ? ArrowUp : ArrowDown;
  const deltaColor = !moved ? "var(--qgi-text-dim)" : delta < 0 ? "#E64545" : "#3FBF8F";
  const deltaText = !moved ? "held" : delta < 0 ? `↑ ${Math.abs(delta)}` : `↓ ${delta}`;

  return (
    <li
      style={{
        display: "grid",
        gridTemplateColumns: "auto 1fr auto auto",
        gap: "14px",
        alignItems: "center",
        padding: "12px 0",
        borderBottom: isLast ? "none" : "1px solid var(--qgi-border)",
      }}
    >
      {/* Recipe icon column */}
      <Link
        href={`/trends/${ev.recipe_id}` as Route}
        style={{
          textDecoration: "none",
          color: "inherit",
          display: "flex",
          alignItems: "center",
          gap: "10px",
          minWidth: 0,
        }}
      >
        <div
          style={{
            width: "32px",
            height: "32px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: familyColor,
            border: `1px solid ${familyColor}`,
            borderRadius: "4px",
            flexShrink: 0,
          }}
        >
          <RecipeIcon recipeId={ev.recipe_id} size={16} strokeWidth={1.6} />
        </div>
      </Link>

      {/* Country + recipe + blurb */}
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            fontSize: "13px",
            fontWeight: 600,
            color: "var(--qgi-text)",
            marginBottom: "2px",
          }}
        >
          <FlagImg emoji={flagFor(ev.country)} name={ev.country} width={16} radius={2} />
          <span>
            {ev.country}{" "}
            <span style={{ color: "var(--qgi-text-muted)", fontWeight: 400 }}>
              on {recipeLabel}
            </span>
          </span>
        </div>
        <div
          style={{ fontSize: "11.5px", color: "var(--qgi-text-muted)", lineHeight: 1.45 }}
        >
          {ev.blurb}
        </div>
      </div>

      {/* Rank shift chip */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "6px",
          padding: "5px 10px",
          border: `1px solid ${deltaColor}`,
          borderRadius: "4px",
          color: deltaColor,
          fontFamily: "ui-monospace, monospace",
          fontSize: "11px",
          fontWeight: 600,
          letterSpacing: "0.3px",
          whiteSpace: "nowrap",
        }}
        title={`Rank moved from #${ev.prior_rank} to #${ev.new_rank} on this trend row vs ${ev.vs_vintage}`}
      >
        <DeltaIcon size={12} strokeWidth={2} />
        <span>
          #{ev.prior_rank} → #{ev.new_rank} · {deltaText}
        </span>
      </div>

      {/* Vintage chip : "since 2026-Q2" verbatim, more honest than a relative count */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "5px",
          fontSize: "10.5px",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
          whiteSpace: "nowrap",
          minWidth: "78px",
          justifyContent: "flex-end",
        }}
        title={`Prior reading from release ${ev.vs_vintage} (${ev.delta_quarters} quarter${ev.delta_quarters === 1 ? "" : "s"} ago)`}
      >
        <Calendar size={11} strokeWidth={1.8} />
        since {ev.vs_vintage}
      </div>
    </li>
  );
}
