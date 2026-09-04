/**
 * Site-wide marketing/methodology statistics — single source of truth (#431).
 *
 * The QA sweep on 2026-04-24 found 5 different country counts (197, 214, 89)
 * and 2 different indicator counts (58, 69) sprinkled across landing,
 * methodology, dashboard, layout metadata, and JSON-LD — all on neighbouring
 * surfaces of the same site. Marketing copy was hardcoded in each location,
 * which made even a one-time correction painful and a recurring fact-check
 * impossible.
 *
 * This module is the ONE place where pipeline-scope numbers live. Every
 * surface that renders a stat about "QGI scale" should import from here.
 *
 * Provenance of the indicator count (250): the 109 originally ingested (World
 * Bank 69 + FAOSTAT 5 + V-Dem 35, verified 2026-05-31 from the staging data
 * lake) plus 136 activated from the 250-run candidate bench (qgi-ml/enrichment/
 * 250-run/selected-141.json, post-license-audit — of the 141, 5 were excluded:
 * 1 already live + 4 same-measure duplicates) plus 5 vetted top-ups from the
 * reachable pool to reach the round 250. See data/indicator-catalog.json.
 *
 * Disambiguation — three DIFFERENT indicator populations appear on the site;
 * do not collapse them:
 *   - PANEL / CATALOG = 250 across 8 providers (TOTAL_INDICATORS /
 *     TOTAL_INDICATOR_CATALOG). "The indicators we track" — powers the
 *     methodology surfaces (StatCards, taxonomy tree, Glossary, CascadeFlow).
 *   - LIVE SCORING RUN = the current te-fleet vintage's set (run-2: 63, see
 *     data/te-fleet-run-2/MANIFEST.json). Powers the briefing "signals tracked"
 *     footer — deliberately the run number, not the panel.
 *   - "Scored this cycle" is loaded dynamically from country-risks.json and is
 *     NOT a constant — see `getScoredThisCycle()`.
 */

import type { CountryRisksData } from "./country-risks";

/**
 * Number of countries in pipeline scope (qgi_data.countries Athena table).
 * Includes historical/dissolved states; this is the denominator the SCDI
 * grid is computed against.
 */
export const TOTAL_COUNTRIES = 214;

/**
 * Number of indicators in the active panel. 250 across 8 providers: the 109
 * originally ingested (World Bank 69 + FAOSTAT 5 + V-Dem 35, verified
 * 2026-05-31) plus 136 activated from the 250-run candidate bench
 * (qgi-ml/enrichment/250-run/selected-141.json, post-license-audit set — of the
 * 141, 5 were excluded: 1 already live [GC.TAX.TOTL.GD.ZS] + 4 same-measure
 * duplicates [FB.BNK.NPLS.ZS, FS-001, v2x_freexp, v2x_execorr]) plus 5 vetted
 * top-ups from the reachable pool (SI.POV.DDAY, SL.EMP.VULN.ZS, SH.STA.ODFC.ZS,
 * FS-019, LOSS). Union breakdown: WB 99 · V-Dem 90 · UCDP 19 · FAOSTAT 13 ·
 * UNHCR 11 · ILOSTAT 8 · OWID 5 · UNDP 5. Not every indicator yet feeds a trend;
 * the ones still "tracked, not yet recipe-carrying" are marked recipe_count:0 in
 * data/indicator-catalog.json, which powers /methodology/indicators.
 */
export const TOTAL_INDICATORS = 250;

/**
 * Total indicators in the active catalog (data/indicator-catalog.json). Equal
 * to the panel count above — the display catalog is now the panel.
 */
export const TOTAL_INDICATOR_CATALOG = 250;

/**
 * Distinct providers feeding the indicator panel. Must equal the number of keys
 * in data/methodology-stats.json `indicator_breakdown` (locked by the
 * site-stats test): World Bank, V-Dem, UCDP, FAOSTAT, UNHCR, ILOSTAT, OWID, UNDP.
 */
export const TOTAL_INDICATOR_PROVIDERS = 8;

/**
 * Countries covered by the live NEWS layer (Risk Board "Topics" + per-country
 * Live Pulse). This is the SINGLE source of truth for the news-coverage count
 * in copy — update it here (one line) when expanding coverage. The authoritative
 * country LIST lives in the pipeline registry (qgi-gdelt-poc/news_countries.json)
 * and flows to the board via data/hf-topics.json; this constant must match
 * hf-topics.json `countries.length`. See the news-expansion runbook.
 */
export const NEWS_COUNTRIES = 30;

/**
 * UN-recognized states. Constant scope descriptor — appears in marketing
 * copy that frames "global coverage" rather than pipeline arithmetic.
 */
export const UN_STATES = 197;

/**
 * SCDI rows in the master grid (Pearson |r| >= 0.7). 14.3B as of the V1.8.1
 * pipeline run. The next regen will refresh this; bumping requires a
 * coordinated update with the methodology blog post.
 */
export const TOTAL_SCDIS = "14.3B";

/**
 * Patterns computed by the V1.9 backtest (recipe windows × predicted vs
 * actual). 2.01B as of qgi-ml/backtest_v19_results.json.
 */
export const TOTAL_PATTERNS = "2.01B";

/**
 * Scoring version currently live on qgintelligence.com.
 */
export const SCORING_VERSION = "V1.9.1";

/**
 * Current data vintage (max year in the World Bank data we ingested).
 */
export const DATA_VINTAGE_YEAR = 2024;

/**
 * Canonical one-line scope sentence used in OG/social/meta descriptions.
 * Reusing this string — rather than copying it five times — keeps the
 * count drift QA caught from re-emerging.
 *
 * 2026-05-24: "economic data" → "open-source indicators" (qgi-aws-tf#877).
 * The indicator panel spans V-Dem governance/regime + FAOSTAT + ILOSTAT
 * + World Bank, not solely economic data; OSINT framing matches the rest
 * of the public surface.
 */
export const CANONICAL_SCOPE_SENTENCE = `Historical precedents across ${TOTAL_COUNTRIES} countries and ${TOTAL_INDICATORS} open-source indicators.`;

/**
 * Number of recipes currently LOCKed by the ML pipeline. Used by the
 * dashboard's recipe-progress display + the methodology page's stat
 * cards. 13 LOCKed as of 2026-05-21 (post-KI-2 amendment; territorial_
 * disputes was FALSIFIED). foreign_intervention graduated 2026-05-23 via
 * the F-ML-1 similarity-as-risk layer (separate from LOCK count which
 * is the calibrated-classifier dive).
 *
 * Update when a recipe is added to or removed from the LOCK set. CI
 * assertion in lib/__tests__/site-stats.test.ts will fail if this drifts
 * from the recipe manifest (TODO #878 follow-up).
 */
export const TOTAL_LOCKED = 13;

/**
 * Read the count of countries that received a risk tier in the current
 * pipeline cycle from country-risks.json. This is data-driven (it
 * fluctuates between cycles as more countries clear the scoring floor).
 */
export function getScoredThisCycle(data: CountryRisksData): number {
  return Object.values(data.countries).filter((c) => c.overall_risk_tier).length;
}
