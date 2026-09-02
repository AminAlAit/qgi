/**
 * analogueHref — the canonical URL for an individual analogue comparison page.
 *
 * Standalone (zero heavy imports) so it is safe to import from CLIENT-bundled
 * components (e.g. AnalogCard, reached through the "use client" CountryPicker)
 * without dragging the server-only indicator-panels JSON into the client bundle.
 *
 * Key shape: `/analogues/{subjectIso2}-{analogueIso2}-{year}` — the same trio the
 * resolver in `analogue-pair.ts` parses. Returns null when any part is missing,
 * so callers can fall back to a non-clickable render.
 */
export function analogueHref(
  subjectIso2: string | null | undefined,
  analogueIso2: string | null | undefined,
  year: number | null | undefined
): string | null {
  if (!subjectIso2 || !analogueIso2 || !year) return null;
  return `/analogues/${subjectIso2.toLowerCase()}-${analogueIso2.toLowerCase()}-${year}`;
}
