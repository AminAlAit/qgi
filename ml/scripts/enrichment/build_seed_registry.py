"""Seed the candidate registry with the 6 new providers' indicators (stage 0).

Builds qgi-data/registries/candidate-registry.json from the curated new-provider
catalog (ILOSTAT/UNHCR/IDMC/UCDP/UNDP/OECD/OWID = 42 candidates), all at status
'candidate'. Re-runnable: adding more catalog rows below and re-running extends
the seed (numeric_ids auto-allocate per provider block). The existing 109
WB/V-Dem/FAOSTAT pool is bootstrapped separately (status 'active') and is not
duplicated here.

Source: docs/specs/methodology/indicator-catalog-detailed.md (extracted 2026-06-25).
Local, $0, no AWS.  Run:  python scripts/enrichment/build_seed_registry.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ENRICH_DIR = Path(__file__).resolve().parent
if str(ENRICH_DIR) not in sys.path:
    sys.path.insert(0, str(ENRICH_DIR))
import registry as rg  # noqa: E402

REPO_ROOT = ENRICH_DIR.parents[1]                       # qgi-ml
OUT = REPO_ROOT.parent / "qgi-data" / "registries" / "candidate-registry.json"

# Each row: (id, provider, name, category, description, provider_meta)
# provider_meta carries fetch hints + coverage/start_year/license for the vet gate.
CANDIDATES: list[tuple[str, str, str, str, str, dict]] = [
    # ---- ILOSTAT (SDMX, sdmx.ilo.org/rest/, CC BY 4.0) ----
    ("IL-01", "ILOSTAT", "Informality rate (% employment in informal economy)", "Economic",
     "Informal economy share; no tax base / safety net; shocks hit informal workers first.",
     {"api": "sdmx", "base_url": "sdmx.ilo.org/rest/", "coverage_countries": 130, "start_year": 2000, "license": "CC BY 4.0"}),
    ("IL-02", "ILOSTAT", "Labor income share of GDP (%)", "Economic",
     "Share of GDP to workers vs capital; declining share -> inequality, polarization.",
     {"api": "sdmx", "base_url": "sdmx.ilo.org/rest/", "coverage_countries": 180, "start_year": 1990, "license": "CC BY 4.0"}),
    ("IL-03", "ILOSTAT", "Mean real wage growth (annual %)", "Economic",
     "Real wage trajectory; declining real wages precede strikes and unrest.",
     {"api": "sdmx", "base_url": "sdmx.ilo.org/rest/", "coverage_countries": 100, "start_year": 2000, "license": "CC BY 4.0"}),
    ("IL-04", "ILOSTAT", "Working poverty rate (% employed below $2.15/day)", "Social",
     "Employed but poor; precedes political violence in developing economies.",
     {"api": "sdmx", "base_url": "sdmx.ilo.org/rest/", "coverage_countries": 140, "start_year": 2000, "license": "CC BY 4.0"}),
    ("IL-05", "ILOSTAT", "Unemployment by education (% tertiary-educated unemployed)", "Social",
     "Educated unemployed: the Arab-Spring demographic.",
     {"api": "sdmx", "base_url": "sdmx.ilo.org/rest/", "coverage_countries": 120, "start_year": 2000, "license": "CC BY 4.0"}),
    ("IL-06", "ILOSTAT", "Gender wage gap (female/male ratio)", "Social",
     "Gender inequality regime signal; tracks social liberalization/backlash.",
     {"api": "sdmx", "base_url": "sdmx.ilo.org/rest/", "coverage_countries": 100, "start_year": 2000, "license": "CC BY 4.0"}),
    ("IL-07", "ILOSTAT", "Excess hours worked (% working >48h/week)", "Economic",
     "Hidden labor stress: underemployment / exploitation signal.",
     {"api": "sdmx", "base_url": "sdmx.ilo.org/rest/", "coverage_countries": 110, "start_year": 2000, "license": "CC BY 4.0"}),
    ("IL-08", "ILOSTAT", "Social protection coverage (% pop with >=1 benefit)", "Social",
     "Share with any safety net; low coverage + shock -> rapid poverty spike.",
     {"api": "sdmx", "base_url": "sdmx.ilo.org/rest/", "coverage_countries": 170, "start_year": 2000, "license": "CC BY 4.0"}),
    ("IL-09", "ILOSTAT", "Social protection expenditure (% GDP)", "Government",
     "Safety-net spending; decline signals austerity -> fiscal change/protests.",
     {"api": "sdmx", "base_url": "sdmx.ilo.org/rest/", "coverage_countries": 150, "start_year": 2000, "license": "CC BY 4.0"}),
    ("IL-10", "ILOSTAT", "Long-term unemployment (12+ months, % labor force)", "Economic",
     "Structural unemployment; precedes long-run instability/populism.",
     {"api": "sdmx", "base_url": "sdmx.ilo.org/rest/", "coverage_countries": 120, "start_year": 2000, "license": "CC BY 4.0"}),
    ("IL-11", "ILOSTAT", "Youth NEET rate (% not in education/employment/training)", "Social",
     "Most dangerous demographic for instability; Arab Spring signature.",
     {"api": "sdmx", "base_url": "sdmx.ilo.org/rest/", "coverage_countries": 150, "start_year": 2000, "license": "CC BY 4.0"}),
    ("IL-12", "ILOSTAT", "Manufacturing employment share (%)", "Economic",
     "Deindustrialization signal; rapid decline -> populist backlash.",
     {"api": "sdmx", "base_url": "sdmx.ilo.org/rest/", "coverage_countries": 160, "start_year": 1990, "license": "CC BY 4.0"}),
    ("IL-13", "ILOSTAT", "Strikes and lockouts (days lost per 1000 workers)", "Social",
     "Direct labor conflict; spikes precede political_violence. Patchy coverage.",
     {"api": "sdmx", "base_url": "sdmx.ilo.org/rest/", "coverage_countries": 80, "start_year": 1969, "license": "CC BY 4.0"}),
    # ---- UNHCR (REST, api.unhcr.org/population/v1/, CC BY 4.0) ----
    ("UN-01", "UNHCR", "Refugees by country of origin (total)", "Demographic",
     "People who fled this country; direct 'how bad inside' measure.",
     {"api": "rest", "endpoint": "api.unhcr.org/population/v1/", "coverage_countries": 200, "start_year": 1951, "license": "CC BY 4.0"}),
    ("UN-02", "UNHCR", "Refugees by country of asylum (total)", "Demographic",
     "Refugees hosted; large influxes strain hosts and trigger secondary instability.",
     {"api": "rest", "endpoint": "api.unhcr.org/population/v1/", "coverage_countries": 200, "start_year": 1951, "license": "CC BY 4.0"}),
    ("UN-03", "UNHCR", "New asylum applications (by origin country)", "Demographic",
     "Leading indicator; precedes recognized refugee counts by 6-24 months.",
     {"api": "rest", "endpoint": "api.unhcr.org/population/v1/", "coverage_countries": 160, "start_year": 2000, "license": "CC BY 4.0"}),
    ("UN-04", "UNHCR", "IDPs (internally displaced persons, total)", "Demographic",
     "Displaced but inside; measures internal conflict severity.",
     {"api": "rest", "endpoint": "api.unhcr.org/population/v1/", "coverage_countries": 80, "start_year": 2000, "license": "CC BY 4.0"}),
    ("UN-05", "UNHCR", "Voluntary refugee returns (annual)", "Demographic",
     "People going home; rising returns = post-conflict stabilization.",
     {"api": "rest", "endpoint": "api.unhcr.org/population/v1/", "coverage_countries": 150, "start_year": 1990, "license": "CC BY 4.0"}),
    ("UN-06", "UNHCR", "Stateless persons (total in country)", "Governance",
     "No nationality; governance failure / ethnic discrimination signal.",
     {"api": "rest", "endpoint": "api.unhcr.org/population/v1/", "coverage_countries": 80, "start_year": 2004, "license": "CC BY 4.0"}),
    # ---- IDMC (REST, api.internal-displacement.org/, free key, CC BY 4.0) ----
    ("ID-01", "IDMC", "New internal displacements by conflict (annual flow)", "Demographic",
     "Newly displaced by conflict; flow = better early warning than stock.",
     {"api": "rest", "endpoint": "api.internal-displacement.org/", "needs_api_key": True, "coverage_countries": 150, "start_year": 2008, "license": "CC BY 4.0"}),
    ("ID-02", "IDMC", "New internal displacements by disaster (annual flow)", "Demographic",
     "Disaster displacement; climate vulnerability signal.",
     {"api": "rest", "endpoint": "api.internal-displacement.org/", "needs_api_key": True, "coverage_countries": 180, "start_year": 2008, "license": "CC BY 4.0"}),
    ("ID-03", "IDMC", "IDP stock by conflict (end-of-year total)", "Demographic",
     "Accumulated conflict displacement; chronic-conflict signal.",
     {"api": "rest", "endpoint": "api.internal-displacement.org/", "needs_api_key": True, "coverage_countries": 60, "start_year": 2008, "license": "CC BY 4.0"}),
    # ---- UCDP (REST, ucdpapi.pcr.uu.se/api/, GW country codes, CC BY 4.0) ----
    ("UC-01", "UCDP", "Battle-related deaths (best estimate, annual)", "Military",
     "Counted conflict fatalities; ground truth for civil_war.",
     {"api": "rest", "endpoint": "ucdpapi.pcr.uu.se/api/", "country_codes": "gw", "coverage_countries": 185, "start_year": 1989, "license": "CC BY 4.0"}),
    ("UC-02", "UCDP", "Number of active conflicts (intrastate + interstate)", "Military",
     "Simultaneous armed conflicts; multi-front wars differ qualitatively.",
     {"api": "rest", "endpoint": "ucdpapi.pcr.uu.se/api/", "country_codes": "gw", "coverage_countries": 185, "start_year": 1946, "license": "CC BY 4.0"}),
    ("UC-03", "UCDP", "Conflict onset (binary: new conflict in country-year)", "Military",
     "Fresh conflict start; doubles as an ML label for civil_war.",
     {"api": "rest", "endpoint": "ucdpapi.pcr.uu.se/api/", "country_codes": "gw", "coverage_countries": 185, "start_year": 1946, "license": "CC BY 4.0"}),
    ("UC-04", "UCDP", "One-sided violence fatalities", "Military",
     "Civilians targeted by state/rebels; precedes full civil_war by 1-2y.",
     {"api": "rest", "endpoint": "ucdpapi.pcr.uu.se/api/", "country_codes": "gw", "coverage_countries": 160, "start_year": 1989, "license": "CC BY 4.0"}),
    # ---- UNDP (CSV, hdr.undp.org/data-center/, CC BY 3.0 IGO) ----
    ("UD-01", "UNDP", "Human Development Index (HDI, 0-1)", "Social",
     "Health+education+income composite; stagnation signals frustration.",
     {"api": "csv", "source": "hdr.undp.org/data-center/", "coverage_countries": 193, "start_year": 1990, "license": "CC BY 3.0 IGO"}),
    ("UD-02", "UNDP", "Inequality-adjusted HDI (IHDI, 0-1)", "Social",
     "HDI discounted for inequality; HDI-IHDI gap = concentrated development.",
     {"api": "csv", "source": "hdr.undp.org/data-center/", "coverage_countries": 150, "start_year": 2010, "license": "CC BY 3.0 IGO"}),
    ("UD-03", "UNDP", "Gender Inequality Index (GII, 0-1)", "Social",
     "Reproductive health + empowerment + labor gaps; tracks authoritarianism.",
     {"api": "csv", "source": "hdr.undp.org/data-center/", "coverage_countries": 170, "start_year": 1995, "license": "CC BY 3.0 IGO"}),
    ("UD-04", "UNDP", "Multidimensional Poverty Index (MPI)", "Social",
     "Non-monetary deprivation; high MPI + stress -> destabilization.",
     {"api": "csv", "source": "hdr.undp.org/data-center/", "coverage_countries": 110, "start_year": 2000, "license": "CC BY 3.0 IGO"}),
    ("UD-05", "UNDP", "Mean years of schooling", "Education",
     "Human capital stock; low attainment + youth bulge = stagnation risk.",
     {"api": "csv", "source": "hdr.undp.org/data-center/", "coverage_countries": 193, "start_year": 1990, "license": "CC BY 3.0 IGO"}),
    ("UD-06", "UNDP", "Expected years of schooling", "Education",
     "Forward-looking schooling; rapid change signals education policy shifts.",
     {"api": "csv", "source": "hdr.undp.org/data-center/", "coverage_countries": 193, "start_year": 1990, "license": "CC BY 3.0 IGO"}),
    ("UD-07", "UNDP", "Gender Development Index (GDI = female HDI / male HDI)", "Social",
     "Gender gap in development; low GDI = institutional rigidity.",
     {"api": "csv", "source": "hdr.undp.org/data-center/", "coverage_countries": 170, "start_year": 1995, "license": "CC BY 3.0 IGO"}),
    # ---- OECD (SDMX, sdmx.oecd.org/public/rest/, 38-80 countries, CC BY 4.0) ----
    ("OE-01", "OECD", "Composite Leading Indicators (CLI)", "Economic",
     "Predicts GDP turning points 6-9 months ahead; best OECD early warning.",
     {"api": "sdmx", "base_url": "sdmx.oecd.org/public/rest/", "freq": "monthly", "coverage_countries": 50, "start_year": 1960, "license": "CC BY 4.0"}),
    ("OE-02", "OECD", "Consumer Confidence Index (CCI)", "Economic",
     "Citizen economic mood; sharp declines precede contractions.",
     {"api": "sdmx", "base_url": "sdmx.oecd.org/public/rest/", "freq": "quarterly", "coverage_countries": 38, "start_year": 1960, "license": "CC BY 4.0"}),
    ("OE-03", "OECD", "Business Confidence Index (BCI)", "Economic",
     "Business investment intent; collapse precedes contraction/election loss.",
     {"api": "sdmx", "base_url": "sdmx.oecd.org/public/rest/", "freq": "quarterly", "coverage_countries": 38, "start_year": 1960, "license": "CC BY 4.0"}),
    ("OE-04", "OECD", "Total social spending (% GDP, SOCX)", "Government",
     "Welfare-state generosity; tracks polarization patterns.",
     {"api": "sdmx", "base_url": "sdmx.oecd.org/public/rest/", "freq": "annual", "coverage_countries": 38, "start_year": 1980, "license": "CC BY 4.0"}),
    ("OE-05", "OECD", "Gini (disposable income, annual)", "Social",
     "Annual Gini where WB Gini has 5-7y gaps; fills a rich-country hole.",
     {"api": "sdmx", "base_url": "sdmx.oecd.org/public/rest/", "freq": "annual", "coverage_countries": 38, "start_year": 1985, "license": "CC BY 4.0"}),
    ("OE-06", "OECD", "Tax revenue (% GDP)", "Finance",
     "Tax-collection capacity = governance capacity; drops signal decay.",
     {"api": "sdmx", "base_url": "sdmx.oecd.org/public/rest/", "freq": "annual", "coverage_countries": 80, "start_year": 1965, "license": "CC BY 4.0"}),
    ("OE-07", "OECD", "Total Factor Productivity growth (annual %)", "Economic",
     "Productivity growth; TFP stagnation precedes economic_crisis.",
     {"api": "sdmx", "base_url": "sdmx.oecd.org/public/rest/", "freq": "quarterly", "coverage_countries": 38, "start_year": 1985, "license": "CC BY 4.0"}),
    # ---- OWID (GitHub CSV, CC BY 4.0) ----
    # OW-02/OW-03 intentionally absent from the catalog (not yet assigned); codes
    # are textual labels only - numeric_ids allocate sequentially regardless.
    ("OW-01", "OWID", "Polity V score (-10 to +10)", "Governance",
     "Autocracy-democracy scale; Polity-vs-VDem divergence is informative. Static after 2018.",
     {"api": "csv", "url": "github.com/owid/owid-datasets", "coverage_countries": 167, "start_year": 1800, "end_year": 2018, "license": "CC BY 4.0"}),
    ("OW-04", "OWID", "CO2 emissions growth rate (annual %, GCP)", "Environment",
     "Rate of change of emissions; boom/contraction signal (WB has level).",
     {"api": "csv", "url": "github.com/owid/owid-datasets", "coverage_countries": 200, "start_year": 1850, "license": "CC BY 4.0"}),
]


def build() -> dict:
    reg = rg.empty_registry()
    for iid, provider, name, category, desc, meta in CANDIDATES:
        rg.add_indicator(reg, indicator_id=iid, provider=provider, name=name,
                         category=category, description=desc, provider_meta=meta,
                         status="candidate")
    errs = rg.validate_registry(reg)
    if errs:
        raise SystemExit("seed invalid:\n" + "\n".join(f"  - {e}" for e in errs))
    return reg


def main() -> int:
    reg = build()
    rg.save_registry(reg, OUT)
    by_provider: dict[str, int] = {}
    for e in reg["indicators"]:
        by_provider[e["provider"]] = by_provider.get(e["provider"], 0) + 1
    print(f"Wrote {len(reg['indicators'])} candidates -> {OUT}")
    print("  by provider:", by_provider)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
