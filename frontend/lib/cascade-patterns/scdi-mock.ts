/**
 * scdi-mock.ts — hand-mocked per-pattern indicator lists for the 10
 * showcase patterns on /patterns/[slug].
 *
 * FILE NAME intentionally keeps "scdi" — internal contract name.
 * User-visible copy says "Pattern Indicators" (Step 6 sweep).
 *
 * When the real `data/cascade/pattern-scdis.json` bake lands, this file
 * gets a ONE-LINE swap: replace the static MOCKED_INDICATORS map with a
 * read from the baked JSON. The TypeScript types (PatternIndicator,
 * PatternMeta) are the stable contract.
 *
 * Slug format (5-segment, alphabetical ISO order):
 *   {a_iso2}-{b_iso2}-{start_year_a}-{end_year} (4 segments)
 *   e.g.  pt-es-1975-2024
 *
 * Indicator codes sourced from data/indexes.json (numeric_id verified).
 * Pearson r values are in range 0.60-0.95. Z-score trajectories have 12
 * quarterly-era points per country (enough for sparkline rendering).
 * Direction "same" = both move together; "opposite" = inverse shapes.
 */

// ── Types ─────────────────────────────────────────────────────────────────

/** A single pattern indicator entry. */
export interface PatternIndicator {
  /** Indicator string code from indexes.json (e.g. "NY.GDP.MKTP.KD.ZG"). */
  code: string;
  /** Numeric indicator ID from indexes.json (1-259). */
  numeric_id: number;
  /** Human-readable name (matches indexes.json .name field). */
  name: string;
  /** Sector string from indexes.json (e.g. "Economic", "Political"). */
  sector: string;
  /** Pearson correlation coefficient over the shared window, range 0.60-0.95. */
  pearson_r: number;
  /** Whether both countries moved in the same direction, or opposite. */
  direction: "same" | "opposite";
  /**
   * 12-point z-score trajectory for country A across the window.
   * Each point is a z-score relative to that country's own baseline.
   */
  series_a: number[];
  /**
   * 12-point z-score trajectory for country B across the window.
   * Same direction → visually similar shape to series_a.
   * Opposite direction → approximately inverted shape.
   */
  series_b: number[];
}

/** Metadata about a pattern entry (mirrors the 5-tuple + strength fields). */
export interface PatternMeta {
  slug: string;
  a_iso2: string;
  b_iso2: string;
  a_name: string;
  b_name: string;
  start_year: number;
  end_year: number;
  length: number;
  pps: number;
  avg_correlation: number;
  num_indicators: number;
  tier: "XL" | "L" | "M" | "S";
  plausibility_note: string;
}

// ── Z-score trajectory helpers ────────────────────────────────────────────

/** Rising trend: starts low, ends high. */
function riseTrajectory(noise = 0.15): number[] {
  return Array.from({ length: 12 }, (_, i) => {
    const t = i / 11;
    return Math.round((-1.2 + t * 2.4 + (Math.random() - 0.5) * noise * 2) * 100) / 100;
  });
}

/** Falling trend: starts high, ends low. */
function fallTrajectory(noise = 0.15): number[] {
  return Array.from({ length: 12 }, (_, i) => {
    const t = i / 11;
    return Math.round((1.2 - t * 2.4 + (Math.random() - 0.5) * noise * 2) * 100) / 100;
  });
}

/** V-shape recovery: drops then recovers. */
function vShapeTrajectory(noise = 0.15): number[] {
  return Array.from({ length: 12 }, (_, i) => {
    const t = i / 11;
    const v = Math.abs(t - 0.5) * 2 - 1;
    return Math.round((v + (Math.random() - 0.5) * noise * 2) * 100) / 100;
  });
}

/** Oscillation: sine wave. */
function sineTrajectory(phase = 0, noise = 0.12): number[] {
  return Array.from({ length: 12 }, (_, i) => {
    const t = i / 11;
    return Math.round((Math.sin(t * Math.PI * 2 + phase) + (Math.random() - 0.5) * noise * 2) * 100) / 100;
  });
}

/** Step-up: flat then sudden jump. */
function stepUpTrajectory(noise = 0.1): number[] {
  return Array.from({ length: 12 }, (_, i) => {
    const base = i >= 6 ? 1.0 : -0.3;
    return Math.round((base + (Math.random() - 0.5) * noise * 2) * 100) / 100;
  });
}

/** Plateau-then-decline. */
function plateauDeclineTrajectory(noise = 0.12): number[] {
  return Array.from({ length: 12 }, (_, i) => {
    const t = i / 11;
    const val = t < 0.5 ? 0.8 : 0.8 - (t - 0.5) * 3;
    return Math.round((val + (Math.random() - 0.5) * noise * 2) * 100) / 100;
  });
}

// ── 10 mocked pattern indicator lists ────────────────────────────────────

const MOCKED_INDICATORS: Record<string, PatternIndicator[]> = {

  // ── XL: pt-es-1975-2024 (Portugal + Spain, 50y, Iberian mirror)
  // Economic convergence, EU accession, democracy consolidation
  "pt-es-1975-2024": [
    { code: "NY.GDP.MKTP.KD.ZG", numeric_id: 1, name: "GDP growth (annual %)", sector: "Economic", pearson_r: 0.91, direction: "same", series_a: riseTrajectory(0.1), series_b: riseTrajectory(0.12) },
    { code: "NY.GDP.PCAP.CD", numeric_id: 9, name: "GDP per capita (current US$)", sector: "Economic", pearson_r: 0.94, direction: "same", series_a: riseTrajectory(0.08), series_b: riseTrajectory(0.09) },
    { code: "FP.CPI.TOTL.ZG", numeric_id: 30, name: "Inflation, consumer prices (annual %)", sector: "Economic", pearson_r: 0.88, direction: "same", series_a: fallTrajectory(0.1), series_b: fallTrajectory(0.11) },
    { code: "SL.UEM.TOTL.ZS", numeric_id: 8, name: "Unemployment, total (% of total labor force)", sector: "Social", pearson_r: 0.82, direction: "same", series_a: vShapeTrajectory(0.12), series_b: vShapeTrajectory(0.13) },
    { code: "NE.EXP.GNFS.ZS", numeric_id: 18, name: "Exports of goods and services (% of GDP)", sector: "Trade", pearson_r: 0.87, direction: "same", series_a: riseTrajectory(0.1), series_b: riseTrajectory(0.1) },
    { code: "NE.IMP.GNFS.ZS", numeric_id: 20, name: "Imports of goods and services (% of GDP)", sector: "Trade", pearson_r: 0.85, direction: "same", series_a: riseTrajectory(0.1), series_b: riseTrajectory(0.1) },
    { code: "VA.EST", numeric_id: 21, name: "Voice and Accountability (estimate)", sector: "Governance", pearson_r: 0.90, direction: "same", series_a: riseTrajectory(0.08), series_b: riseTrajectory(0.08) },
    { code: "GE.EST", numeric_id: 22, name: "Government Effectiveness (estimate)", sector: "Governance", pearson_r: 0.86, direction: "same", series_a: riseTrajectory(0.09), series_b: riseTrajectory(0.1) },
    { code: "RL.EST", numeric_id: 24, name: "Rule of Law (estimate)", sector: "Governance", pearson_r: 0.88, direction: "same", series_a: riseTrajectory(0.09), series_b: riseTrajectory(0.1) },
    { code: "CC.EST", numeric_id: 25, name: "Control of Corruption (estimate)", sector: "Governance", pearson_r: 0.84, direction: "same", series_a: riseTrajectory(0.1), series_b: riseTrajectory(0.1) },
    { code: "RQ.EST", numeric_id: 23, name: "Regulatory Quality (estimate)", sector: "Governance", pearson_r: 0.87, direction: "same", series_a: riseTrajectory(0.09), series_b: riseTrajectory(0.1) },
    { code: "SE.PRM.ENRR", numeric_id: 6, name: "School enrollment, primary (% gross)", sector: "Education", pearson_r: 0.79, direction: "same", series_a: riseTrajectory(0.12), series_b: riseTrajectory(0.12) },
    { code: "SP.URB.TOTL.IN.ZS", numeric_id: 62, name: "Urban population (% of total population)", sector: "Demographic", pearson_r: 0.95, direction: "same", series_a: riseTrajectory(0.05), series_b: riseTrajectory(0.06) },
    { code: "SP.DYN.LE00.IN", numeric_id: 4, name: "Life expectancy at birth, total (years)", sector: "Health", pearson_r: 0.96, direction: "same", series_a: riseTrajectory(0.05), series_b: riseTrajectory(0.05) },
    { code: "SH.DYN.MORT", numeric_id: 14, name: "Mortality rate, under-5 (per 1,000 live births)", sector: "Health", pearson_r: 0.93, direction: "same", series_a: fallTrajectory(0.07), series_b: fallTrajectory(0.07) },
    { code: "SP.DYN.TFRT.IN", numeric_id: 15, name: "Fertility rate, total (births per woman)", sector: "Demographic", pearson_r: 0.91, direction: "same", series_a: fallTrajectory(0.08), series_b: fallTrajectory(0.09) },
    { code: "IT.NET.USER.ZS", numeric_id: 13, name: "Individuals using the Internet (% of population)", sector: "Infrastructure", pearson_r: 0.92, direction: "same", series_a: riseTrajectory(0.07), series_b: riseTrajectory(0.07) },
    { code: "BX.KLT.DINV.WD.GD.ZS", numeric_id: 40, name: "Foreign direct investment, net inflows (% of GDP)", sector: "Finance", pearson_r: 0.72, direction: "same", series_a: sineTrajectory(0, 0.15), series_b: sineTrajectory(0.2, 0.15) },
    { code: "NV.SRV.TOTL.ZS", numeric_id: 36, name: "Services, value added (% of GDP)", sector: "Economic", pearson_r: 0.89, direction: "same", series_a: riseTrajectory(0.09), series_b: riseTrajectory(0.1) },
    { code: "NV.IND.TOTL.ZS", numeric_id: 34, name: "Industry (including construction), value added (% of GDP)", sector: "Economic", pearson_r: 0.67, direction: "opposite", series_a: riseTrajectory(0.1), series_b: fallTrajectory(0.1) },
    { code: "NV.AGR.TOTL.ZS", numeric_id: 33, name: "Agriculture, forestry, and fishing, value added (% of GDP)", sector: "Economic", pearson_r: 0.85, direction: "same", series_a: fallTrajectory(0.1), series_b: fallTrajectory(0.1) },
    { code: "MS.MIL.XPND.GD.ZS", numeric_id: 26, name: "Military expenditure (% of GDP)", sector: "Military", pearson_r: 0.71, direction: "same", series_a: fallTrajectory(0.12), series_b: fallTrajectory(0.13) },
    { code: "PV.EST", numeric_id: 3, name: "Political Stability and Absence of Violence (estimate)", sector: "Governance", pearson_r: 0.78, direction: "same", series_a: riseTrajectory(0.12), series_b: riseTrajectory(0.12) },
    { code: "NE.GDI.TOTL.ZS", numeric_id: 37, name: "Gross capital formation (% of GDP)", sector: "Economic", pearson_r: 0.66, direction: "same", series_a: sineTrajectory(0.3, 0.15), series_b: sineTrajectory(0.5, 0.15) },
    { code: "SP.POP.GROW", numeric_id: 61, name: "Population growth (annual %)", sector: "Demographic", pearson_r: 0.81, direction: "same", series_a: fallTrajectory(0.12), series_b: fallTrajectory(0.12) },
  ],

  // ── L1: pl-cz-1989-2024 (Poland + Czech Republic, 35y, post-communist transition)
  "pl-cz-1989-2024": [
    { code: "NY.GDP.MKTP.KD.ZG", numeric_id: 1, name: "GDP growth (annual %)", sector: "Economic", pearson_r: 0.88, direction: "same", series_a: riseTrajectory(0.12), series_b: riseTrajectory(0.11) },
    { code: "FP.CPI.TOTL.ZG", numeric_id: 30, name: "Inflation, consumer prices (annual %)", sector: "Economic", pearson_r: 0.85, direction: "same", series_a: fallTrajectory(0.1), series_b: fallTrajectory(0.11) },
    { code: "SL.UEM.TOTL.ZS", numeric_id: 8, name: "Unemployment, total (% of total labor force)", sector: "Social", pearson_r: 0.79, direction: "same", series_a: vShapeTrajectory(0.12), series_b: vShapeTrajectory(0.13) },
    { code: "VA.EST", numeric_id: 21, name: "Voice and Accountability (estimate)", sector: "Governance", pearson_r: 0.87, direction: "same", series_a: riseTrajectory(0.09), series_b: riseTrajectory(0.09) },
    { code: "GE.EST", numeric_id: 22, name: "Government Effectiveness (estimate)", sector: "Governance", pearson_r: 0.83, direction: "same", series_a: riseTrajectory(0.1), series_b: riseTrajectory(0.1) },
    { code: "RL.EST", numeric_id: 24, name: "Rule of Law (estimate)", sector: "Governance", pearson_r: 0.86, direction: "same", series_a: riseTrajectory(0.1), series_b: riseTrajectory(0.1) },
    { code: "CC.EST", numeric_id: 25, name: "Control of Corruption (estimate)", sector: "Governance", pearson_r: 0.81, direction: "same", series_a: riseTrajectory(0.1), series_b: riseTrajectory(0.11) },
    { code: "BX.KLT.DINV.WD.GD.ZS", numeric_id: 40, name: "Foreign direct investment, net inflows (% of GDP)", sector: "Finance", pearson_r: 0.76, direction: "same", series_a: riseTrajectory(0.14), series_b: riseTrajectory(0.14) },
    { code: "IT.NET.USER.ZS", numeric_id: 13, name: "Individuals using the Internet (% of population)", sector: "Infrastructure", pearson_r: 0.91, direction: "same", series_a: riseTrajectory(0.07), series_b: riseTrajectory(0.07) },
    { code: "SP.DYN.LE00.IN", numeric_id: 4, name: "Life expectancy at birth, total (years)", sector: "Health", pearson_r: 0.92, direction: "same", series_a: riseTrajectory(0.06), series_b: riseTrajectory(0.06) },
    { code: "NY.GDP.PCAP.CD", numeric_id: 9, name: "GDP per capita (current US$)", sector: "Economic", pearson_r: 0.90, direction: "same", series_a: riseTrajectory(0.09), series_b: riseTrajectory(0.09) },
    { code: "NE.EXP.GNFS.ZS", numeric_id: 18, name: "Exports of goods and services (% of GDP)", sector: "Trade", pearson_r: 0.82, direction: "same", series_a: riseTrajectory(0.11), series_b: riseTrajectory(0.11) },
    { code: "MS.MIL.XPND.GD.ZS", numeric_id: 26, name: "Military expenditure (% of GDP)", sector: "Military", pearson_r: 0.68, direction: "opposite", series_a: riseTrajectory(0.1), series_b: fallTrajectory(0.1) },
    { code: "NV.IND.MANF.ZS", numeric_id: 35, name: "Manufacturing, value added (% of GDP)", sector: "Economic", pearson_r: 0.74, direction: "same", series_a: sineTrajectory(0.1, 0.13), series_b: sineTrajectory(0.2, 0.13) },
    { code: "SE.PRM.ENRR", numeric_id: 6, name: "School enrollment, primary (% gross)", sector: "Education", pearson_r: 0.77, direction: "same", series_a: riseTrajectory(0.12), series_b: riseTrajectory(0.12) },
    { code: "PV.EST", numeric_id: 3, name: "Political Stability and Absence of Violence (estimate)", sector: "Governance", pearson_r: 0.80, direction: "same", series_a: riseTrajectory(0.11), series_b: riseTrajectory(0.11) },
    { code: "SP.DYN.TFRT.IN", numeric_id: 15, name: "Fertility rate, total (births per woman)", sector: "Demographic", pearson_r: 0.89, direction: "same", series_a: fallTrajectory(0.09), series_b: fallTrajectory(0.09) },
  ],

  // ── L2: ke-ug-1990-2024 (Kenya + Uganda, 34y, East Africa co-development)
  "ke-ug-1990-2024": [
    { code: "NY.GDP.MKTP.KD.ZG", numeric_id: 1, name: "GDP growth (annual %)", sector: "Economic", pearson_r: 0.81, direction: "same", series_a: sineTrajectory(0, 0.15), series_b: sineTrajectory(0.2, 0.15) },
    { code: "SP.DYN.LE00.IN", numeric_id: 4, name: "Life expectancy at birth, total (years)", sector: "Health", pearson_r: 0.93, direction: "same", series_a: riseTrajectory(0.08), series_b: riseTrajectory(0.09) },
    { code: "SH.DYN.MORT", numeric_id: 14, name: "Mortality rate, under-5 (per 1,000 live births)", sector: "Health", pearson_r: 0.91, direction: "same", series_a: fallTrajectory(0.09), series_b: fallTrajectory(0.09) },
    { code: "SP.DYN.TFRT.IN", numeric_id: 15, name: "Fertility rate, total (births per woman)", sector: "Demographic", pearson_r: 0.88, direction: "same", series_a: fallTrajectory(0.1), series_b: fallTrajectory(0.1) },
    { code: "NE.EXP.GNFS.ZS", numeric_id: 18, name: "Exports of goods and services (% of GDP)", sector: "Trade", pearson_r: 0.72, direction: "same", series_a: riseTrajectory(0.14), series_b: riseTrajectory(0.14) },
    { code: "NE.IMP.GNFS.ZS", numeric_id: 20, name: "Imports of goods and services (% of GDP)", sector: "Trade", pearson_r: 0.74, direction: "same", series_a: riseTrajectory(0.13), series_b: riseTrajectory(0.14) },
    { code: "VA.EST", numeric_id: 21, name: "Voice and Accountability (estimate)", sector: "Governance", pearson_r: 0.67, direction: "same", series_a: sineTrajectory(0.3, 0.2), series_b: sineTrajectory(0.5, 0.2) },
    { code: "PV.EST", numeric_id: 3, name: "Political Stability and Absence of Violence (estimate)", sector: "Governance", pearson_r: 0.71, direction: "same", series_a: sineTrajectory(0.1, 0.18), series_b: sineTrajectory(0.2, 0.18) },
    { code: "BX.KLT.DINV.WD.GD.ZS", numeric_id: 40, name: "Foreign direct investment, net inflows (% of GDP)", sector: "Finance", pearson_r: 0.76, direction: "same", series_a: riseTrajectory(0.13), series_b: riseTrajectory(0.13) },
    { code: "IT.NET.USER.ZS", numeric_id: 13, name: "Individuals using the Internet (% of population)", sector: "Infrastructure", pearson_r: 0.87, direction: "same", series_a: stepUpTrajectory(0.1), series_b: stepUpTrajectory(0.1) },
    { code: "SP.URB.TOTL.IN.ZS", numeric_id: 62, name: "Urban population (% of total population)", sector: "Demographic", pearson_r: 0.92, direction: "same", series_a: riseTrajectory(0.07), series_b: riseTrajectory(0.07) },
    { code: "SE.PRM.ENRR", numeric_id: 6, name: "School enrollment, primary (% gross)", sector: "Education", pearson_r: 0.83, direction: "same", series_a: riseTrajectory(0.11), series_b: riseTrajectory(0.11) },
    { code: "NV.AGR.TOTL.ZS", numeric_id: 33, name: "Agriculture, forestry, and fishing, value added (% of GDP)", sector: "Economic", pearson_r: 0.78, direction: "same", series_a: fallTrajectory(0.12), series_b: fallTrajectory(0.12) },
    { code: "NY.GDP.PCAP.CD", numeric_id: 9, name: "GDP per capita (current US$)", sector: "Economic", pearson_r: 0.85, direction: "same", series_a: riseTrajectory(0.1), series_b: riseTrajectory(0.11) },
  ],

  // ── M1: tn-eg-1975-2018 (Tunisia + Egypt, 43y, MENA authoritarian-transition)
  "eg-tn-1975-2018": [
    { code: "NY.GDP.MKTP.KD.ZG", numeric_id: 1, name: "GDP growth (annual %)", sector: "Economic", pearson_r: 0.80, direction: "same", series_a: sineTrajectory(0, 0.15), series_b: sineTrajectory(0.1, 0.15) },
    { code: "SP.POP.TOTL", numeric_id: 2, name: "Population, total", sector: "Demographic", pearson_r: 0.79, direction: "same", series_a: riseTrajectory(0.07), series_b: riseTrajectory(0.07) },
    { code: "VA.EST", numeric_id: 21, name: "Voice and Accountability (estimate)", sector: "Governance", pearson_r: 0.72, direction: "same", series_a: sineTrajectory(0, 0.18), series_b: sineTrajectory(0.2, 0.18) },
    { code: "PV.EST", numeric_id: 3, name: "Political Stability and Absence of Violence (estimate)", sector: "Governance", pearson_r: 0.69, direction: "same", series_a: plateauDeclineTrajectory(0.12), series_b: plateauDeclineTrajectory(0.13) },
    { code: "FP.CPI.TOTL.ZG", numeric_id: 30, name: "Inflation, consumer prices (annual %)", sector: "Economic", pearson_r: 0.75, direction: "same", series_a: sineTrajectory(0.1, 0.15), series_b: sineTrajectory(0.2, 0.15) },
    { code: "SL.UEM.TOTL.ZS", numeric_id: 8, name: "Unemployment, total (% of total labor force)", sector: "Social", pearson_r: 0.71, direction: "same", series_a: sineTrajectory(0.2, 0.15), series_b: sineTrajectory(0.3, 0.15) },
    { code: "SP.DYN.LE00.IN", numeric_id: 4, name: "Life expectancy at birth, total (years)", sector: "Health", pearson_r: 0.88, direction: "same", series_a: riseTrajectory(0.08), series_b: riseTrajectory(0.09) },
    { code: "SP.DYN.TFRT.IN", numeric_id: 15, name: "Fertility rate, total (births per woman)", sector: "Demographic", pearson_r: 0.87, direction: "same", series_a: fallTrajectory(0.09), series_b: fallTrajectory(0.09) },
    { code: "NE.EXP.GNFS.ZS", numeric_id: 18, name: "Exports of goods and services (% of GDP)", sector: "Trade", pearson_r: 0.73, direction: "same", series_a: sineTrajectory(0.2, 0.15), series_b: sineTrajectory(0.3, 0.15) },
    { code: "CC.EST", numeric_id: 25, name: "Control of Corruption (estimate)", sector: "Governance", pearson_r: 0.66, direction: "same", series_a: fallTrajectory(0.14), series_b: fallTrajectory(0.14) },
  ],

  // ── M2: ar-ru-1985-2024 (Argentina + Russia, 39y, hyperinflation/collapse/recovery)
  "ar-ru-1985-2024": [
    { code: "FP.CPI.TOTL.ZG", numeric_id: 30, name: "Inflation, consumer prices (annual %)", sector: "Economic", pearson_r: 0.85, direction: "same", series_a: sineTrajectory(0, 0.12), series_b: sineTrajectory(0.2, 0.12) },
    { code: "NY.GDP.MKTP.KD.ZG", numeric_id: 1, name: "GDP growth (annual %)", sector: "Economic", pearson_r: 0.79, direction: "same", series_a: vShapeTrajectory(0.14), series_b: vShapeTrajectory(0.14) },
    { code: "CC.EST", numeric_id: 25, name: "Control of Corruption (estimate)", sector: "Governance", pearson_r: 0.72, direction: "same", series_a: fallTrajectory(0.13), series_b: fallTrajectory(0.13) },
    { code: "VA.EST", numeric_id: 21, name: "Voice and Accountability (estimate)", sector: "Governance", pearson_r: 0.68, direction: "same", series_a: sineTrajectory(0, 0.18), series_b: sineTrajectory(0.2, 0.18) },
    { code: "NY.GDP.PCAP.CD", numeric_id: 9, name: "GDP per capita (current US$)", sector: "Economic", pearson_r: 0.76, direction: "same", series_a: sineTrajectory(0.1, 0.15), series_b: sineTrajectory(0.2, 0.15) },
    { code: "MS.MIL.XPND.GD.ZS", numeric_id: 26, name: "Military expenditure (% of GDP)", sector: "Military", pearson_r: 0.67, direction: "same", series_a: fallTrajectory(0.14), series_b: fallTrajectory(0.14) },
    { code: "NE.EXP.GNFS.ZS", numeric_id: 18, name: "Exports of goods and services (% of GDP)", sector: "Trade", pearson_r: 0.71, direction: "same", series_a: riseTrajectory(0.14), series_b: riseTrajectory(0.14) },
    { code: "BX.KLT.DINV.WD.GD.ZS", numeric_id: 40, name: "Foreign direct investment, net inflows (% of GDP)", sector: "Finance", pearson_r: 0.62, direction: "same", series_a: sineTrajectory(0.5, 0.2), series_b: sineTrajectory(0.6, 0.2) },
    { code: "PV.EST", numeric_id: 3, name: "Political Stability and Absence of Violence (estimate)", sector: "Governance", pearson_r: 0.70, direction: "same", series_a: sineTrajectory(0.2, 0.18), series_b: sineTrajectory(0.3, 0.18) },
    { code: "RL.EST", numeric_id: 24, name: "Rule of Law (estimate)", sector: "Governance", pearson_r: 0.65, direction: "same", series_a: fallTrajectory(0.14), series_b: fallTrajectory(0.14) },
  ],

  // ── M3: gh-sn-1980-2024 (Ghana + Senegal, 44y, West Africa democratic consolidation)
  "gh-sn-1980-2024": [
    { code: "NY.GDP.MKTP.KD.ZG", numeric_id: 1, name: "GDP growth (annual %)", sector: "Economic", pearson_r: 0.77, direction: "same", series_a: riseTrajectory(0.14), series_b: riseTrajectory(0.14) },
    { code: "VA.EST", numeric_id: 21, name: "Voice and Accountability (estimate)", sector: "Governance", pearson_r: 0.84, direction: "same", series_a: riseTrajectory(0.1), series_b: riseTrajectory(0.1) },
    { code: "PV.EST", numeric_id: 3, name: "Political Stability and Absence of Violence (estimate)", sector: "Governance", pearson_r: 0.80, direction: "same", series_a: riseTrajectory(0.11), series_b: riseTrajectory(0.12) },
    { code: "SH.DYN.MORT", numeric_id: 14, name: "Mortality rate, under-5 (per 1,000 live births)", sector: "Health", pearson_r: 0.89, direction: "same", series_a: fallTrajectory(0.09), series_b: fallTrajectory(0.09) },
    { code: "SP.DYN.LE00.IN", numeric_id: 4, name: "Life expectancy at birth, total (years)", sector: "Health", pearson_r: 0.87, direction: "same", series_a: riseTrajectory(0.09), series_b: riseTrajectory(0.09) },
    { code: "NE.EXP.GNFS.ZS", numeric_id: 18, name: "Exports of goods and services (% of GDP)", sector: "Trade", pearson_r: 0.74, direction: "same", series_a: riseTrajectory(0.13), series_b: riseTrajectory(0.13) },
    { code: "BX.KLT.DINV.WD.GD.ZS", numeric_id: 40, name: "Foreign direct investment, net inflows (% of GDP)", sector: "Finance", pearson_r: 0.71, direction: "same", series_a: riseTrajectory(0.14), series_b: riseTrajectory(0.14) },
    { code: "SP.DYN.TFRT.IN", numeric_id: 15, name: "Fertility rate, total (births per woman)", sector: "Demographic", pearson_r: 0.90, direction: "same", series_a: fallTrajectory(0.09), series_b: fallTrajectory(0.09) },
    { code: "SE.PRM.ENRR", numeric_id: 6, name: "School enrollment, primary (% gross)", sector: "Education", pearson_r: 0.82, direction: "same", series_a: riseTrajectory(0.11), series_b: riseTrajectory(0.11) },
    { code: "CC.EST", numeric_id: 25, name: "Control of Corruption (estimate)", sector: "Governance", pearson_r: 0.75, direction: "same", series_a: sineTrajectory(0.1, 0.15), series_b: sineTrajectory(0.2, 0.15) },
    { code: "NV.AGR.TOTL.ZS", numeric_id: 33, name: "Agriculture, forestry, and fishing, value added (% of GDP)", sector: "Economic", pearson_r: 0.78, direction: "same", series_a: fallTrajectory(0.12), series_b: fallTrajectory(0.12) },
  ],

  // ── S1: ua-ge-2000-2024 (Ukraine + Georgia, 24y, post-Soviet reform/rupture)
  "ge-ua-2000-2024": [
    { code: "VA.EST", numeric_id: 21, name: "Voice and Accountability (estimate)", sector: "Governance", pearson_r: 0.82, direction: "same", series_a: riseTrajectory(0.12), series_b: riseTrajectory(0.12) },
    { code: "PV.EST", numeric_id: 3, name: "Political Stability and Absence of Violence (estimate)", sector: "Governance", pearson_r: 0.70, direction: "same", series_a: sineTrajectory(0, 0.18), series_b: sineTrajectory(0.2, 0.18) },
    { code: "GE.EST", numeric_id: 22, name: "Government Effectiveness (estimate)", sector: "Governance", pearson_r: 0.78, direction: "same", series_a: riseTrajectory(0.12), series_b: riseTrajectory(0.12) },
    { code: "CC.EST", numeric_id: 25, name: "Control of Corruption (estimate)", sector: "Governance", pearson_r: 0.74, direction: "same", series_a: riseTrajectory(0.13), series_b: riseTrajectory(0.13) },
    { code: "BX.KLT.DINV.WD.GD.ZS", numeric_id: 40, name: "Foreign direct investment, net inflows (% of GDP)", sector: "Finance", pearson_r: 0.68, direction: "same", series_a: sineTrajectory(0.3, 0.18), series_b: sineTrajectory(0.4, 0.18) },
    { code: "IT.NET.USER.ZS", numeric_id: 13, name: "Individuals using the Internet (% of population)", sector: "Infrastructure", pearson_r: 0.87, direction: "same", series_a: stepUpTrajectory(0.1), series_b: stepUpTrajectory(0.1) },
    { code: "NY.GDP.MKTP.KD.ZG", numeric_id: 1, name: "GDP growth (annual %)", sector: "Economic", pearson_r: 0.73, direction: "same", series_a: sineTrajectory(0.2, 0.16), series_b: sineTrajectory(0.3, 0.16) },
  ],

  // ── S2: lb-gr-2000-2022 (Lebanon + Greece, 22y, sovereign debt crisis rhyme)
  "gr-lb-2000-2022": [
    { code: "FP.CPI.TOTL.ZG", numeric_id: 30, name: "Inflation, consumer prices (annual %)", sector: "Economic", pearson_r: 0.73, direction: "same", series_a: stepUpTrajectory(0.1), series_b: stepUpTrajectory(0.12) },
    { code: "SL.UEM.TOTL.ZS", numeric_id: 8, name: "Unemployment, total (% of total labor force)", sector: "Social", pearson_r: 0.79, direction: "same", series_a: stepUpTrajectory(0.1), series_b: stepUpTrajectory(0.12) },
    { code: "NY.GDP.MKTP.KD.ZG", numeric_id: 1, name: "GDP growth (annual %)", sector: "Economic", pearson_r: 0.76, direction: "same", series_a: vShapeTrajectory(0.13), series_b: vShapeTrajectory(0.14) },
    { code: "PV.EST", numeric_id: 3, name: "Political Stability and Absence of Violence (estimate)", sector: "Governance", pearson_r: 0.67, direction: "same", series_a: fallTrajectory(0.14), series_b: fallTrajectory(0.14) },
    { code: "CC.EST", numeric_id: 25, name: "Control of Corruption (estimate)", sector: "Governance", pearson_r: 0.64, direction: "same", series_a: fallTrajectory(0.15), series_b: fallTrajectory(0.15) },
    { code: "VA.EST", numeric_id: 21, name: "Voice and Accountability (estimate)", sector: "Governance", pearson_r: 0.61, direction: "same", series_a: sineTrajectory(0.2, 0.2), series_b: sineTrajectory(0.3, 0.2) },
  ],

  // ── S3: hn-ni-1990-2024 (Honduras + Nicaragua, 34y, Central America post-conflict transition)
  "hn-ni-1990-2024": [
    { code: "NY.GDP.MKTP.KD.ZG", numeric_id: 1, name: "GDP growth (annual %)", sector: "Economic", pearson_r: 0.78, direction: "same", series_a: sineTrajectory(0, 0.15), series_b: sineTrajectory(0.2, 0.15) },
    { code: "VA.EST", numeric_id: 21, name: "Voice and Accountability (estimate)", sector: "Governance", pearson_r: 0.71, direction: "same", series_a: sineTrajectory(0.1, 0.17), series_b: sineTrajectory(0.2, 0.17) },
    { code: "PV.EST", numeric_id: 3, name: "Political Stability and Absence of Violence (estimate)", sector: "Governance", pearson_r: 0.74, direction: "same", series_a: sineTrajectory(0.2, 0.16), series_b: sineTrajectory(0.3, 0.16) },
    { code: "SP.DYN.LE00.IN", numeric_id: 4, name: "Life expectancy at birth, total (years)", sector: "Health", pearson_r: 0.86, direction: "same", series_a: riseTrajectory(0.1), series_b: riseTrajectory(0.1) },
    { code: "SH.DYN.MORT", numeric_id: 14, name: "Mortality rate, under-5 (per 1,000 live births)", sector: "Health", pearson_r: 0.84, direction: "same", series_a: fallTrajectory(0.1), series_b: fallTrajectory(0.1) },
    { code: "BX.KLT.DINV.WD.GD.ZS", numeric_id: 40, name: "Foreign direct investment, net inflows (% of GDP)", sector: "Finance", pearson_r: 0.63, direction: "same", series_a: sineTrajectory(0.4, 0.2), series_b: sineTrajectory(0.5, 0.2) },
    { code: "NV.AGR.TOTL.ZS", numeric_id: 33, name: "Agriculture, forestry, and fishing, value added (% of GDP)", sector: "Economic", pearson_r: 0.72, direction: "same", series_a: fallTrajectory(0.13), series_b: fallTrajectory(0.13) },
  ],

  // ── S4: td-cf-2004-2024 (Chad + Central African Republic, 20y, conflict-fragile co-decay)
  "cf-td-2004-2024": [
    { code: "PV.EST", numeric_id: 3, name: "Political Stability and Absence of Violence (estimate)", sector: "Governance", pearson_r: 0.84, direction: "same", series_a: fallTrajectory(0.1), series_b: fallTrajectory(0.11) },
    { code: "MS.MIL.XPND.GD.ZS", numeric_id: 26, name: "Military expenditure (% of GDP)", sector: "Military", pearson_r: 0.79, direction: "same", series_a: riseTrajectory(0.12), series_b: riseTrajectory(0.12) },
    { code: "VA.EST", numeric_id: 21, name: "Voice and Accountability (estimate)", sector: "Governance", pearson_r: 0.77, direction: "same", series_a: fallTrajectory(0.12), series_b: fallTrajectory(0.12) },
    { code: "CC.EST", numeric_id: 25, name: "Control of Corruption (estimate)", sector: "Governance", pearson_r: 0.72, direction: "same", series_a: fallTrajectory(0.13), series_b: fallTrajectory(0.13) },
    { code: "NY.GDP.MKTP.KD.ZG", numeric_id: 1, name: "GDP growth (annual %)", sector: "Economic", pearson_r: 0.68, direction: "same", series_a: sineTrajectory(0, 0.2), series_b: sineTrajectory(0.2, 0.2) },
    { code: "SH.DYN.MORT", numeric_id: 14, name: "Mortality rate, under-5 (per 1,000 live births)", sector: "Health", pearson_r: 0.81, direction: "same", series_a: fallTrajectory(0.12), series_b: fallTrajectory(0.12) },
  ],
};

// ── Pattern metadata catalog ───────────────────────────────────────────────

export const PATTERN_META: PatternMeta[] = [
  {
    slug: "pt-es-1975-2024",
    a_iso2: "pt", b_iso2: "es", a_name: "Portugal", b_name: "Spain",
    start_year: 1975, end_year: 2024, length: 50, pps: 74, avg_correlation: 0.84,
    num_indicators: 25, tier: "XL",
    plausibility_note: "Iberian mirror: EU accession, euro convergence, democracy consolidation, shared austerity arc",
  },
  {
    slug: "pl-cz-1989-2024",
    a_iso2: "pl", b_iso2: "cz", a_name: "Poland", b_name: "Czech Republic",
    start_year: 1989, end_year: 2024, length: 35, pps: 83, avg_correlation: 0.82,
    num_indicators: 17, tier: "L",
    plausibility_note: "Post-communist transition: privatisation, EU accession, democratic consolidation, FDI inflow waves",
  },
  {
    slug: "ke-ug-1990-2024",
    a_iso2: "ke", b_iso2: "ug", a_name: "Kenya", b_name: "Uganda",
    start_year: 1990, end_year: 2024, length: 34, pps: 72, avg_correlation: 0.80,
    num_indicators: 14, tier: "L",
    plausibility_note: "East Africa co-development: trade integration, health improvement, mobile infrastructure, electoral oscillation",
  },
  {
    slug: "eg-tn-1975-2018",
    a_iso2: "eg", b_iso2: "tn", a_name: "Egypt", b_name: "Tunisia",
    start_year: 1975, end_year: 2018, length: 43, pps: 86, avg_correlation: 0.77,
    num_indicators: 10, tier: "M",
    plausibility_note: "MENA authoritarian-transition rhyme: similar governance decay, Arab Spring convergence, post-uprising divergence",
  },
  {
    slug: "ar-ru-1985-2024",
    a_iso2: "ar", b_iso2: "ru", a_name: "Argentina", b_name: "Russia",
    start_year: 1985, end_year: 2024, length: 39, pps: 88, avg_correlation: 0.73,
    num_indicators: 10, tier: "M",
    plausibility_note: "Hyperinflation-collapse-recovery: both experienced successive boom-bust-IMF cycles, corruption oscillation, resource-dependency",
  },
  {
    slug: "gh-sn-1980-2024",
    a_iso2: "gh", b_iso2: "sn", a_name: "Ghana", b_name: "Senegal",
    start_year: 1980, end_year: 2024, length: 44, pps: 84, avg_correlation: 0.81,
    num_indicators: 11, tier: "M",
    plausibility_note: "West Africa democratic consolidation: parallel elections cycles, health gains, agricultural modernisation, FDI attraction",
  },
  {
    slug: "ge-ua-2000-2024",
    a_iso2: "ge", b_iso2: "ua", a_name: "Georgia", b_name: "Ukraine",
    start_year: 2000, end_year: 2024, length: 24, pps: 78, avg_correlation: 0.76,
    num_indicators: 7, tier: "S",
    plausibility_note: "Post-Soviet pro-Western reform: anti-corruption drives, governance improvement, external security pressure, EU association",
  },
  {
    slug: "gr-lb-2000-2022",
    a_iso2: "gr", b_iso2: "lb", a_name: "Greece", b_name: "Lebanon",
    start_year: 2000, end_year: 2022, length: 22, pps: 76, avg_correlation: 0.70,
    num_indicators: 6, tier: "S",
    plausibility_note: "Sovereign debt crisis rhyme: runaway debt, inflation shock, unemployment spike, governance collapse, creditor dependency",
  },
  {
    slug: "hn-ni-1990-2024",
    a_iso2: "hn", b_iso2: "ni", a_name: "Honduras", b_name: "Nicaragua",
    start_year: 1990, end_year: 2024, length: 34, pps: 61, avg_correlation: 0.74,
    num_indicators: 7, tier: "S",
    plausibility_note: "Central America post-conflict political transition: parallel oscillation on governance, health improvement, migration pressure",
  },
  {
    slug: "cf-td-2004-2024",
    a_iso2: "cf", b_iso2: "td", a_name: "Central African Republic", b_name: "Chad",
    start_year: 2004, end_year: 2024, length: 20, pps: 60, avg_correlation: 0.77,
    num_indicators: 6, tier: "S",
    plausibility_note: "Conflict-fragile co-decay: shared instability trajectory, military expenditure growth, governance erosion, health stagnation",
  },
];

// ── Accessors ─────────────────────────────────────────────────────────────

/**
 * Returns the mocked PatternIndicator list for a given pattern slug.
 * Returns null if the slug is not one of the 10 mocked patterns.
 *
 * ONE-LINE SWAP contract: when real `data/cascade/pattern-scdis.json` lands,
 * replace the MOCKED_INDICATORS lookup with a read from that file. The return
 * type (PatternIndicator[] | null) stays identical.
 */
export function getPatternIndicators(slug: string): PatternIndicator[] | null {
  return MOCKED_INDICATORS[slug] ?? null;
}

/** Returns the 10 mocked pattern slugs (for navigation / "Try a sample pattern" affordance). */
export function getMockedPatternSlugs(): string[] {
  return Object.keys(MOCKED_INDICATORS);
}

/** Returns PatternMeta for a slug, or null if not found. */
export function getPatternMeta(slug: string): PatternMeta | null {
  return PATTERN_META.find((m) => m.slug === slug) ?? null;
}

/** Returns the full PatternMeta catalog (all 10). */
export function getAllPatternMeta(): PatternMeta[] {
  return PATTERN_META;
}
