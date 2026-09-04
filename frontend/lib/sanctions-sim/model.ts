/**
 * Sanctions Simulator — illustrative scenario model.
 *
 * VISION PROTOTYPE. The real sanctions-impact model is in R&D (see
 * `docs/specs/internal/ops/sanctions-simulator-rnd-brief-2026-06-04.md`). Every
 * number here is ILLUSTRATIVE: it applies a curated, tier-scaled "impact
 * profile" to a country's current state to show the SHAPE of the method, not a
 * calibrated causal forecast. Structured so a future R&D phase can swap the
 * curated tables for real model output without changing the UI.
 *
 * Conventions:
 *  - Everything is a 0..100 "level": for indicators, 100 = healthy/benign,
 *    0 = stressed; for trends, 100 = strong resemblance. Sanctions push
 *    indicator levels DOWN and stress-trend resemblance UP.
 *  - Color semantics (set by the UI, not here): a level falling / a resemblance
 *    rising = RED (deteriorating / drifting toward); the opposite = GREEN.
 */

export type TierId = "targeted" | "sectoral" | "comprehensive";

export interface TierDef {
  id: TierId;
  label: string;
  color: string;
  blurb: string;
  /** How much of the full (comprehensive) impact this tier applies, 0..1. */
  factor: number;
  /** Visual band half-width as a fraction of the applied impact (widens with
   *  tier to signal thinner historical samples / higher variance). */
  band: number;
  /** One-line honest note on sample/uncertainty for this tier. */
  sampleNote: string;
}

export const TIERS: TierDef[] = [
  {
    id: "targeted",
    label: "Targeted",
    color: "#E68F29", // amber
    blurb:
      "Asset freezes and travel bans on named individuals. Narrow economic footprint.",
    factor: 0.3,
    band: 0.12,
    sampleNote: "Wider historical sample.",
  },
  {
    id: "sectoral",
    label: "Sectoral",
    color: "#E64545", // red
    blurb:
      "Restrictions on key sectors such as energy, finance, or defense. Moderate systemic pressure.",
    factor: 0.62,
    band: 0.2,
    sampleNote: "Moderate sample, heterogeneous cases.",
  },
  {
    id: "comprehensive",
    label: "Comprehensive",
    color: "#9B2525", // deep red
    blurb:
      "Near-total trade and financial isolation. Historically rare, largest trajectory impact.",
    factor: 1.0,
    band: 0.32,
    sampleNote: "Thin sample, high country-level variance.",
  },
];

export function tier(id: TierId): TierDef {
  return TIERS.find((t) => t.id === id) ?? TIERS[1];
}

export type IndicatorCategory = "Economic" | "Political" | "Social";

export interface IndicatorDef {
  code: string;
  short: string; // tile label
  label: string; // full label
  category: IndicatorCategory;
  /** Goodness lost at full (comprehensive) impact, in 0..100 level points.
   *  All eight deteriorate under sanctions; stored as a positive drop. */
  impact: number;
}

/** The eight most defensible, legible sanctions-channel indicators (Kwame). */
export const INDICATORS: IndicatorDef[] = [
  {
    code: "TRADE",
    short: "Trade openness",
    label: "Trade openness (exports + imports, % GDP)",
    category: "Economic",
    impact: 38,
  },
  {
    code: "FDI",
    short: "FDI inflows",
    label: "Foreign direct investment, net inflows (% GDP)",
    category: "Economic",
    impact: 46,
  },
  {
    code: "RESV",
    short: "FX reserves",
    label: "Foreign-exchange reserves (months of import cover)",
    category: "Economic",
    impact: 40,
  },
  {
    code: "GDP",
    short: "GDP growth",
    label: "GDP growth rate (annual %)",
    category: "Economic",
    impact: 30,
  },
  {
    code: "INFL",
    short: "Price stability",
    label: "Price stability (inverse CPI inflation)",
    category: "Economic",
    impact: 44,
  },
  {
    code: "GOVEFF",
    short: "Govt effectiveness",
    label: "Government effectiveness (governance index)",
    category: "Political",
    impact: 18,
  },
  {
    code: "LAW",
    short: "Rule of law",
    label: "Rule of law (governance index)",
    category: "Political",
    impact: 16,
  },
  {
    code: "CIVLIB",
    short: "Civil liberties",
    label: "Civil liberties (V-Dem)",
    category: "Social",
    impact: 22,
  },
];

export interface TrendDef {
  id: string;
  label: string;
  /** Resemblance gained at full (comprehensive) impact, in 0..100 points.
   *  Positive = country drifts toward this trend; negative = drifts away. */
  response: number;
  /** Suppressed = reverse-causal (the trigger of the sanction, not its effect);
   *  shown greyed with a note, never given a simulated shift. */
  suppressed?: boolean;
  note?: string;
}

/** Event trends a sanctioned trajectory most credibly drifts toward (Kwame),
 *  plus one explicitly-suppressed reverse-causal trend. */
export const TRENDS: TrendDef[] = [
  { id: "econ", label: "Economic stress & currency crisis", response: 34 },
  { id: "default", label: "Sovereign default", response: 28 },
  { id: "repression", label: "Political repression", response: 25 },
  { id: "protest", label: "Protest wave", response: 22 },
  { id: "elite", label: "Elite fragmentation", response: 15 },
  { id: "trade_dispute", label: "Trade dispute", response: 12 },
  { id: "reform", label: "Reform & opening", response: -19 },
  {
    id: "interstate",
    label: "Interstate conflict",
    response: 0,
    suppressed: true,
    note: "Sanction-trigger trend, not a sanction-effect. Often the reason a sanction was imposed, so its resemblance is held fixed here.",
  },
];

export interface CountryDatum {
  iso2: string;
  name: string;
  region: string;
  /** Current 0..100 goodness per indicator code. */
  baseline: Record<string, number>;
  /** Current 0..100 resemblance per trend id. */
  trends: Record<string, number>;
  /** Closest historical sanctioned-period analogues (illustrative). */
  analogues: { country: string; iso2: string; period: string; outcome: string }[];
}

/** Six sanctions-relevant countries with curated, plausible current states. */
export const COUNTRIES: CountryDatum[] = [
  {
    iso2: "ir",
    name: "Iran",
    region: "MENA",
    baseline: {
      TRADE: 42,
      FDI: 30,
      RESV: 46,
      GDP: 48,
      INFL: 28,
      GOVEFF: 36,
      LAW: 34,
      CIVLIB: 24,
    },
    trends: {
      econ: 58,
      default: 36,
      repression: 62,
      protest: 47,
      elite: 40,
      trade_dispute: 44,
      reform: 30,
      interstate: 55,
    },
    analogues: [
      {
        country: "Iran",
        iso2: "ir",
        period: "2012 to 2016",
        outcome:
          "Oil-export embargo, rial collapse, then partial relief under the JCPOA.",
      },
      {
        country: "Russia",
        iso2: "ru",
        period: "2014 to 2018",
        outcome:
          "Crimea-linked sectoral measures, reserve build-up, import substitution.",
      },
    ],
  },
  {
    iso2: "ru",
    name: "Russia",
    region: "Europe",
    baseline: {
      TRADE: 50,
      FDI: 38,
      RESV: 64,
      GDP: 54,
      INFL: 44,
      GOVEFF: 44,
      LAW: 38,
      CIVLIB: 30,
    },
    trends: {
      econ: 44,
      default: 30,
      repression: 58,
      protest: 34,
      elite: 38,
      trade_dispute: 60,
      reform: 28,
      interstate: 70,
    },
    analogues: [
      {
        country: "Russia",
        iso2: "ru",
        period: "2014 to 2021",
        outcome:
          "Sectoral finance and energy curbs; reserves and import substitution cushioned the shock.",
      },
      {
        country: "Iran",
        iso2: "ir",
        period: "2012 to 2016",
        outcome: "Comparable energy-export pressure and currency stress.",
      },
    ],
  },
  {
    iso2: "ve",
    name: "Venezuela",
    region: "Americas",
    baseline: {
      TRADE: 30,
      FDI: 18,
      RESV: 22,
      GDP: 24,
      INFL: 10,
      GOVEFF: 18,
      LAW: 16,
      CIVLIB: 26,
    },
    trends: {
      econ: 78,
      default: 72,
      repression: 64,
      protest: 55,
      elite: 46,
      trade_dispute: 30,
      reform: 22,
      interstate: 24,
    },
    analogues: [
      {
        country: "Venezuela",
        iso2: "ve",
        period: "2017 to 2021",
        outcome:
          "Oil-sector and financial measures amid hyperinflation and mass emigration.",
      },
      {
        country: "Zimbabwe",
        iso2: "zw",
        period: "2002 to 2008",
        outcome: "Targeted measures alongside a domestic currency and output collapse.",
      },
    ],
  },
  {
    iso2: "by",
    name: "Belarus",
    region: "Europe",
    baseline: {
      TRADE: 52,
      FDI: 34,
      RESV: 40,
      GDP: 50,
      INFL: 40,
      GOVEFF: 38,
      LAW: 32,
      CIVLIB: 22,
    },
    trends: {
      econ: 46,
      default: 34,
      repression: 66,
      protest: 52,
      elite: 36,
      trade_dispute: 42,
      reform: 26,
      interstate: 30,
    },
    analogues: [
      {
        country: "Belarus",
        iso2: "by",
        period: "2020 to 2023",
        outcome:
          "Post-election sectoral measures; deepening dependence on a single partner economy.",
      },
      {
        country: "Russia",
        iso2: "ru",
        period: "2014 to 2018",
        outcome: "Shared exposure channels and a similar consolidation response.",
      },
    ],
  },
  {
    iso2: "mm",
    name: "Myanmar",
    region: "Asia-Pacific",
    baseline: {
      TRADE: 44,
      FDI: 28,
      RESV: 38,
      GDP: 40,
      INFL: 34,
      GOVEFF: 24,
      LAW: 20,
      CIVLIB: 18,
    },
    trends: {
      econ: 56,
      default: 40,
      repression: 70,
      protest: 58,
      elite: 44,
      trade_dispute: 28,
      reform: 20,
      interstate: 38,
    },
    analogues: [
      {
        country: "Myanmar",
        iso2: "mm",
        period: "2021 to 2024",
        outcome: "Post-coup measures; FDI withdrawal and a sharp currency depreciation.",
      },
      {
        country: "Myanmar",
        iso2: "mm",
        period: "1997 to 2011",
        outcome: "An earlier, longer isolation episode that ended in gradual reopening.",
      },
    ],
  },
  {
    iso2: "sy",
    name: "Syria",
    region: "MENA",
    baseline: {
      TRADE: 26,
      FDI: 14,
      RESV: 18,
      GDP: 20,
      INFL: 12,
      GOVEFF: 16,
      LAW: 14,
      CIVLIB: 16,
    },
    trends: {
      econ: 80,
      default: 66,
      repression: 72,
      protest: 40,
      elite: 50,
      trade_dispute: 24,
      reform: 18,
      interstate: 64,
    },
    analogues: [
      {
        country: "Syria",
        iso2: "sy",
        period: "2011 to 2019",
        outcome: "Comprehensive measures during conflict; currency and reserve collapse.",
      },
      {
        country: "Venezuela",
        iso2: "ve",
        period: "2017 to 2021",
        outcome: "Comparable depth of contraction under broad financial isolation.",
      },
    ],
  },
];

export function country(iso2: string): CountryDatum {
  return COUNTRIES.find((c) => c.iso2 === iso2.toLowerCase()) ?? COUNTRIES[0];
}

export const HORIZONS = [1, 2, 3, 5] as const;
export type Horizon = (typeof HORIZONS)[number];

/** Pre-onset lead-in (years shown before t=0) for the trajectory charts. */
export const LEAD_IN = 2;

const clamp = (v: number, lo = 0, hi = 100) => Math.max(lo, Math.min(hi, v));

/** Impact applied at relative time t (years after onset), as a fraction of the
 *  full per-tier impact. 0 before onset, easing up to 1.0 by the horizon end
 *  (fast early, plateauing). */
function rampFraction(t: number, horizon: number): number {
  if (t <= 0) return 0;
  const x = Math.min(1, t / horizon);
  return 1 - Math.pow(1 - x, 1.7);
}

export interface SeriesPoint {
  t: number; // year relative to onset (negative = pre)
  baseline: number; // 0..100 level, flat at current
  sim: number; // 0..100 simulated level
  lo: number; // band lower
  hi: number; // band upper
}

/** Per-indicator trajectory: flat baseline vs ramped sanctioned level + band. */
export function indicatorSeries(
  c: CountryDatum,
  code: string,
  tierId: TierId,
  horizon: number
): SeriesPoint[] {
  const def = INDICATORS.find((i) => i.code === code)!;
  const base = c.baseline[code] ?? 50;
  const t = tier(tierId);
  const fullDrop = def.impact * t.factor;
  const out: SeriesPoint[] = [];
  for (let yr = -LEAD_IN; yr <= horizon; yr++) {
    const frac = rampFraction(yr, horizon);
    const drop = fullDrop * frac;
    const sim = clamp(base - drop);
    const half = drop * t.band;
    out.push({
      t: yr,
      baseline: base,
      sim,
      lo: clamp(sim - half),
      hi: clamp(sim + half),
    });
  }
  return out;
}

/** Composite goodness (mean across the eight indicators) trajectory. */
export function compositeSeries(
  c: CountryDatum,
  tierId: TierId,
  horizon: number
): SeriesPoint[] {
  const perCode = INDICATORS.map((i) => indicatorSeries(c, i.code, tierId, horizon));
  const n = perCode[0].length;
  const out: SeriesPoint[] = [];
  for (let k = 0; k < n; k++) {
    const avg = (sel: (p: SeriesPoint) => number) =>
      perCode.reduce((s, arr) => s + sel(arr[k]), 0) / perCode.length;
    out.push({
      t: perCode[0][k].t,
      baseline: avg((p) => p.baseline),
      sim: avg((p) => p.sim),
      lo: avg((p) => p.lo),
      hi: avg((p) => p.hi),
    });
  }
  return out;
}

/** Composite end-state level (at the horizon) for a tier — used by the
 *  tier-response curve and headline stat. */
export function compositeEnd(c: CountryDatum, tierId: TierId, horizon: number): number {
  const s = compositeSeries(c, tierId, horizon);
  return s[s.length - 1].sim;
}

export interface TrendShift {
  id: string;
  label: string;
  current: number;
  sim: number;
  delta: number;
  suppressed?: boolean;
  note?: string;
}

/** Trend-resemblance shift now -> simulated for the chosen tier. */
export function trendShifts(c: CountryDatum, tierId: TierId): TrendShift[] {
  const f = tier(tierId).factor;
  return TRENDS.map((tr) => {
    const current = c.trends[tr.id] ?? 0;
    if (tr.suppressed) {
      return {
        id: tr.id,
        label: tr.label,
        current,
        sim: current,
        delta: 0,
        suppressed: true,
        note: tr.note,
      };
    }
    const sim = clamp(current + tr.response * f);
    return { id: tr.id, label: tr.label, current, sim, delta: Math.round(sim - current) };
  });
}

/** The dynamic scenario readout: the strongest riser and faller. */
export function readout(
  c: CountryDatum,
  tierId: TierId
): { topRise: TrendShift | null; topFall: TrendShift | null } {
  const live = trendShifts(c, tierId).filter((s) => !s.suppressed);
  const rising = [...live].sort((a, b) => b.delta - a.delta);
  const falling = [...live].sort((a, b) => a.delta - b.delta);
  const topRise = rising[0] && rising[0].delta > 0 ? rising[0] : null;
  const topFall = falling[0] && falling[0].delta < 0 ? falling[0] : null;
  return { topRise, topFall };
}
