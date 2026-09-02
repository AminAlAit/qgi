/**
 * Indicator-ID → friendly-name resolver for ML recipe data.
 *
 * Used by `lib/buyer-view.ts` when shaping `top_k_indicators[]` into
 * the `BuyerIndicator[]` shape consumed by the V2 detail page.
 *
 * Background: `data/ml-recipe-stack.json` carries `top_k_indicators` whose
 * `indicator_id` is the raw provider code (World Bank dotted ticker like
 * `VC.BTL.DETH`, V-Dem variable like `v2x_polyarchy`) plus an engineered
 * transform suffix (`__diff`, `__lag`, `__zscore`).
 *
 * Strategy:
 *   1. Strip transform suffix → base code
 *   2. Look up base in `data/indexes.json` (curated 259-entry catalog)
 *   3. Fall back to supplementary map for V-Dem + WB codes not yet in
 *      indexes.json (11 codes used by the 13 LOCKed recipes)
 *   4. Append plain-English transform descriptor
 *   5. If nothing resolves, surface the raw base code rather than crash
 *
 * Long-term plan: the bake script (`qgi-ml/#683`) should write an
 * `indicator_label` field alongside `indicator_id` so this lookup is
 * unnecessary. Until then this is the canonical client-side resolver.
 *
 * Isolated test coverage: `lib/__tests__/indicator-labels.test.ts`.
 */
import indexesData from "@/data/indexes.json";
import catalogData from "@/data/indicator-catalog.json";

// ---------------------------------------------------------------------------
// Catalog (indexes.json) — string-id → display name
// ---------------------------------------------------------------------------

const INDEXES_BY_STRING_ID = new Map<string, string>();
for (const idx of indexesData as Array<{ id: string; name: string }>) {
  if (idx.id && idx.name) {
    INDEXES_BY_STRING_ID.set(idx.id, idx.name);
  }
}

// Full active catalogue (250 entries across 8 providers, incl. all World Bank
// names) — the authoritative provider-code → name source. Closes the
// te-fleet-run-2 inline WB-name gap: when a bake leaves indicator_name null for
// a World Bank code, the label still resolves here by code.
const CATALOG_BY_CODE = new Map<string, string>();
{
  const arr = Array.isArray(catalogData)
    ? (catalogData as Array<{ code?: string; name?: string }>)
    : ((catalogData as { indicators?: Array<{ code?: string; name?: string }> })
        .indicators ?? []);
  for (const c of arr) {
    if (c.code && c.name) CATALOG_BY_CODE.set(c.code, c.name);
  }
}

// ---------------------------------------------------------------------------
// Supplementary map for codes used by 13 LOCKed ML recipes that are NOT
// in indexes.json. WB + V-Dem catalog names lifted from provider docs.
//
// Audit: this list mirrors what `bake_ml_recipes_for_frontend.py` writes
// today. When a new validated recipe references a fresh indicator not on
// this list, the resolver falls through to the inferred-prefix label
// ("Indicator FOO_BAR") rather than crashing — add the entry here AND
// file a ticket to put it in `qgi-ml/data/indicator-catalog.csv`.
// ---------------------------------------------------------------------------

const SUPPLEMENTARY_LABELS: Record<string, string> = {
  // ---- World Bank codes missing from indexes.json ----
  "BM.TRF.PWKR.CD.DT": "Personal remittances paid (current US$)",
  "BX.KLT.DINV.WD.GD.ZS": "Foreign direct investment, net inflows (% of GDP)",
  "BX.TRF.PWKR.DT.GD.ZS": "Personal remittances received (% of GDP)",
  "CC.EST": "Control of Corruption (World Bank WGI)",
  "DC.ODA.TOTL.GD.ZS": "Net official development assistance disbursed (% of GDP)",
  "DT.DOD.DSTC.ZS": "Short-term debt (% of total external debt)",
  "DT.INT.DECT.GN.ZS": "Interest payments on external debt (% of GNI)",
  "FB.AST.NPER.ZS": "Bank non-performing loans (% of gross loans)",
  "FP.CPI.TOTL.ZG": "Inflation, consumer prices (annual %)",
  "FX.OWN.TOTL.ZS": "Account ownership at a financial institution (% of population)",
  "GC.DOD.TOTL.GD.ZS": "Central government debt (% of GDP)",
  "GE.EST": "Government Effectiveness (World Bank WGI)",
  "GFDD.DI.01": "Bank deposits (% of GDP)",
  "IC.LGL.DURS": "Time required to enforce a contract (days)",
  "IC.REG.COST.PC.ZS": "Cost of business start-up procedures (% of GNI per capita)",
  "MS.MIL.XPND.GD.ZS": "Military expenditure (% of GDP)",
  "NE.RSB.GNFS.ZS": "External balance on goods and services (% of GDP)",
  "NE.TRD.GNFS.ZS": "Trade (% of GDP)",
  "NV.SRV.TOTL.ZS": "Services, value added (% of GDP)",
  "NY.GDP.MKTP.KD.ZG": "GDP growth (annual %)",
  "NY.GDP.PCAP.KD.ZG": "GDP per capita growth (annual %)",
  "PV.EST": "Political Stability and Absence of Violence (World Bank WGI)",
  "RQ.EST": "Regulatory Quality (World Bank WGI)",
  "SG.GEN.PARL.ZS": "Proportion of seats held by women in national parliaments",
  "SI.POV.GINI": "Gini index",
  "SL.EMP.VULN.ZS": "Vulnerable employment (% of total employment)",
  "SL.UEM.1524.ZS": "Unemployment, youth total (% of labor force ages 15-24)",
  "SL.UEM.TOTL.ZS": "Unemployment, total (% of labor force)",
  "SM.POP.NETM": "Net migration",
  "SM.POP.REFG": "Refugee population by country or territory of asylum",
  "SM.POP.REFG.OR": "Refugee population by country or territory of origin",
  "SM.POP.RHCR.EO": "Refugee population by origin",
  "VC.BTL.DETH": "Battle-related deaths (number of people)",
  "VC.IDP.NWDS": "Internally displaced persons, new displacement (conflict)",
  "VC.IHR.PSRC.P5": "Intentional homicides (per 100,000 people)",

  // ---- V-Dem variables ----
  v2cacamps: "Political polarization (V-Dem)",
  v2clkill: "Freedom from political killings (V-Dem)",
  v2cltort: "Freedom from torture (V-Dem)",
  v2cltrnslw: "Transparent laws with predictable enforcement (V-Dem)",
  v2cseeorgs: "CSO entry and exit freedom (V-Dem)",
  v2csprtcpt: "Civil society participatory environment (V-Dem)",
  v2csreprss: "Civil society repression (V-Dem)",
  v2elintmon: "International election monitoring (V-Dem)",
  v2elfrfair: "Free and fair elections (V-Dem)",
  v2elmulpar: "Multi-party elections (V-Dem)",
  v2exaphogp: "Appointment of head of government (V-Dem)",
  v2excrptps: "Executive corruption (V-Dem)",
  v2exl_legitlead: "Legitimacy of political leadership (V-Dem)",
  v2exremhog: "Removal of head of government (V-Dem)",
  v2ex_hosw: "Head of state — who holds power (V-Dem)",
  v2juncind: "Judicial independence (V-Dem)",
  v2jureform: "Judicial reform attempts (V-Dem)",
  v2lgbicam: "Bicameral legislature (V-Dem)",
  v2lginvstp: "Legislature investigates the executive (V-Dem)",
  v2lgqstexp: "Legislature questions officials in practice (V-Dem)",
  v2mecenefm: "Print and broadcast media censorship (V-Dem)",
  v2pepwrgen: "Power distributed by gender (V-Dem)",
  v2pepwrort: "Power distributed by sexual orientation (V-Dem)",
  v2pepwrses: "Power distributed by social group (V-Dem)",
  v2pepwrsoc: "Power distributed by socioeconomic position (V-Dem)",
  v2psoppaut: "Opposition party autonomy (V-Dem)",
  v2psparban: "Party ban (V-Dem)",
  v2psprlnks: "Party-society linkages (V-Dem)",
  v2stfisccap: "State fiscal capacity (V-Dem)",
  v2svdomaut: "Domestic autonomy / sovereignty (V-Dem)",
  v2x_civlib: "Civil liberties index (V-Dem)",
  v2x_clphy: "Physical violence index (V-Dem)",
  v2x_clpol: "Political civil liberties index (V-Dem)",
  v2x_clpriv: "Private civil liberties index (V-Dem)",
  v2x_corr: "Political corruption index (V-Dem)",
  v2x_freexp_altinf: "Freedom of expression and alternative information (V-Dem)",
  v2x_gender: "Women's political empowerment index (V-Dem)",
  v2x_jucon: "Judicial constraints on executive (V-Dem)",
  v2x_libdem: "Liberal democracy index (V-Dem)",
  v2x_neopat: "Neopatrimonialism index (V-Dem)",
  v2x_partip: "Political participation index (V-Dem)",
  v2x_polyarchy: "Electoral democracy index (V-Dem)",
  v2x_regime: "Regime type (V-Dem)",
  v2x_rule: "Rule of law index (V-Dem)",
  v2xeg_eqprotec: "Equal protection index (V-Dem)",
  v2xel_frefair: "Free and fair elections index (V-Dem)",
  v2xlg_legcon: "Legislative constraints on executive (V-Dem)",
};

// ---------------------------------------------------------------------------
// Transform-suffix descriptors
// ---------------------------------------------------------------------------

const TRANSFORM_LABELS: Record<string, string> = {
  __diff: "year-over-year change",
  __lag: "lagged value",
  __zscore: "z-score",
  __change: "change",
  __delta: "delta",
  __momentum: "momentum",
};

// Sort by length descending so `__zscore` matches before a hypothetical `__z`.
const TRANSFORM_SUFFIXES = Object.keys(TRANSFORM_LABELS).sort(
  (a, b) => b.length - a.length
);

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface ResolverResult {
  /** Friendly label, ready to render to users. */
  label: string;
  /** Whether the base code was found in any catalog (true = high-confidence). */
  found: boolean;
  /** Base code with transform stripped. */
  baseId: string;
  /** Transform suffix in plain English, or `""` if no transform. */
  transformLabel: string;
}

/**
 * Resolve a raw indicator id to a buyer-facing label.
 *
 * Examples:
 *   resolveIndicatorLabel("VC.BTL.DETH__diff")
 *     → { label: "Battle-related deaths (number of people) (year-over-year change)",
 *         found: true, baseId: "VC.BTL.DETH", transformLabel: "year-over-year change" }
 *
 *   resolveIndicatorLabel("v2x_polyarchy__diff")
 *     → { label: "Electoral democracy index (V-Dem) (year-over-year change)", ... }
 *
 *   resolveIndicatorLabel("UNKNOWN__diff")
 *     → { label: "UNKNOWN (year-over-year change)", found: false, ... }
 *
 *   resolveIndicatorLabel("VC.BTL.DETH")  // no transform
 *     → { label: "Battle-related deaths (number of people)", found: true, ... }
 */
export function resolveIndicatorLabel(rawId: string | null | undefined): ResolverResult {
  // 2026-05-30 hardening — fleet-run-1 shap_attribution[] occasionally
  // carries entries with no `indicator_code` (data gap). Returning a
  // safe placeholder here prevents the call from crashing the entire
  // SSR render of every page that imports countries-v4-data.ts.
  if (!rawId) {
    return {
      label: "(indicator code missing)",
      found: false,
      baseId: "",
      transformLabel: "",
    };
  }
  let baseId = rawId;
  let transformLabel = "";
  for (const suffix of TRANSFORM_SUFFIXES) {
    if (rawId.endsWith(suffix)) {
      baseId = rawId.slice(0, -suffix.length);
      transformLabel = TRANSFORM_LABELS[suffix] ?? "";
      break;
    }
  }
  const fromIndexes = INDEXES_BY_STRING_ID.get(baseId);
  const fromSupplementary = SUPPLEMENTARY_LABELS[baseId];
  const baseName = fromIndexes ?? fromSupplementary ?? CATALOG_BY_CODE.get(baseId);
  const found = baseName !== undefined;
  // If no catalog hit, surface the raw base code rather than crash.
  // Analyst readers can still recognize the provider format.
  const namePart = baseName ?? baseId;
  const label = transformLabel ? `${namePart} (${transformLabel})` : namePart;
  return { label, found, baseId, transformLabel };
}

/** Convenience wrapper: just the label string. */
export function getIndicatorLabel(rawId: string | null | undefined): string {
  return resolveIndicatorLabel(rawId).label;
}

/**
 * A trailing "(provider)" baked into some catalog names — e.g. "Control of
 * Corruption (World Bank WGI)" or "Civil society participatory environment
 * (V-Dem)". Matched only when the parenthetical names a known data provider, so
 * a methodology note like "(3-yr change)" is never stripped.
 */
const PROVIDER_PAREN_RE =
  /\s*\([^)]*\b(?:V-?Dem|World Bank|WGI|WDI|FAOSTAT|ILOSTAT|IMF|OECD|Polity|Freedom House|UNESCO|UNDP|WHO)\b[^)]*\)\s*$/i;

/**
 * Drop the trailing "(provider)" from an indicator label. Every panel that
 * lists indicators already shows the provider on its own line, so the
 * parenthetical is duplicate noise: "Civil society participatory environment
 * (V-Dem)" becomes "Civil society participatory environment".
 */
export function stripProviderSuffix(name: string): string {
  return name.replace(PROVIDER_PAREN_RE, "").trim();
}
