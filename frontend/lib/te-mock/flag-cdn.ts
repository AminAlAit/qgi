/**
 * flag-cdn — derive a flagcdn.com image URL straight from a flag emoji.
 *
 * Why: on Windows 10 the flag emoji (a pair of Regional Indicator Symbols)
 * has no glyph in Segoe UI Emoji, so 🇸🇩 falls back to the bare letters
 * "SD". The cross-browser fix (set on Recipes V4.1) is to render flags as
 * <img> from flagcdn.com. Rather than maintain a name→iso2 lookup (which
 * drifts: "DR Congo" vs "Congo, DRC", "Türkiye" vs "Turkey"), we decode the
 * ISO 3166-1 alpha-2 code directly from the emoji's two Regional Indicator
 * code points. This is exact for every flag emoji, no table to keep in sync.
 *
 * Mockup-only — when the bake ships per-country JSONs the alpha-2 code will
 * arrive on the record directly.
 */

const RI_A = 0x1f1e6; // 🇦 Regional Indicator Symbol Letter A
const RI_Z = 0x1f1ff; // 🇿

/**
 * Decode a flag emoji to its lowercase ISO 3166-1 alpha-2 code, e.g.
 * "🇸🇩" → "sd". Returns null when the input isn't a two-letter flag emoji.
 */
export function iso2FromFlagEmoji(emoji: string): string | null {
  const letters: string[] = [];
  for (const ch of emoji) {
    const cp = ch.codePointAt(0);
    if (cp !== undefined && cp >= RI_A && cp <= RI_Z) {
      letters.push(String.fromCharCode(97 + (cp - RI_A))); // 97 = 'a'
    }
  }
  if (letters.length < 2) return null;
  return letters.slice(0, 2).join("");
}

/**
 * Build a flagcdn.com PNG URL from a flag emoji. `size` is a flagcdn
 * "WxH" preset (e.g. "24x18", "40x30", "64x48"). Returns null when the
 * emoji can't be decoded, so callers render a sized placeholder instead.
 */
export function flagCdnUrl(emoji: string, size = "24x18"): string | null {
  const iso2 = iso2FromFlagEmoji(emoji);
  return iso2 ? `https://flagcdn.com/${size}/${iso2}.png` : null;
}
