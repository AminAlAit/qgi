/**
 * Canonical country-pair key — shared dedupe helper for pattern rows.
 *
 * Pattern rows in `ranking.json` carry `country_a` / `country_b` (name
 * strings) and `country_a_id` / `country_b_id` (numeric WB IDs). For
 * dedupe to be stable across surfaces, two requirements must hold:
 *
 *   1. **Order-insensitivity.** A pattern between Paraguay and South
 *      Korea should produce the SAME key regardless of which is
 *      `country_a` vs `country_b`. Otherwise (X→Y) and (Y→X) count as
 *      different "unique pairs" and the count balloons.
 *
 *   2. **Numeric padding.** Compare 6-digit-padded numeric strings,
 *      not lex-ordered raw values. Per T2 #295 + QA P1-4 fix
 *      (2026-04-19): bare `String(id)` produces `"10" < "2"`
 *      (lex-order on first char), which orders pairs differently from
 *      any numeric-comparing caller.
 *
 * Three callsites in the codebase previously rolled their own variant
 * of this logic (QA-v4 review on PR #100, 2026-05-17 — Findings
 * 2.2 and 2.3). One of them was unpadded and a fourth (the patterns
 * page) had an unsorted name-string key. The divergence produced the
 * #777 "9 pairs vs 4 pairs" mismatch Marcus flagged in persona-test
 * Round 3.
 *
 * Use `canonicalPairKey(row)` from every dedupe loop. If you find
 * yourself writing `${row.country_a}|${row.country_b}` or open-coding
 * a `padStart(6, "0")` here, stop and call this instead.
 */

/** Row shape every caller agrees on (country_a/b are name strings;
 *  *_id are WB numeric IDs — strings in the bake JSON). */
export interface CanonicalPairRow {
  country_a_id?: string | number;
  country_b_id?: string | number;
  country_a: string;
  country_b: string;
}

/** Pad a numeric ID (or name fallback) to 6 digits for lex-safe sort. */
export function padKey(value: string | number | undefined, fallback: string): string {
  const n = Number(value);
  return Number.isFinite(n) ? String(n).padStart(6, "0") : String(value ?? fallback);
}

/**
 * Compute the canonical (order-insensitive, numeric-padded) pair key
 * for a pattern row. Use as the dedupe-set key.
 */
export function canonicalPairKey(row: CanonicalPairRow): string {
  const a = padKey(row.country_a_id, row.country_a);
  const b = padKey(row.country_b_id, row.country_b);
  return a < b ? `${a}|${b}` : `${b}|${a}`;
}
