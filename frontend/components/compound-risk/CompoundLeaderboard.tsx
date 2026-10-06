import Link from "next/link";
import type { Route } from "next";
import { RecipeIcon } from "@/components/te-v4-shared/RecipeIcon";
import {
  RECIPE_LOOKUP,
  type CompoundCountry,
  type CompoundLitRecipe,
} from "@/lib/te-mock/compound-risk-data";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { FamilyChip } from "@/components/countries-v4-1/FamilyChip";
import { flagFor } from "@/lib/te-mock/country-flags";
import { familyColor, familyLabel } from "@/lib/te-mock/l1-families";
import { statusLabel } from "@/lib/te-mock/country-families";
import type { JSX } from "react";

interface Props {
  countries: CompoundCountry[];
  minThreshold: number;
  allCount: number;
  filteredCount: number;
  page: number;
  totalPages: number;
  pageSize: number;
  pageStart: number;
}

export function CompoundLeaderboard({
  countries,
  minThreshold,
  allCount,
  filteredCount,
  page,
  totalPages,
  pageSize,
  pageStart,
}: Props) {
  // V4.1 follow-up 2026-05-29 — paginated leaderboard. Range and label below
  // describe the current slice; pagination controls live in the footer.
  const showStart = filteredCount === 0 ? 0 : pageStart + 1;
  const showEnd = Math.min(pageStart + countries.length, filteredCount);

  return (
    <section data-tour="compound-leaderboard" style={{ marginTop: "32px" }}>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "12px",
          marginBottom: "14px",
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
          Compound leaderboard
        </h2>
        <span
          style={{
            fontSize: "10.5px",
            color: "var(--qgi-text-muted)",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.3px",
          }}
        >
          {filteredCount === 0
            ? `0 of ${allCount} · ${minThreshold}+ recipes matched`
            : `${showStart}–${showEnd} of ${filteredCount} · ${minThreshold}+ recipes matched`}
        </span>
      </div>

      {countries.length === 0 ? (
        <div
          style={{
            padding: "32px",
            border: "1px dashed var(--qgi-border)",
            background: "rgba(122,143,160,0.04)",
            borderRadius: "8px",
            textAlign: "center",
            color: "var(--qgi-text-muted)",
            fontSize: "13px",
            fontStyle: "italic",
          }}
        >
          No countries clear the current threshold + family filter. Loosen the minimum or
          remove a family requirement.
        </div>
      ) : (
        <>
          <ol
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
              display: "flex",
              flexDirection: "column",
              gap: "10px",
            }}
          >
            {countries.map((c, i) => (
              <CompoundRow key={c.iso} country={c} rank={pageStart + i + 1} />
            ))}
          </ol>
          <Pagination page={page} totalPages={totalPages} pageSize={pageSize} />
        </>
      )}
    </section>
  );
}

/**
 * Server-rendered pagination control. Each control is a Link with the current
 * filter searchParams preserved and only ?page= updated. The whole control
 * disappears when there's a single page.
 *
 * The pagination context (filter state) is read from the URL by the parent
 * page; we receive only the page number + count of pages here. Pure render,
 * no client JS.
 */
function Pagination({
  page,
  totalPages,
  pageSize,
}: {
  page: number;
  totalPages: number;
  pageSize: number;
}) {
  if (totalPages <= 1) return null;

  // Show: first, prev, current ±2, next, last. Ellipsis when there's a gap.
  const pageNumbers = paginationWindow(page, totalPages);

  return (
    <nav
      aria-label="Compound leaderboard pagination"
      style={{
        marginTop: "20px",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: "12px",
        flexWrap: "wrap",
      }}
    >
      <span
        style={{
          fontSize: "10.5px",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
          letterSpacing: "0.3px",
        }}
      >
        Page {page} of {totalPages} · {pageSize} per page
      </span>
      <div style={{ display: "flex", gap: "4px", alignItems: "center" }}>
        <PageLink page={page - 1} disabled={page <= 1} label="Prev" />
        {pageNumbers.map((p, i) =>
          p === "…" ? (
            <span
              key={`gap-${i}`}
              aria-hidden="true"
              style={{
                fontSize: "11px",
                color: "var(--qgi-text-dim)",
                padding: "0 4px",
                fontFamily: "ui-monospace, monospace",
              }}
            >
              …
            </span>
          ) : (
            <PageLink key={p} page={p} active={p === page} label={String(p)} />
          )
        )}
        <PageLink page={page + 1} disabled={page >= totalPages} label="Next" />
      </div>
    </nav>
  );
}

/** Compute a compact page window: first, current±2, last, with ellipses. */
function paginationWindow(current: number, total: number): Array<number | "…"> {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const set = new Set<number>([1, total, current - 1, current, current + 1]);
  // Add a buffer at the edges so we don't get "1, 2, 3, 4, 5, ..., 10" but
  // "1, ..., 4, 5, 6, ..., 10".
  if (current <= 4) [2, 3, 4].forEach((n) => set.add(n));
  if (current >= total - 3) [total - 1, total - 2, total - 3].forEach((n) => set.add(n));
  const sorted = Array.from(set)
    .filter((n) => n >= 1 && n <= total)
    .sort((a, b) => a - b);
  const out: Array<number | "…"> = [];
  for (let i = 0; i < sorted.length; i++) {
    out.push(sorted[i]);
    if (i < sorted.length - 1 && sorted[i + 1] !== sorted[i] + 1) out.push("…");
  }
  return out;
}

function PageLink({
  page,
  active,
  disabled,
  label,
}: {
  page: number;
  active?: boolean;
  disabled?: boolean;
  label: string;
}) {
  const style: React.CSSProperties = {
    minWidth: "28px",
    padding: "4px 8px",
    fontSize: "11px",
    fontFamily: "ui-monospace, monospace",
    letterSpacing: "0.3px",
    textAlign: "center",
    border: `1px solid ${active ? "var(--qgi-accent)" : "var(--qgi-border)"}`,
    borderRadius: "4px",
    background: active ? "var(--qgi-accent)" : "var(--qgi-surface)",
    color: disabled
      ? "var(--qgi-text-dim)"
      : active
        ? "var(--qgi-bg)"
        : "var(--qgi-text-muted)",
    textDecoration: "none",
    cursor: disabled ? "default" : "pointer",
    opacity: disabled ? 0.4 : 1,
    pointerEvents: disabled ? "none" : "auto",
  };
  if (disabled) {
    return (
      <span style={style} aria-disabled="true">
        {label}
      </span>
    );
  }
  // Preserve current filter state via the search params already in the URL.
  // The Link rewrites only the `page` param via the `?page=…` hash; Next.js
  // typed-routes is happy with a relative search string.
  const href = `?page=${page}` as Route;
  return (
    <Link href={href} style={style} aria-current={active ? "page" : undefined}>
      {label}
    </Link>
  );
}

function CompoundRow({ country, rank }: { country: CompoundCountry; rank: number }) {
  const sortedRecipes = [...country.lit_recipes].sort((a, b) => b.score - a.score);

  // Rule 2: country-scoped family chips use the top-recipe-in-family icon as
  // the glyph. Build a lookup: famId → top-scoring recipe_id in that family.
  const topRecipeByFamily = new Map<string, string>();
  for (const r of sortedRecipes) {
    if (!topRecipeByFamily.has(r.l1_id)) {
      topRecipeByFamily.set(r.l1_id, r.recipe_id);
    }
  }
  return (
    <li>
      <article
        style={{
          background: "var(--qgi-surface)",
          border: "1px solid var(--qgi-border)",
          borderRadius: "8px",
          padding: "14px 16px",
          display: "grid",
          gridTemplateColumns: "44px minmax(180px, 1.4fr) 1fr 110px",
          alignItems: "center",
          gap: "16px",
        }}
      >
        {/* Rank */}
        <div
          style={{
            fontSize: "18px",
            fontWeight: 600,
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            textAlign: "right",
          }}
        >
          {String(rank).padStart(2, "0")}
        </div>

        {/* Country block */}
        <div style={{ minWidth: 0 }}>
          <Link
            href={`/countries/${country.iso.toLowerCase()}` as Route}
            style={{
              textDecoration: "none",
              color: "var(--qgi-text)",
              display: "flex",
              alignItems: "center",
              gap: "10px",
            }}
          >
            <FlagImg emoji={flagFor(country.country)} name={country.country} width={24} />
            <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
              <span style={{ fontSize: "15px", fontWeight: 600, lineHeight: 1.2 }}>
                {country.country}
              </span>
              <span
                style={{
                  fontSize: "10.5px",
                  color: "var(--qgi-text-dim)",
                  letterSpacing: "0.6px",
                  fontFamily: "ui-monospace, monospace",
                  marginTop: "2px",
                }}
              >
                {country.iso} · {country.region}
              </span>
            </span>
          </Link>
          {/* Rule 2: family chips on a country-scoped surface. Each chip
              keeps showLabel={false} (compact) but the letter glyph is
              replaced by the top-recipe-in-family icon via iconNode. */}
          <div
            style={{ display: "flex", gap: "4px", marginTop: "8px", flexWrap: "wrap" }}
          >
            {country.lit_families.map((famId) => {
              const fam = country.lit_recipes.find((r) => r.l1_id === famId);
              if (!fam) return null;
              const color = familyColor(famId, fam.l1_color);
              const label = familyLabel(famId, fam.l1_label);
              const topRecipeId = topRecipeByFamily.get(famId);
              const iconNode: JSX.Element | undefined = topRecipeId ? (
                <RecipeIcon
                  recipeId={topRecipeId}
                  size={12}
                  strokeWidth={1.8}
                  aria-hidden="true"
                />
              ) : undefined;
              return (
                <FamilyChip
                  key={famId}
                  id={famId}
                  label={label}
                  color={color}
                  showLabel={false}
                  iconNode={iconNode}
                />
              );
            })}
          </div>
        </div>

        {/* Recipe icons row */}
        <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
          {sortedRecipes.map((r) => (
            <RecipeChip key={r.recipe_id} recipe={r} />
          ))}
        </div>

        {/* Score block */}
        <div style={{ textAlign: "right" }}>
          <div
            style={{
              fontSize: "10px",
              letterSpacing: "1px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
              marginBottom: "3px",
            }}
            title={
              `Bounded 0-100 score. Averages this country's recipe matches ` +
              `(root-mean-square), dampened for thin coverage. ` +
              `Prior unbounded sum-of-margins for this country: ${country.compound_score_legacy.toFixed(1)}.`
            }
          >
            COMPOUND RISK
          </div>
          <div
            style={{
              fontSize: "26px",
              fontWeight: 600,
              fontFamily: "ui-monospace, monospace",
              color: "var(--qgi-amber)",
              lineHeight: 1,
            }}
          >
            {country.compound_score.toFixed(1)}
          </div>
          <div
            style={{
              fontSize: "10px",
              color: "var(--qgi-text-muted)",
              fontFamily: "ui-monospace, monospace",
              marginTop: "4px",
              letterSpacing: "0.3px",
            }}
          >
            {country.lit_recipes.length} recipes matched
          </div>
        </div>
      </article>
    </li>
  );
}

function RecipeChip({ recipe }: { recipe: CompoundLitRecipe }) {
  const tracker = RECIPE_LOOKUP[recipe.recipe_id];
  const rawStatus = tracker?.status ?? "queued";
  const { label: friendlyStatus } = statusLabel(rawStatus);
  const chipColor = familyColor(recipe.l1_id, recipe.l1_color);
  return (
    <Link
      href={`/trends/${recipe.recipe_id}` as Route}
      title={`${recipe.label}: score ${recipe.score.toFixed(1)} (decile ${recipe.decile}), ${friendlyStatus}`}
      style={{
        textDecoration: "none",
        position: "relative",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: "38px",
        height: "38px",
        borderRadius: "6px",
        background: `${chipColor}1A`,
        border: `1px solid ${chipColor}`,
        color: chipColor,
        // Tested-did-not-hold-up signature: dashed border per RecipeCard.tsx convention.
        borderStyle: rawStatus === "walked_no_graduation" ? "dashed" : "solid",
        opacity: rawStatus === "queued" ? 0.55 : 1,
      }}
    >
      <RecipeIcon recipeId={recipe.recipe_id} size={20} strokeWidth={1.6} />
      <span
        style={{
          position: "absolute",
          bottom: "-4px",
          right: "-4px",
          fontSize: "9px",
          fontFamily: "ui-monospace, monospace",
          background: "var(--qgi-bg)",
          color: "var(--qgi-text-muted)",
          border: "1px solid var(--qgi-border)",
          borderRadius: "8px",
          padding: "1px 4px",
          lineHeight: 1,
          letterSpacing: "0.2px",
        }}
      >
        {recipe.score.toFixed(0)}
      </span>
      {/* Hidden a11y status — screen readers pick it up from title above */}
      <span style={{ position: "absolute", left: "-9999px" }} aria-hidden>
        {friendlyStatus}
      </span>
    </Link>
  );
}
