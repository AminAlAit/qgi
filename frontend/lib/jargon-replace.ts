/**
 * Mechanical jargon-to-plain-English rewriter for buyer-facing prose.
 *
 * Used by `lib/buyer-view.ts` to clean methodology vocabulary out of
 * bake-script prose fields (`mechanism_narrative`, `anchor_ahi_reason`,
 * `buyer_disclosure_recommendation`, `zero_positive_cohort_flag`,
 * `open_followups[]`) before they reach the JSX render layer.
 *
 * Order matters: longest / most-specific patterns first so bare-acronym
 * patterns don't preempt context-bearing ones. Final pass collapses
 * whitespace artifacts from drops.
 *
 * Tested via `lib/__tests__/jargon-replace.test.ts` AND end-to-end via
 * `lib/__tests__/buyer-view.test.ts`, which runs the live bake output
 * through this pipeline and asserts the polish-scanner finds zero hits.
 *
 * Coverage targets all jargon terms in `scripts/polish_leak_scan.py`
 * `JARGON_TERMS`. When a new internal acronym appears in bake prose,
 * add it here AND to the scanner's JARGON_TERMS so the CI gate catches
 * regressions.
 *
 * Long-term plan: the bake script (qgi-ml ticket #683) should write
 * buyer-clean prose directly, making this module redundant. Until then
 * this is the frontend's content-architecture quarantine.
 */

/**
 * Each entry is [pattern, replacement] applied in order. Final entries
 * are whitespace/punctuation cleanup.
 *
 * Important: Don't reorder casually. Tests will catch most regressions
 * but some interactions are subtle (e.g. `LOCO AUC` must come BEFORE
 * `LOCO` and `AUC` as bare-word patterns).
 */
const JARGON_REPLACEMENTS: ReadonlyArray<readonly [RegExp, string]> = [
  // ============================================================
  // 1. Drop internal citations and parenthetical noise (longest)
  // ============================================================
  // "(post-KI-2, 2026-05-11)" / "(post-KI-2)"
  [/\s*\(post-KI-\d+(?:,\s*\d{4}-\d{2}-\d{2})?\)/g, ""],
  // "(KI-2)" — bare
  [/\s*\(KI-\d+\)/g, ""],
  // "(F-H-3)" — bare
  [/\s*\(F-H-\d+\)/g, ""],
  // "per Sard Majles S-First (2026-05-01)" — drop the attribution +
  // optional dated parenthetical. Conservative: stops at the closing
  // paren, doesn't eat following prose.
  [
    /\s*\bper\s+(?:Asas|Sard|Ihsa|Bina|Tasweeq|Tijara)\s+Majles(?:\s+[A-Z]-[A-Za-z]+)?(?:\s*\([^)]*\))?/g,
    "",
  ],
  // "Per Stage 5 §F-H-3 buyer-disclosure rule" → drop the cite, keep
  // the rule reference.
  [
    /\s*Per\s+Stage\s+\d+\s+§F-H-\d+\s+buyer-disclosure\s+rule/g,
    "Per buyer-disclosure rule",
  ],
  // "F-H-3 rule" / "F-H-3 amendment" — drop the citation
  [/\s*\bF-H-\d+\s+(?:rule|amendment|pre-?reg)\b/g, ""],
  // "KI-2 amendment" / "KI-2 (something)" — drop
  [/\s*\bKI-\d+\s+amendment\b/g, ""],
  // Bare F-H-N citations remaining inline
  [/\s*\bF-H-\d+\b/g, ""],
  // Bare KI-N citations
  [/\s*\bKI-\d+\b/g, ""],

  // ============================================================
  // 2. Markdown links to internal docs → unlink (keep label text)
  // ============================================================
  // [label](../internal/...) / [label](../anything-not-http)
  [/\[([^\]]+)\]\(\.\.\/[^)]+\)/g, "$1"],
  // [label](internal/...)
  [/\[([^\]]+)\]\(internal\/[^)]+\)/g, "$1"],
  // [label](docs/specs/internal/...) (with org-prefix)
  [/\[([^\]]+)\]\((?:docs-specs\/)?internal\/[^)]+\)/g, "$1"],

  // ============================================================
  // 3. Multi-word jargon (longest before bare-word patterns)
  // ============================================================
  [/\bhybrid\s+D2\/D5\b/gi, "hybrid prediction"],
  [/\bn_pos_LOCO\b/g, "held-out positives"],
  [/\bn_pos_test\b/g, "test-window positives"],
  [/\bn_pos\s*=\s*/g, "positives = "],
  [/\bcohort_ece\b/g, "tier calibration"],
  [/\bf_rule_anomaly\b/g, "in-sample fit anomaly"],
  [/\bdispatch_sha\b/g, ""],
  [/\bbootstrap\s+CI\b/g, "uncertainty range"],

  // ============================================================
  // 4. Architecture terms with context
  // ============================================================
  [/\bD2\s+(?:multi-task\s+)?(?:architecture|head|backbone)/g, "level-features model"],
  [/\bD5\s+(?:trajectory\s+)?(?:architecture|head|backbone)/g, "trend-features model"],
  // Bare "D2" / "D5" in remaining contexts (e.g. "Under D2, this recipe
  // was FALSIFIED" or "the D5 head was preserved"). Word-boundary-aware
  // so "ABCD2" or "D24" don't match.
  [/\bD2\b(?!\.)/g, "level-features model"],
  [/\bD5\b(?!\.)/g, "trend-features model"],
  // Apposition residue from the bare-D2/D5 rewrite: "D5 trajectory features"
  // first becomes "trend-features model trajectory features" via the bare-D5
  // replacement; the appositive duplicates the model name. The replacement
  // ALSO fixes subject-verb agreement: "trajectory features were" (plural
  // subject) becomes "trend-features model was" (singular subject + verb).
  // 4-persona walkthrough Phase A2 finding (Ingrid, Yuki, Sipho, Elif).
  [/\btrend-features model trajectory features\s+were\b/g, "trend-features model was"],
  [/\btrend-features model trajectory features\s+are\b/g, "trend-features model is"],
  [/\btrend-features model trajectory features\b/g, "trend-features model"],
  [/\blevel-features model level features\s+were\b/g, "level-features model was"],
  [/\blevel-features model level features\s+are\b/g, "level-features model is"],
  [/\blevel-features model level features\b/g, "level-features model"],
  // Article-injection helper for post-rewrite grammar: bare "level-features
  // model" / "trend-features model" needs a definite article when used as a
  // subject (only when preceded by sentence-connective / preposition). Two
  // passes — first the connectives that put the model in subject position,
  // then bare prepositions.
  [
    /\b(so|and|but|then|then,|which is why|why)\s+(level-features model|trend-features model)\b(?!\s+(?:was|is|were|are|baseline|rescue|trajectory))/g,
    "$1 the $2",
  ],
  [
    /\b(Under|under|With|with|By|by|For|for|From|from)\s+(level-features model|trend-features model)\b/g,
    "$1 the $2",
  ],
  [
    /\b(so|and|but|then|then,)\s+(level-features model|trend-features model)\s+(is|was)\b/g,
    "$1 the $2 $3",
  ],

  // ============================================================
  // 5. Composite metric names (must come BEFORE bare AUC)
  // ============================================================
  [/\bLOCO\s+AUC\b/g, "out-of-country score"],
  [/\bF[12]\s+AUC\b/g, "in-sample score"],
  [/\bF[12]\s+ECE\b/g, "calibration error"],
  [/\bin-sample\s+F[12]\b/gi, "in-sample"],

  // ============================================================
  // 6. Single acronyms (bare-word — runs after composites)
  // ============================================================
  [/\bLOCO\b/g, "out-of-country"],
  [/\bAUC\b/g, "score"],
  [/\bECE\b/g, "calibration error"],
  [/\bAHI\b/g, "anchor stability"],
  [/\bRCI\b/g, "recipe confidence"],
  [/\bPPS\b/g, "score"],
  [/\bSCDI\b/g, "cross-country indicator"],
  [/\bRRF\b/g, "rank-fusion"],
  [/\bMNAR\b/g, "missing-not-at-random"],

  // ============================================================
  // 7. Internal status / process words
  // ============================================================
  [/\bLOCKed\b/g, "validated"],
  // Bare "LOCK" (e.g. "the flagship LOCK") + plural "LOCKs" — 4-persona
  // Phase A2 finding. `(?!ed)` so we don't collide with `LOCKed` (already
  // handled above). Plural form `LOCKs` won't match `\bLOCK\b` (the trailing
  // `s` joins via word-char boundary), so handle plural separately.
  [/\bLOCKs\b/g, "validated recipes"],
  [/\bLOCK\b(?!ed)/g, "validated recipe"],
  [/\bFALSIFIED\b/g, "removed from production"],
  [/\bDEFERRED\b/g, "planned"],
  [/\bLEAK\b/g, ""],

  // ============================================================
  // 8. Method / persona / process names (drop)
  // ============================================================
  // Drop Majles persona-group names entirely.
  [/\b(?:Asas|Sard|Ihsa|Bina|Tasweeq|Tijara)\s+Majles\s+[A-Z]-[A-Za-z]+\b/g, ""],
  [/\b(?:Asas|Sard|Ihsa|Bina|Tasweeq|Tijara)\s+Majles\b/g, ""],
  [/\b(?:Asas|Sard|Ihsa|Bina|Tasweeq|Tijara)\b/g, ""],
  [/\bMajles\s+cycle\b/g, "review cycle"],
  [/\bMajles\b/g, ""],
  [/\bLakatosian\b/g, ""],
  [/\bauditioner\b/g, ""],
  [/\bDeepHit\b/g, "survival model"],
  [/\bisotonic\s+(?:regression|calibration)\b/g, "monotone calibration"],
  [/\bisotonic\b/g, ""],
  [/\bpre-reg-anchored\b/g, "methodology-locked"],
  [/\bpre-reg\b/g, "methodology lock"],

  // ============================================================
  // 9. Whitespace and punctuation cleanup (final pass)
  // ============================================================
  // Strip leading whitespace before punctuation
  [/\s+([.,;:!?])/g, "$1"],
  // Strip empty parentheticals from drops: "(  )" / "()"
  [/\(\s*\)/g, ""],
  [/\s*\([\s,;]*\)/g, ""],
  // Collapse "—  " (em-dash + multiple spaces from drops)
  [/—\s+([,.;:!?])/g, "—$1"],
  // Collapse "  " (multiple spaces) to single space
  [/[ \t]{2,}/g, " "],
  // Trim trailing whitespace per line
  [/[ \t]+$/gm, ""],
  // Strip standalone dangling commas from removals: ", ," → ","
  [/,\s*,/g, ","],
  // Strip leading commas at line/sentence start after drops
  [/(^|[.!?]\s+),\s*/g, "$1"],
];

/**
 * Apply the jargon replacement pipeline to a prose string.
 *
 * @param prose Input text from a bake-output field
 * @returns Buyer-clean text
 *
 * Examples:
 *   replaceJargonInProse("LOCO AUC 0.722")
 *     → "out-of-country score 0.722"
 *
 *   replaceJargonInProse("Per Stage 5 §F-H-3 buyer-disclosure rule")
 *     → "Per buyer-disclosure rule"
 *
 *   replaceJargonInProse("13 LOCKed recipes (post-KI-2, 2026-05-11)")
 *     → "13 validated recipes"
 *
 *   replaceJargonInProse("See [per-recipe AHI analysis](../internal/x.md)")
 *     → "See per-recipe anchor stability analysis"
 */
export function replaceJargonInProse(prose: string): string {
  if (!prose) return prose;
  let result = prose;
  for (const [pattern, replacement] of JARGON_REPLACEMENTS) {
    result = result.replace(pattern, replacement);
  }
  return result.trim();
}
