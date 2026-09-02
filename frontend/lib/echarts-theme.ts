/**
 * ECharts can't read CSS variables — option objects are plain JS evaluated at
 * build time. So chart components resolve a token set with getEchartsTokens(isDark)
 * (from useTheme) and reference t.* everywhere they'd otherwise hardcode a hex.
 *
 * The two sets mirror app/globals.css :root (dark) and :root.light (light) exactly.
 * Categorical data palettes (lib/design.ts SECTOR_COLORS etc.) are data-ink and
 * are NOT themed here — they carry meaning, not chrome.
 */
export interface EchartsTokens {
  bg: string;
  surface: string;
  surface2: string;
  border: string;
  text: string;
  textMuted: string;
  textDim: string;
  splitLine: string;
  accent: string;
  accentDim: string;
  amber: string;
  countryA: string;
  countryB: string;
  predicted: string;
  success: string;
  warning: string;
  danger: string;
}

const DARK: EchartsTokens = {
  bg: "#0f1923",
  surface: "#162032",
  surface2: "#1e2d42",
  border: "#243347",
  text: "#e2e8f0",
  textMuted: "#9ab0c4",
  textDim: "#8aa6be",
  splitLine: "#1a2a3a",
  accent: "#38bdf8",
  accentDim: "#0ea5e9",
  amber: "#f59e0b",
  countryA: "#38bdf8",
  countryB: "#fb923c",
  predicted: "#6b7f96",
  success: "#34d399",
  warning: "#fbbf24",
  danger: "#f87171",
};

const LIGHT: EchartsTokens = {
  bg: "#f8fafc",
  surface: "#ffffff",
  surface2: "#f1f5f9",
  border: "#cbd5e1",
  text: "#0f172a",
  textMuted: "#475569",
  textDim: "#64748b",
  splitLine: "#e2e8f0",
  accent: "#0284c7",
  accentDim: "#0369a1",
  amber: "#b45309",
  countryA: "#0284c7",
  countryB: "#ea580c",
  predicted: "#94a3b8",
  success: "#16a34a",
  warning: "#92400e", // amber-800; matches --qgi-warning light (small-text contrast)
  danger: "#dc2626",
};

export function getEchartsTokens(isDark: boolean): EchartsTokens {
  return isDark ? DARK : LIGHT;
}
