import type { PatternRow } from "@/lib/types";

/**
 * Cross-family Pattern-window tier vocabulary — S-win/M-win/L-win/
 * XL-win. Source of truth lives here (not in the page or the client
 * component) so `lib/` can stand alone and downstream consumers don't
 * import from app-router or `"use client"` modules.
 */
export type PatternWindowTier = "S-win" | "M-win" | "L-win" | "XL-win";

/** Valid sort columns — matches `PatternsMergedListClient` SortColumn union. */
export type PatternsSortColumn =
  | "pattern_power_score"
  | "avg_correlation"
  | "pattern_length"
  | "window_tier";

export type PatternsSortDir = "asc" | "desc";

/**
 * #781 + #786 — initial filter state seeded from URL on the server. The
 * client component uses these for `useState` initializers.
 */
export interface PatternsInitialFilters {
  search: string;
  /** Country names — seeded from CSV `country=`, repeated keys
   *  `?country=X&country=Y`, numeric `country_a`/`country_b` mapped
   *  to names server-side, and ISO alpha_2 codes (when the alpha_2
   *  map is provided). */
  countryFilter: string[];
  tierFilter: PatternWindowTier[];
  /** #786(d) — initial sort column from URL `?sort=`. Falls back to
   *  the client component's default when undefined. */
  sortCol?: PatternsSortColumn;
  sortDir?: PatternsSortDir;
}

const WINDOW_TIERS: ReadonlySet<PatternWindowTier> = new Set([
  "S-win",
  "M-win",
  "L-win",
  "XL-win",
]);

const SORT_COLUMNS: ReadonlySet<PatternsSortColumn> = new Set([
  "pattern_power_score",
  "avg_correlation",
  "pattern_length",
  "window_tier",
]);

/**
 * Legacy sort-key aliases. Multiple precedent + country page cross-refs
 * (e.g., `MergedDetailFooter.tsx:42`, `PrecedentMergedDossier.tsx:478`,
 * `CountryMergedDetail.tsx:385`) construct `?sort=loco_auc` — but
 * `loco_auc` is a recipe-level metric, not a per-pattern column.
 * Closest pattern equivalent is `pattern_power_score`. Map for back-
 * compat instead of silently dropping. Caught by Mei-Lin + Roberto in
 * persona-test Round 5 (2026-05-17).
 */
const SORT_ALIASES: Readonly<Record<string, PatternsSortColumn>> = {
  loco_auc: "pattern_power_score",
};

const SORT_DIRS: ReadonlySet<PatternsSortDir> = new Set(["asc", "desc"]);

export type PatternsSearchParams = {
  q?: string | string[];
  country?: string | string[];
  country_a?: string | string[];
  country_b?: string | string[];
  tier?: string | string[];
  /** #786(d) — sort column name. May be one of `PatternsSortColumn` or
   *  a legacy alias from `SORT_ALIASES`. */
  sort?: string | string[];
  dir?: string | string[];
};

function firstOf(v: string | string[] | undefined): string | undefined {
  if (Array.isArray(v)) return v[0];
  return v;
}

/**
 * #786(c) — handle both `?country=X,Y` (CSV) and `?country=X&country=Y`
 * (repeated keys, the RFC-compliant form `URLSearchParams.getAll()`
 * produces). Mei-Lin (World Bank R5) hit this: typed URL with two
 * repeated keys collapsed to one chip via the old `firstOf` path.
 */
function flattenCsvOrRepeated(v: string | string[] | undefined): string[] {
  if (!v) return [];
  const arr = Array.isArray(v) ? v : [v];
  const out: string[] = [];
  for (const raw of arr) {
    for (const piece of raw.split(",")) {
      const t = piece.trim();
      if (t) out.push(t);
    }
  }
  return out;
}

/**
 * #786(b) — accept ISO alpha_2 codes (e.g., `TR`) on `country_a`/
 * `country_b`. The patterns row data carries WB numeric IDs + name
 * strings, NOT alpha_2 codes; so the page passes an optional
 * alpha_2 → name map (sourced from `loadCountryRisks().countries`).
 * Karl (Eurasia R5) shared URLs in ISO form with colleagues; the
 * filter silently no-op'd.
 */
function looksLikeAlpha2(s: string): boolean {
  return /^[A-Za-z]{2}$/.test(s);
}

export function resolvePatternsInitialFilters(
  params: PatternsSearchParams,
  rows: ReadonlyArray<
    Pick<PatternRow, "country_a" | "country_b" | "country_a_id" | "country_b_id">
  >,
  /** #786(b) — optional alpha_2 → country-name map for ISO-code
   *  resolution. When omitted, `country_a=TR`-style URLs silently
   *  fall back to the numeric-ID lookup (which won't match a 2-letter
   *  code) — same behavior as pre-#786. */
  alpha2ToName?: ReadonlyMap<string, string>
): PatternsInitialFilters {
  const search = firstOf(params.q) ?? "";

  const countryFilter = new Set<string>();

  // (c) — CSV + repeated keys for the `country` param
  for (const name of flattenCsvOrRepeated(params.country)) {
    countryFilter.add(name);
  }

  // (b) — string OR numeric `country_a` / `country_b`
  const caRaw = firstOf(params.country_a);
  const cbRaw = firstOf(params.country_b);
  for (const idOrCode of [caRaw, cbRaw]) {
    if (!idOrCode) continue;
    // ISO alpha_2 → name (when map available)
    if (alpha2ToName && looksLikeAlpha2(idOrCode)) {
      const name = alpha2ToName.get(idOrCode.toUpperCase());
      if (name) {
        countryFilter.add(name);
        continue;
      }
    }
    // Numeric WB ID → look up via rows
    for (const r of rows) {
      const aId = r.country_a_id != null ? String(r.country_a_id) : "";
      const bId = r.country_b_id != null ? String(r.country_b_id) : "";
      if (aId === idOrCode || bId === idOrCode) {
        countryFilter.add(aId === idOrCode ? r.country_a : r.country_b);
        break;
      }
    }
  }

  const tierFilter: PatternWindowTier[] = [];
  for (const t of flattenCsvOrRepeated(params.tier)) {
    if (WINDOW_TIERS.has(t as PatternWindowTier)) {
      tierFilter.push(t as PatternWindowTier);
    }
  }

  // (d) — sort column + dir from URL with alias support
  let sortCol: PatternsSortColumn | undefined;
  const sortRaw = firstOf(params.sort);
  if (sortRaw) {
    if (SORT_COLUMNS.has(sortRaw as PatternsSortColumn)) {
      sortCol = sortRaw as PatternsSortColumn;
    } else if (sortRaw in SORT_ALIASES) {
      sortCol = SORT_ALIASES[sortRaw];
    }
  }
  let sortDir: PatternsSortDir | undefined;
  const dirRaw = firstOf(params.dir);
  if (dirRaw && SORT_DIRS.has(dirRaw as PatternsSortDir)) {
    sortDir = dirRaw as PatternsSortDir;
  }

  return {
    search,
    countryFilter: Array.from(countryFilter),
    tierFilter,
    sortCol,
    sortDir,
  };
}
