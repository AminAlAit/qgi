/**
 * country-families — derive a country's distinct lit L1 families, ordered
 * by the best (highest) recipe score in each family. Shared by the atlas
 * card, the country-page header, and the panels so "dominant family" means
 * the same thing everywhere.
 */
import { familyColor } from "@/lib/te-mock/l1-families";
import type { CountryV4 } from "@/lib/te-mock/countries-v4-data";

export interface FamilyRank {
  id: string;
  label: string;
  color: string;
  /** Best recipe score within this family for the country. */
  best: number;
}

export function familiesByBestScore(country: CountryV4): FamilyRank[] {
  const map = new Map<string, FamilyRank>();
  for (const r of country.top_recipes) {
    const cur = map.get(r.l1_id);
    if (!cur || r.score > cur.best) {
      map.set(r.l1_id, {
        id: r.l1_id,
        label: r.l1_label,
        color: familyColor(r.l1_id, r.l1_color),
        best: r.score,
      });
    }
  }
  return [...map.values()].sort((a, b) => b.best - a.best);
}

/** User-facing label + tone for a recipe's validation status.
 *
 *  V4.1 round-3 amendment (2026-05-29) — two-bucket collapse:
 *
 *  Founder ratified: drop "Validated" and "Prior version" from the
 *  audience surface. The high-confidence framing (when a recipe LOCKs)
 *  will be expressed differently in a future iteration — not via a
 *  third status chip. For now every active-rotation recipe (LOCK,
 *  directional, experimental, in_progress, cascade-era live_legacy)
 *  reads as **"in play"** (lowercase). Pre-walk / queued / hold reads
 *  as **"Coming soon"**.
 *
 *  Mapping:
 *   - graduated / LOCK / walked_no_graduation / in_progress / live_legacy
 *     → "in play"  (neutral tone, family-color pulsing dot)
 *   - queued / hold
 *     → "Coming soon"  (neutral tone, no dot)
 *
 *  The `deployed` and `failed` tone codes are retained on the type so
 *  any legacy caller still compiles, but no path returns them now.
 */
export type StatusTone = "deployed" | "neutral" | "failed";

export function statusLabel(status: string): { label: string; tone: StatusTone } {
  switch (status) {
    case "queued":
    case "hold":
      return { label: "Coming soon", tone: "neutral" };
    case "graduated":
    case "walked_no_graduation":
    case "in_progress":
    case "in_play": // pipeline emits this V4.1 audience-facing label directly
    case "live_legacy":
      return { label: "in play", tone: "neutral" };
    default:
      return { label: "Coming soon", tone: "neutral" };
  }
}
