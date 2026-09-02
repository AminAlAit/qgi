/**
 * Pipeline-version display formatter.
 *
 * The Athena bake script writes a `pipeline_version` string into
 * `recipes-aggregated.json` (and similar baked JSONs) that can carry
 * internal-state suffixes — `-dev`, `-baked`, `-rc`, `-beta`, `-alpha` —
 * leaked from CI / staging cuts. Those suffixes are engineer metadata,
 * not user-facing version semantics.
 *
 * Marcus (Siemens VP, persona-test Round 3 2026-05-17): "vV2.0-dev"
 * rendered in production "looks like a developer tag that escaped into
 * production. That alone makes a CFO nervous." Closes #776.
 *
 * Single source-of-truth helper applied to every render of
 * `pipeline_version` across the frontend. Centralizing the regex
 * eliminates the divergence-over-time risk Opus flagged on PR #100
 * (different callsites drifting on which suffixes to strip).
 *
 * Behavior:
 *   "V2.0-dev"       → "v2.0"
 *   "v2.0-baked"     → "v2.0"
 *   "v2.0-rc"        → "v2.0"
 *   "v2.0-dev-tag"   → "v2.0"    (anchored-to-end strip removes the
 *                                  whole `-dev-tag` tail, not just
 *                                  the middle `-dev`)
 *   "v2.0.1"         → "v2.0.1"  (no suffix; pass-through)
 *   "v2.0-rc1"       → "v2.0-rc1" (rc1 has a digit — `\b` between
 *                                  `c` and `1` is not a word boundary
 *                                  in /[a-z]\d/, so `rc1` is not
 *                                  matched. Intentional — `rc1` could
 *                                  be a meaningful release-candidate
 *                                  number worth surfacing.)
 *   "2.0"            → "v2.0"    (prepended `v` for display
 *                                  consistency; the bake writes the
 *                                  bare version sometimes.)
 *   ""               → "v"       (degenerate, non-crashing)
 *
 * Bake JSON is intentionally NOT patched at source — the raw value
 * stays available for diagnostics, only the render-side display is
 * sanitized.
 */
const PIPELINE_STATE_SUFFIX_REGEX = /-(?:dev|baked|rc|beta|alpha)\b.*$/i;

export function formatPipelineVersion(raw: string): string {
  const stripped = raw.replace(/^v/i, "").replace(PIPELINE_STATE_SUFFIX_REGEX, "");
  return `v${stripped}`;
}
