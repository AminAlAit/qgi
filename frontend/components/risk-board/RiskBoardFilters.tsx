"use client";

/**
 * Client-side filter + search shell around the inlined FilteredGrid. Keeps
 * interactivity out of the server page per the Next.js 16 page convention
 * (page.tsx stays a Server Component).
 *
 * Filters:
 *   - L1 family chips (multi-select; empty = all).
 *   - Status filter (scored / queued — but only the
 *     scored statuses produce visible scores; queued shows greyed rows).
 *   - Free-text country search (matches any cell.country in any visible row).
 *
 * Search behaviour: when a country query is entered, each row's cells are
 * filtered down to matching countries (and the rank position is preserved).
 * Rows with zero matches drop out.
 *
 * RiskGrid.tsx was deleted in QA-8 P1. All grid rendering now lives here so
 * the §Q7 coverage caption + not_scored cell branch always render.
 */

import { useMemo, useState } from "react";
import { Search, X, Filter, RotateCcw, Star } from "lucide-react";
import { RecipeIcon } from "@/components/te-v4-shared/RecipeIcon";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
// 2026-05-29 — touch comment to force Turbopack to re-detect this module's
// dependency on the updated FlagImg + country-flags lib (cache invalidation
// guard for the 16-flag-missing fix).
import { flagFor, iso2For } from "@/lib/te-mock/country-flags";
import { useUserSettings } from "@/components/settings/useUserSettings";
import {
  getRecipeRow,
  type BoardCell,
  type RecipeRow,
} from "@/lib/te-mock/risk-board-data";
import { familyColor } from "@/lib/te-mock/l1-families";
import { MUTED_GRAY, confidenceT, lerpHexToRgb, confidenceGlow } from "@/lib/color-lerp";
import Link from "next/link";
import type { Route } from "next";

/** Slim projection type — only public-safe fields forwarded from the server. */
export interface RiskBoardRecipeProjection {
  recipe_id: string;
  label: string;
  l1_id: string;
  l1_label: string;
  l1_color: string;
  l2_label: string;
  statusLabel: string;
  statusTone: "deployed" | "neutral" | "failed";
  /**
   * Round-3.5 (2026-05-29) — full country→score lookup for THIS recipe,
   * used in custom-grid mode when the user selects specific countries
   * that may not be in the recipe's default top-10. Empty object for
   * queued recipes.
   */
  scoreByCountry: Record<string, number>;
}

interface Props {
  recipes: RiskBoardRecipeProjection[];
  /** L1 family meta to render filter chips. Derived once on the server. */
  l1Families: Array<{ id: string; label: string; color: string }>;
  /** Every country that could be selected (union of every recipe's
   *  scored countries + every recipe row's rendered cells). Sorted
   *  alphabetically server-side. */
  countryUniverse: string[];
}

const MAX_SELECTED = 10;

/** Short chip labels for the filter bar — saves horizontal space without
 *  changing canonical family names elsewhere. */
const CHIP_SHORT_LABEL: Record<string, string> = {
  "Diplomacy & Geopolitics": "Diplomacy",
  "Humanitarian Crisis": "Humanitarian",
};

export function RiskBoardFilters({ recipes, l1Families, countryUniverse }: Props) {
  const [selectedL1, setSelectedL1] = useState<Set<string>>(new Set());
  // Round-3.5 (2026-05-29): status filter retired. The grid is scored-only
  // by default and queued recipes never enter the grid mode — the user
  // never asked for that toggle.
  // Round-3.5 country multi-select. When N>0, the grid renders with
  // selectedCountries as columns instead of top-10 per recipe. Capped at
  // MAX_SELECTED. Order preserved (first selected = first column).
  // The effective selection (`selectedCountries`, derived below) is the
  // watchlist until the user edits it, then their manual list. Keeping it
  // derived — rather than copying the watchlist into state via an effect —
  // makes the watchlist a default lens with no render side-effects.
  const [manualCountries, setManualCountries] = useState<string[]>([]);
  const [userTouchedCountries, setUserTouchedCountries] = useState(false);
  // Country picker free-text typeahead — distinct from the grid filter
  // search of yore. The query narrows the dropdown list, not the rows.
  const [pickerQuery, setPickerQuery] = useState("");
  // Hover highlight in custom-grid mode. When the user hovers any cell,
  // every cell carrying the same country across rows lights up; the rest
  // fade. Null = no hover, normal rendering.
  const [hoveredCountry, setHoveredCountry] = useState<string | null>(null);

  // Watchlist → default lens. The user's watchlist (settings.watchlist, stored
  // as alpha-2 codes) is mapped to this board's country NAMES via the board's
  // own iso2For() so the identity matches exactly.
  const { settings } = useUserSettings();
  const watchlistNames = useMemo(() => {
    const codes = new Set(settings.watchlist.map((c) => c.toUpperCase()));
    if (codes.size === 0) return [] as string[];
    return countryUniverse.filter((name) => {
      const i2 = iso2For(name);
      return i2 ? codes.has(i2.toUpperCase()) : false;
    });
  }, [settings.watchlist, countryUniverse]);
  const watchlistSeed = useMemo(
    () => watchlistNames.slice(0, MAX_SELECTED),
    [watchlistNames]
  );
  // Derived: the watchlist is the default until the user edits the selection.
  const selectedCountries = userTouchedCountries ? manualCountries : watchlistSeed;

  const toggleL1 = (id: string) => {
    setSelectedL1((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Edits operate on the current effective selection (watchlist or manual) and
  // flip it to manual, so the first edit "adopts" the watchlist then diverges.
  const addCountry = (name: string) => {
    setPickerQuery("");
    if (selectedCountries.includes(name) || selectedCountries.length >= MAX_SELECTED)
      return;
    setUserTouchedCountries(true);
    setManualCountries([...selectedCountries, name]);
  };
  const removeCountry = (name: string) => {
    setUserTouchedCountries(true);
    setManualCountries(selectedCountries.filter((c) => c !== name));
  };
  const applyWatchlist = () => {
    setUserTouchedCountries(true);
    setManualCountries(watchlistSeed);
  };

  const reset = () => {
    setSelectedL1(new Set());
    setUserTouchedCountries(true);
    setManualCountries([]);
    setPickerQuery("");
  };

  const pq = pickerQuery.trim().toLowerCase();

  // Suggestions for the typeahead — top 8 matches, with already-selected
  // countries excluded. Country names are dense enough that the user can
  // usually type 2-3 chars and pick.
  const pickerSuggestions = useMemo(() => {
    if (!pq && selectedCountries.length === 0) return [];
    const out: string[] = [];
    for (const name of countryUniverse) {
      if (selectedCountries.includes(name)) continue;
      if (!pq || name.toLowerCase().includes(pq)) {
        out.push(name);
        if (out.length >= 8) break;
      }
    }
    return out;
  }, [pq, countryUniverse, selectedCountries]);

  // Trend focus (user setting) narrows the board to the trends the user acts
  // on. `showAllTrends` is a local escape hatch to reveal every trend without
  // touching the saved preference.
  const [showAllTrends, setShowAllTrends] = useState(false);
  const trendFocus = settings.trendFocus;
  const focusActive = !showAllTrends && !!trendFocus && trendFocus.length > 0;

  // Apply L1 filter + trend focus + always-scored mode → rows for the grid.
  const visibleRows = useMemo(() => {
    const rows: Array<{ recipe: RiskBoardRecipeProjection; row: RecipeRow }> = [];
    for (const recipe of recipes) {
      if (selectedL1.size > 0 && !selectedL1.has(recipe.l1_id)) continue;
      if (focusActive && trendFocus && !trendFocus.includes(recipe.recipe_id)) continue;
      const row = getRecipeRow(recipe.recipe_id);
      if (!row) continue;
      // Round-3.5: scored-only. Coming-soon recipes never enter the grid.
      if (row.display_state === "queued") continue;
      rows.push({ recipe, row });
    }
    return rows;
  }, [recipes, selectedL1, focusActive, trendFocus]);

  const customMode = selectedCountries.length > 0;
  const activeFilterCount = selectedL1.size + selectedCountries.length;

  return (
    <>
      {/* Filter bar */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "12px",
          alignItems: "center",
          padding: "14px 16px",
          marginBottom: "14px",
          border: "1px solid var(--qgi-border)",
          background: "var(--qgi-surface)",
          borderRadius: "8px",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            color: "var(--qgi-text-dim)",
          }}
        >
          <Filter size={14} strokeWidth={1.6} />
          <span
            style={{
              fontSize: "10px",
              letterSpacing: "1.5px",
              textTransform: "uppercase",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            Filter
          </span>
        </div>

        {/* L1 family chips */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: "5px" }}>
          {l1Families.map((fam) => {
            const active = selectedL1.has(fam.id);
            const displayColor = familyColor(fam.id, fam.color);
            return (
              <button
                key={fam.id}
                type="button"
                onClick={() => toggleL1(fam.id)}
                style={{
                  fontSize: "10px",
                  padding: "3px 7px",
                  background: active ? displayColor : "transparent",
                  color: active ? "var(--qgi-bg)" : displayColor,
                  border: `1px solid ${displayColor}`,
                  borderRadius: "4px",
                  fontFamily: "ui-monospace, monospace",
                  letterSpacing: "0.3px",
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "4px",
                }}
                title={`Toggle ${fam.label}`}
              >
                <span
                  style={{
                    width: "6px",
                    height: "6px",
                    borderRadius: "50%",
                    background: active ? "var(--qgi-bg)" : displayColor,
                  }}
                />
                {/* V4.1 §1.2: family letter glyph banned. Label only. */}
                {CHIP_SHORT_LABEL[fam.label] ?? fam.label}
              </button>
            );
          })}
        </div>

        <span
          style={{
            width: "1px",
            height: "22px",
            background: "var(--qgi-border)",
            margin: "0 4px",
          }}
        />

        {/* Round-3.5 (2026-05-29): country multi-select picker. The user
            picks up to 10 countries; the grid then switches to a
            custom-column mode where each column is a selected country
            and each cell is that country's score in that recipe (or
            "not scored" when the country lacks coverage). */}
        <CountryMultiPicker
          selected={selectedCountries}
          suggestions={pickerSuggestions}
          query={pickerQuery}
          onQueryChange={setPickerQuery}
          onAdd={addCountry}
          onRemove={removeCountry}
        />

        <span style={{ flex: 1 }} />

        {trendFocus && trendFocus.length > 0 && (
          <button
            type="button"
            onClick={() => setShowAllTrends((v) => !v)}
            title={focusActive ? "Show all trends" : "Show only your focus trends"}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "5px",
              fontSize: "10.5px",
              padding: "5px 10px",
              background: focusActive ? "var(--qgi-accent)" : "transparent",
              color: focusActive ? "var(--qgi-bg)" : "var(--qgi-accent)",
              border: "1px solid var(--qgi-accent)",
              borderRadius: "4px",
              fontFamily: "ui-monospace, monospace",
              cursor: "pointer",
            }}
          >
            <Filter size={11} strokeWidth={1.8} />
            {focusActive ? `Focus: ${trendFocus.length}` : "All trends"}
          </button>
        )}

        {watchlistNames.length > 0 && (
          <button
            type="button"
            onClick={applyWatchlist}
            title="Show your watchlist countries"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "5px",
              fontSize: "10.5px",
              padding: "5px 10px",
              background: "transparent",
              color: "var(--qgi-accent)",
              border: "1px solid var(--qgi-accent)",
              borderRadius: "4px",
              fontFamily: "ui-monospace, monospace",
              cursor: "pointer",
            }}
          >
            <Star size={11} strokeWidth={1.8} />
            My watchlist
          </button>
        )}

        {activeFilterCount > 0 && (
          <button
            type="button"
            onClick={reset}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "5px",
              fontSize: "10.5px",
              padding: "5px 10px",
              background: "transparent",
              color: "var(--qgi-text-dim)",
              border: "1px solid var(--qgi-border)",
              borderRadius: "4px",
              fontFamily: "ui-monospace, monospace",
              cursor: "pointer",
            }}
          >
            <RotateCcw size={11} strokeWidth={1.8} />
            Reset ({activeFilterCount})
          </button>
        )}
      </div>

      {/* Grid — switches between default top-10 mode and custom-country
          mode depending on whether the user has selected any countries.
          Hover-to-highlight and dim-others are always on (founder ask
          2026-05-30 round 3): without the dim, the highlight is invisible
          on a 44-row board because the hovered match doesn't stand out
          against equally-bright neighbours. */}
      <FilteredGrid
        rows={visibleRows}
        customCountries={customMode ? selectedCountries : null}
        hoveredCountry={hoveredCountry}
        onHoverCountry={setHoveredCountry}
        dimOthersOnHover={true}
      />
    </>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/* In-place client grid — accepts already-filtered rows + a country query     */
/* to apply per-cell highlighting. Ported from RiskGrid.tsx (deleted QA-8).  */
/* Includes the §Q7 coverage caption + not_scored cell branch.               */
/* ────────────────────────────────────────────────────────────────────────── */

function FilteredGrid({
  rows,
  customCountries,
  hoveredCountry,
  onHoverCountry,
  dimOthersOnHover,
}: {
  rows: Array<{ recipe: RiskBoardRecipeProjection; row: RecipeRow }>;
  /** Null = default top-10 mode. Array (≥1) = custom-column mode with
   *  these countries as the columns. */
  customCountries: string[] | null;
  hoveredCountry: string | null;
  onHoverCountry: (name: string | null) => void;
  /** True only in custom-column mode where columns are vertically aligned
   *  across rows; in default mode each row's top-10 is mostly disjoint so
   *  dimming 43/44 rows reads as the page going dark. */
  dimOthersOnHover: boolean;
}) {
  if (rows.length === 0) {
    return (
      <div
        style={{
          padding: "32px",
          border: "1px dashed var(--qgi-border)",
          borderRadius: "6px",
          textAlign: "center",
          color: "var(--qgi-text-muted)",
          fontSize: "13px",
        }}
      >
        No trends match the current filters. Try clearing one.
      </div>
    );
  }

  // Number of cell columns + the grid-template string. In default mode
  // we always render exactly 10 columns (#1..#10). In custom mode the
  // number matches the user's selection (1..10).
  const colCount = customCountries ? customCountries.length : 10;
  // Label column: floor reduced to 96px on narrow screens (was 160px) so the
  // 10 data columns aren't pushed off-screen. 28% resolves to ~215px at 768px
  // and ~280px at desktop — unchanged above 1024px.
  // Per-cell min reduced from 60px to 44px so 10 columns fit at 768px without
  // overflow (96 + 10×44 = 536px < 768px available).
  const gridTemplate = `clamp(96px, 28%, 280px) repeat(${colCount}, minmax(44px, 1fr))`;

  return (
    <div>
      {/* Rounded CLIP FRAME (overflow:hidden, no scroll) + inner SCROLLER
        (overflow:auto). Keeping border-radius on the non-scrolling frame avoids
        the iOS Safari corner-clipping / scrollbar glitch that occurs when
        overflow:auto and border-radius are on the same element. */}
      <div
        style={{
          border: "1px solid var(--qgi-border)",
          borderRadius: "8px",
          background: "var(--qgi-surface)",
          overflow: "hidden",
        }}
      >
        <div style={{ overflow: "auto" }}>
          {/* Explicit min-width on the scroller's content (mirrors TopicBoard's
              VerdictGrid): guarantees the overflow:auto scroller always has
              content wider than a phone viewport to scroll. Floor = label clamp
              floor (96px) + colCount × 44px per-cell floor. On desktop this is a
              floor only — the grid's 1fr tracks expand to fill the container. */}
          <div style={{ minWidth: `${96 + colCount * 44}px` }}>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: gridTemplate,
                background: "var(--qgi-bg)",
                borderBottom: "1px solid var(--qgi-border)",
                fontFamily: "ui-monospace, monospace",
                fontSize: "10.5px",
                letterSpacing: "1px",
                color: "var(--qgi-text-dim)",
              }}
            >
              <div
                style={{
                  padding: "10px 14px",
                  borderRight: "1px solid var(--qgi-border)",
                }}
              >
                Trend ↓ · Country →
              </div>
              {/* Header columns — rank labels in BOTH modes. In custom mode the
            cells re-sort per row by score, so a fixed country header at
            the top would mismatch the cells beneath; rank labels stay
            stable and the cells carry their own country identity. */}
              {Array.from({ length: colCount }, (_, i) => (
                <div
                  key={i}
                  style={{
                    padding: "10px 6px",
                    textAlign: "center",
                    borderRight:
                      i === colCount - 1 ? "none" : "1px solid var(--qgi-border)",
                  }}
                >
                  #{i + 1}
                </div>
              ))}
            </div>

            {/* Round-3.5.2 (2026-05-29) — recipes grouped by L1 family. Each
          family gets a section header strip in its own family color so
          the grid reads as A-Z-keyed bands instead of an undifferentiated
          flat list. Group order follows the canonical A..H L1 sequence
          (already passed down via the l1Families prop). */}
            {(() => {
              const groups: Array<{
                l1_id: string;
                l1_label: string;
                l1_color: string;
                items: typeof rows;
              }> = [];
              const seen = new Map<string, number>();
              for (const r of rows) {
                let idx = seen.get(r.recipe.l1_id);
                if (idx === undefined) {
                  idx = groups.length;
                  seen.set(r.recipe.l1_id, idx);
                  groups.push({
                    l1_id: r.recipe.l1_id,
                    l1_label: r.recipe.l1_label,
                    l1_color: familyColor(r.recipe.l1_id, r.recipe.l1_color),
                    items: [],
                  });
                }
                groups[idx].items.push(r);
              }
              // Stable canonical L1 ordering (A..H).
              groups.sort((a, b) => a.l1_id.localeCompare(b.l1_id));

              const totalRows = rows.length;
              let renderedRowIdx = 0;
              return groups.map((g, gi) => (
                <div key={g.l1_id}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "10px",
                      padding: "10px 16px 9px",
                      background: `linear-gradient(90deg, ${hexToRgba(g.l1_color, 0.16)} 0%, ${hexToRgba(g.l1_color, 0.02)} 100%)`,
                      borderTop: gi === 0 ? "none" : "1px solid var(--qgi-border)",
                      borderBottom: "1px solid var(--qgi-border)",
                    }}
                  >
                    <span
                      aria-hidden="true"
                      style={{
                        width: "10px",
                        height: "10px",
                        borderRadius: "50%",
                        background: g.l1_color,
                        flexShrink: 0,
                      }}
                    />
                    <span
                      style={{
                        fontSize: "11px",
                        letterSpacing: "1.5px",
                        textTransform: "uppercase",
                        color: g.l1_color,
                        fontWeight: 600,
                        fontFamily: "ui-monospace, monospace",
                      }}
                    >
                      {g.l1_label}
                    </span>
                    {/* L1 group recipe-count chip removed 2026-05-29 — the
                  family label alone carries enough context; the count
                  was visual noise. */}
                  </div>
                  {g.items.map(({ recipe, row }) => {
                    const isLast = renderedRowIdx === totalRows - 1;
                    renderedRowIdx += 1;
                    return (
                      <RecipeGridRow
                        key={recipe.recipe_id}
                        recipe={recipe}
                        row={row}
                        customCountries={customCountries}
                        hoveredCountry={hoveredCountry}
                        onHoverCountry={onHoverCountry}
                        dimOthersOnHover={dimOthersOnHover}
                        gridTemplate={gridTemplate}
                        isLast={isLast}
                      />
                    );
                  })}
                </div>
              ));
            })()}
          </div>
        </div>
      </div>
      {/* Mobile scroll affordance: a plain CSS-gated hint below the grid (no
        data-obscuring fade, no overflow:hidden that would suppress the iOS
        scrollbar). md:hidden → shown only below 768px, where the matrix
        overflows. CSS-only, matching TopicBoard's hint (no JS re-render). */}
      <p
        className="md:hidden"
        style={{
          margin: "8px 2px 0",
          fontSize: "11px",
          fontFamily: "ui-monospace, monospace",
          color: "var(--qgi-text-dim)",
          textAlign: "center",
        }}
      >
        ← scroll sideways to see all ranks →
      </p>
    </div>
  );
}

function RecipeGridRow({
  recipe,
  row,
  customCountries,
  hoveredCountry,
  onHoverCountry,
  dimOthersOnHover,
  gridTemplate,
  isLast,
}: {
  recipe: RiskBoardRecipeProjection;
  row: RecipeRow;
  customCountries: string[] | null;
  hoveredCountry: string | null;
  onHoverCountry: (name: string | null) => void;
  dimOthersOnHover: boolean;
  gridTemplate: string;
  isLast: boolean;
}) {
  const isQueued = row.display_state === "queued";
  const displayColor = familyColor(recipe.l1_id, recipe.l1_color);

  // V4.1 §1.4 (2026-05-29): the coverage caption ("X of 174 platform
  // countries scored · Y lack coverage…") was self-flagellation noise —
  // removed. hasCoverageData + coverageGap derivations dropped with it.

  // Round-3.5 (2026-05-29): in custom mode the cells aren't the row's
  // top-10; they're derived per-column from the user's selected countries
  // resolved against recipe.scoreByCountry. Missing entries render as
  // "not scored" cells (state="not_scored", score=null).
  //
  // Round-3.5.1 sort (2026-05-29): per founder ask, custom-mode cells rank
  // highest-to-lowest LEFT-to-RIGHT — same convention as the default top-10
  // grid (column #1 = highest = leftmost). Sorting is PER ROW: each recipe
  // ranks the user's selected countries by THAT recipe's own scores.
  // Not-scored cells sit at the far right (effectively negative infinity)
  // so they don't pollute the scored ordering.
  const cellsToRender: BoardCell[] = customCountries
    ? customCountries
        .map((name): BoardCell => {
          const sc = recipe.scoreByCountry[name];
          return typeof sc === "number"
            ? { country: name, score: sc, state: "scored" as const }
            : { country: name, score: null, state: "not_scored" as const };
        })
        .sort((a, b) => (b.score ?? -Infinity) - (a.score ?? -Infinity))
    : row.cells;
  const colCount = cellsToRender.length;

  return (
    <div style={{ borderBottom: isLast ? "none" : "1px solid var(--qgi-border)" }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: gridTemplate,
          background: isQueued ? "rgba(0,0,0,0.18)" : "transparent",
        }}
      >
        <Link
          href={`/trends/${recipe.recipe_id}` as Route}
          style={{ textDecoration: "none", color: "inherit" }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              padding: "10px 12px",
              borderRight: "1px solid var(--qgi-border)",
              borderLeft: `3px solid ${displayColor}`,
              height: "100%",
              opacity: isQueued ? 0.62 : 1,
            }}
          >
            <div
              style={{
                width: "28px",
                height: "28px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: displayColor,
                flexShrink: 0,
              }}
            >
              <RecipeIcon recipeId={recipe.recipe_id} size={18} strokeWidth={1.6} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  fontSize: "12.5px",
                  fontWeight: 600,
                  color: "var(--qgi-text)",
                  lineHeight: 1.2,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {recipe.label}
              </div>
              {/* Per-row "in play" status line removed 2026-05-29 — every
                  row in the visible grid is in play by construction (the
                  status filter is hardcoded scored-only), so the label
                  carried zero signal per-row and added visual repetition
                  down the column. */}
            </div>
          </div>
        </Link>

        {cellsToRender.map((cell, i) => {
          const isHovered = hoveredCountry === cell.country;
          // Dim policy is mode-gated: in custom mode every row shows the
          // same N countries in the same column order so dim-others makes
          // the matched column pop. In default mode each row is its own
          // top-10 (mostly disjoint) so dimming 43/44 rows reads as the
          // page going dark — keep them at full opacity, the highlight
          // alone carries the signal.
          const dimmed = dimOthersOnHover && hoveredCountry !== null && !isHovered;
          return (
            <HeatCell
              key={`${recipe.recipe_id}-${i}-${cell.country}`}
              cell={cell}
              recipeId={recipe.recipe_id}
              familyColor={displayColor}
              isLastCol={i === colCount - 1}
              isQueued={isQueued}
              isHovered={isHovered}
              isDimmed={dimmed}
              onHoverCountry={onHoverCountry}
            />
          );
        })}
      </div>

      {/* 2026-05-31 (founder): the per-row "N countries not scored — view list"
          footer caption was removed. It read as coverage self-flagellation
          between every recipe row; the grid stands on its scored cells. */}
    </div>
  );
}

function HeatCell({
  cell,
  recipeId,
  familyColor: resolvedFamilyColor,
  isLastCol,
  isQueued,
  isHovered,
  isDimmed,
  onHoverCountry,
}: {
  cell: BoardCell;
  recipeId: string;
  familyColor: string;
  isLastCol: boolean;
  isQueued: boolean;
  /** Round-3.5: this cell's country matches the user's hovered country. */
  isHovered?: boolean;
  /** Round-3.5: ANOTHER cell's country is hovered; dim everything else. */
  isDimmed?: boolean;
  onHoverCountry?: (name: string | null) => void;
}) {
  // ── State-specific render branches ─────────────────────────────────────

  // no_walk_yet — recipe is queued; all cells render as placeholder
  if (cell.state === "no_walk_yet" || isQueued) {
    return (
      <div
        style={{
          position: "relative",
          height: "62px",
          padding: "6px 8px",
          borderRight: isLastCol ? "none" : "1px solid var(--qgi-border)",
          background: "transparent",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          cursor: "default",
        }}
        title="Coming soon: trend enters scoring once its evidence base is ready."
        /* V4.1 §4: "not yet tested" → "coming soon" */
      >
        <div
          style={{
            fontSize: "11px",
            color: "var(--qgi-text-dim)",
            fontWeight: 500,
            lineHeight: 1.2,
          }}
        >
          coming soon
        </div>
        <span
          style={{
            fontSize: "14px",
            fontWeight: 600,
            fontFamily: "ui-monospace, monospace",
            color: "var(--qgi-text-dim)",
            lineHeight: 1,
          }}
        >
          –
        </span>
      </div>
    );
  }

  // not_scored — recipe IS walked, this country lacks indicator coverage.
  // Honesty per R&D reply §Q7: hatched pattern + "not scored" copy, NEVER a low rank.
  if (cell.state === "not_scored") {
    return (
      <div
        onMouseEnter={onHoverCountry ? () => onHoverCountry(cell.country) : undefined}
        onMouseLeave={onHoverCountry ? () => onHoverCountry(null) : undefined}
        style={{
          position: "relative",
          height: "62px",
          padding: "6px 8px",
          borderRight: isLastCol ? "none" : "1px solid var(--qgi-border)",
          background:
            "repeating-linear-gradient(45deg, rgba(122,143,160,0.05) 0 4px, transparent 4px 8px)",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          cursor: "help",
          outline: isHovered ? `2px solid ${resolvedFamilyColor}` : "none",
          outlineOffset: isHovered ? "-2px" : 0,
          opacity: isDimmed ? 0.32 : 1,
          transition: "opacity 120ms ease-out",
        }}
        title={`${cell.country} · not scored: country lacks indicator coverage for this trend, not the same as a low score.`}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "5px",
            fontSize: "11px",
            color: "var(--qgi-text-dim)",
            fontWeight: 500,
            lineHeight: 1.2,
            overflow: "hidden",
            minWidth: 0,
          }}
        >
          <FlagImg
            emoji={flagFor(cell.country)}
            name={cell.country}
            width={14}
            radius={2}
          />
          <span
            style={{
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {cell.country}
          </span>
        </div>
        <span
          style={{
            fontSize: "10px",
            letterSpacing: "0.6px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            textTransform: "uppercase",
          }}
        >
          not scored
        </span>
      </div>
    );
  }

  // ── Scored cell — normal heatmap branch ────────────────────────────────
  const score = cell.score as number;
  const intensity = Math.max(0, Math.min(1, (score - 40) / 60));
  const alpha = 0.1 + intensity * 0.55;
  // Round-3.6 (2026-05-29) — drop HIGH / MODERATE / LOW bins. The number
  // alone (now a percentage) carries the confidence reading; color + glow
  // do the categorical work the bins used to do.
  //
  // Round-3.6.1 (2026-05-29) — gradient endpoint is WHITE, not the family
  // color, because the cell background is already a family-color gradient.
  // The number lerps MUTED_GRAY → WHITE so high-confidence percentages
  // pop OFF the colored background instead of dissolving into it. The
  // glow halo is white too, so the number reads as illuminated.
  const cT = confidenceT(score);
  const confidenceColor = lerpHexToRgb(MUTED_GRAY, "#FFFFFF", cT);
  const confidenceGlowShadow = confidenceGlow("#FFFFFF", cT);
  const pct = Math.round(score);

  // A scored cell is a (country x recipe) intersection — link to the match
  // page ("how this country is tracing this recipe"). Fall back to the recipe
  // page when the country name has no ISO mapping.
  const cellIso2 = iso2For(cell.country);
  const cellHref =
    cellIso2 && /^[a-z]{2}$/.test(cellIso2)
      ? `/trends/${recipeId}/countries/${cellIso2}`
      : `/trends/${recipeId}`;

  return (
    <Link
      href={cellHref as Route}
      onMouseEnter={onHoverCountry ? () => onHoverCountry(cell.country) : undefined}
      onMouseLeave={onHoverCountry ? () => onHoverCountry(null) : undefined}
      style={{ textDecoration: "none", color: "inherit", display: "block" }}
    >
      <div
        style={{
          position: "relative",
          height: "62px",
          padding: "6px 8px",
          borderRight: isLastCol ? "none" : "1px solid var(--qgi-border)",
          background: `linear-gradient(90deg, ${hexToRgba(resolvedFamilyColor, alpha)} 0%, ${hexToRgba(resolvedFamilyColor, alpha * 0.4)} 100%)`,
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          cursor: "pointer",
          outline: isHovered ? `2px solid ${resolvedFamilyColor}` : "none",
          outlineOffset: isHovered ? "-2px" : 0,
          opacity: isDimmed ? 0.32 : 1,
          transition: "opacity 120ms ease-out, outline-color 120ms",
        }}
        title={`${cell.country} · ${pct}% confidence — this country's recent path has been this close to the trend's canonical pre-event shape.`}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "5px",
            fontSize: "11px",
            color: "var(--qgi-text)",
            fontWeight: isHovered ? 700 : 500,
            lineHeight: 1.2,
            overflow: "hidden",
            minWidth: 0,
          }}
        >
          <FlagImg
            emoji={flagFor(cell.country)}
            name={cell.country}
            width={14}
            radius={2}
          />
          <span
            style={{
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {cell.country}
          </span>
        </div>
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            alignItems: "baseline",
          }}
        >
          <span
            style={{
              fontSize: "16px",
              fontWeight: 700,
              fontFamily: "ui-monospace, monospace",
              color: confidenceColor,
              letterSpacing: "-0.5px",
              lineHeight: 1,
              textShadow: confidenceGlowShadow || undefined,
              transition: "text-shadow 180ms ease-out, color 180ms",
            }}
          >
            {pct}%
          </span>
        </div>
      </div>
    </Link>
  );
}

function hexToRgba(hex: string, alpha: number): string {
  let h = hex.replace("#", "");
  if (h.length === 3)
    h = h
      .split("")
      .map((c) => c + c)
      .join("");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/* ────────────────────────────────────────────────────────────────────────── */
/* CountryMultiPicker — up to 10 country chips + typeahead dropdown          */
/* ────────────────────────────────────────────────────────────────────────── */

function CountryMultiPicker({
  selected,
  suggestions,
  query,
  onQueryChange,
  onAdd,
  onRemove,
}: {
  selected: string[];
  suggestions: string[];
  query: string;
  onQueryChange: (q: string) => void;
  onAdd: (name: string) => void;
  onRemove: (name: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const atCap = selected.length >= MAX_SELECTED;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "8px",
        padding: "5px 10px",
        background: "var(--qgi-bg)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "4px",
        minWidth: "260px",
        flex: "0 1 520px",
        position: "relative",
        flexWrap: "wrap",
      }}
    >
      <Search size={13} strokeWidth={1.8} color="var(--qgi-text-dim)" />
      {/* Selected chips */}
      {selected.map((name) => (
        <span
          key={name}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "4px",
            padding: "2px 4px 2px 6px",
            background: "var(--qgi-surface)",
            border: "1px solid var(--qgi-border)",
            borderRadius: "3px",
            fontSize: "11px",
            color: "var(--qgi-text)",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          <FlagImg emoji={flagFor(name)} name={name} width={12} radius={2} />
          {name}
          <button
            type="button"
            onClick={() => onRemove(name)}
            aria-label={`Remove ${name}`}
            style={{
              background: "transparent",
              border: "none",
              color: "var(--qgi-text-dim)",
              cursor: "pointer",
              padding: 0,
              display: "flex",
              marginLeft: "2px",
            }}
          >
            <X size={10} strokeWidth={2.2} />
          </button>
        </span>
      ))}
      <input
        type="text"
        value={query}
        onChange={(e) => {
          onQueryChange(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={
          atCap
            ? `Max ${MAX_SELECTED} countries`
            : selected.length === 0
              ? "Select up to 10 countries..."
              : `Add country (${MAX_SELECTED - selected.length} left)`
        }
        aria-label="Country picker"
        disabled={atCap}
        style={{
          flex: 1,
          background: "transparent",
          border: "none",
          outline: "none",
          color: "var(--qgi-text)",
          fontFamily: "ui-monospace, monospace",
          fontSize: "11.5px",
          minWidth: "120px",
        }}
      />
      {open && !atCap && suggestions.length > 0 && (
        <div
          role="listbox"
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: "calc(100% + 4px)",
            background: "var(--qgi-surface)",
            border: "1px solid var(--qgi-border)",
            borderRadius: "4px",
            boxShadow: "0 8px 24px rgba(0,0,0,0.45)",
            zIndex: 50,
            maxHeight: "240px",
            overflowY: "auto",
          }}
        >
          {suggestions.map((name) => (
            <button
              key={name}
              type="button"
              role="option"
              aria-selected={false}
              onMouseDown={(e) => {
                // mouseDown beats the input's onBlur so the click registers.
                e.preventDefault();
                onAdd(name);
              }}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                width: "100%",
                padding: "7px 12px",
                background: "transparent",
                border: "none",
                color: "var(--qgi-text)",
                fontFamily: "ui-monospace, monospace",
                fontSize: "11.5px",
                cursor: "pointer",
                textAlign: "left",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = "var(--qgi-bg)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = "transparent";
              }}
            >
              <FlagImg emoji={flagFor(name)} name={name} width={14} radius={2} />
              {name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
