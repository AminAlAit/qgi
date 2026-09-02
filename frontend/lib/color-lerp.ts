/**
 * Shared color-lerp helpers for the Risk Board cell scores + recipe card
 * Confidence badge.
 *
 * The visual contract is the same in both places:
 *   - At 50% (coin flip / lowest meaningful) the number reads in MUTED_GRAY,
 *     matching `var(--qgi-text-muted)`, so a low-confidence cell sits
 *     quietly on the page.
 *   - At 100% (asymptote) the number reads in full family color.
 *   - Between, RGB is linearly interpolated — the gradient IS the meaning.
 *   - From ~60% onward a soft glow blooms behind the number, scaling up to
 *     a strong halo at 100%. High-confidence numbers visually "light up"
 *     so the eye is drawn to them without reading every digit.
 */

/** Matches var(--qgi-text-muted) — the muted-gray endpoint at 50%. */
export const MUTED_GRAY = "#9ab0c4";

interface Rgb {
  r: number;
  g: number;
  b: number;
}

function parseHex(hex: string): Rgb {
  return {
    r: parseInt(hex.slice(1, 3), 16),
    g: parseInt(hex.slice(3, 5), 16),
    b: parseInt(hex.slice(5, 7), 16),
  };
}

/** Clamp `(score - 50) / 50` into [0, 1]. score = 50 → 0, score = 100 → 1. */
export function confidenceT(score: number): number {
  return Math.max(0, Math.min(1, (score - 50) / 50));
}

/** Linear interpolation between two `#RRGGBB` hex colors. */
export function lerpHexToRgb(startHex: string, endHex: string, t: number): string {
  const s = parseHex(startHex);
  const e = parseHex(endHex);
  const mix = (a: number, b: number) => Math.round(a + (b - a) * t);
  return `rgb(${mix(s.r, e.r)}, ${mix(s.g, e.g)}, ${mix(s.b, e.b)})`;
}

/**
 * Build a text-shadow string that glows in `endHex` (the family color),
 * scaling with t. Returns an empty string below a soft threshold so weak
 * scores don't carry any glow at all — the halo earns its space.
 *
 * Round-3.6.3 (2026-05-29) — SOFT variant. Used by the Risk Board cells
 * and the Dashboard TopPairsStrip, which sit on bright/dense backgrounds.
 *   t = 0    → no glow
 *   t = 0.25 → no glow (lifted threshold)
 *   t = 0.5  → tight 2px @ 0.23 + 5px halo @ 0.13
 *   t = 1.0  → tight 2px @ 0.34 + 8px halo @ 0.20
 */
export function confidenceGlow(endHex: string, t: number): string {
  if (t < 0.25) return "";
  const e = parseHex(endHex);
  const rgb = `${e.r}, ${e.g}, ${e.b}`;
  const innerBlur = Math.round(1 + t * 1);
  const outerBlur = Math.round(2 + t * 6);
  const innerAlpha = (0.12 + t * 0.22).toFixed(2);
  const outerAlpha = (0.06 + t * 0.14).toFixed(2);
  return `0 0 ${innerBlur}px rgba(${rgb}, ${innerAlpha}), 0 0 ${outerBlur}px rgba(${rgb}, ${outerAlpha})`;
}

/**
 * Build a stronger text-shadow halo. Used by the Recipe gallery cards
 * specifically, where the badge sits on a calm slate panel with plenty
 * of dead space around it and EARNS the extra bloom. The Risk Board
 * cells stay on `confidenceGlow` (soft) because their backgrounds are
 * already family-color-gradient and a strong glow blooms into
 * neighboring cells.
 *
 * Round-3.6.4 (2026-05-30) — restored to the original confidenceGlow
 * intensity per founder ask (recipe cards only):
 *   t = 0    → no glow
 *   t < 0.18 → no glow
 *   t = 0.5  → tight 3px @ 0.60 + 11px halo @ 0.37
 *   t = 1.0  → tight 4px @ 0.85 + 18px halo @ 0.55
 */
export function confidenceGlowBold(endHex: string, t: number): string {
  if (t < 0.18) return "";
  const e = parseHex(endHex);
  const rgb = `${e.r}, ${e.g}, ${e.b}`;
  const innerBlur = Math.round(1 + t * 3);
  const outerBlur = Math.round(4 + t * 14);
  const innerAlpha = (0.35 + t * 0.5).toFixed(2);
  const outerAlpha = (0.18 + t * 0.37).toFixed(2);
  return `0 0 ${innerBlur}px rgba(${rgb}, ${innerAlpha}), 0 0 ${outerBlur}px rgba(${rgb}, ${outerAlpha})`;
}
