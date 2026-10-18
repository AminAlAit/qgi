# Data Sources, Provenance & Licensing Attribution (Decision D34)

The Quantitative Geopolitical Intelligence (QGI) platform integrates empirical time-series and event datasets from internationally recognized institutional providers. All upstream data ingestion, normalization, and visual presentation adhere strictly to non-commercial academic, research, and portfolio attribution standards.

---

## 1. SIPRI Military Expenditure Database

- **Provider:** Stockholm International Peace Research Institute (SIPRI)
- **URL:** <https://www.sipri.org/databases/milex>
- **Indicators Ingested:** Military expenditure as a share of GDP (`MS.MIL.XPND.GD.ZS`), military expenditure as a share of general government expenditure (`MS.MIL.XPND.ZS`), and constant-USD defense burden trajectories.
- **Attribution & Non-Commercial Compliance (Decision D34):**
  * Data from the SIPRI Military Expenditure Database is used strictly for non-commercial quantitative research and engineering demonstration.
  * Raw SIPRI bulk tables are never resold or redistributed. All analytical views and model tear sheets cite SIPRI as the primary institutional source for military expenditure series.

---

## 2. Armed Conflict Location & Event Data Project (ACLED)

- **Provider:** Armed Conflict Location & Event Data Project (ACLED)
- **URL:** <https://acleddata.com>
- **Citation:** Raleigh, C., Kishi, R., & Linke, A. (2023). *Political instability patterns are obscured by conflict dataset scope conditions, sources, and coding choices.* Humanities and Social Sciences Communications.
- **Compliance:** ACLED event taxonomy aggregates are processed into country-year and monthly risk indicators with explicit source attribution in accordance with ACLED's Terms of Use.

---

## 3. World Bank Open Data (World Development Indicators)

- **Provider:** The World Bank Group
- **URL:** <https://databank.worldbank.org/source/world-development-indicators>
- **License:** Creative Commons Attribution 4.0 International (CC BY 4.0)
- **Indicators Ingested:** Macroeconomic, fiscal, external debt, trade openness, demographic, and governance indicators (`1`–`275` and `1400`–`2399` numeric ID blocks in the QGI Control Surface).

---

## 4. Varieties of Democracy (V-Dem)

- **Provider:** V-Dem Institute, University of Gothenburg
- **URL:** <https://www.v-dem.net>
- **Citation:** Coppedge, Michael, et al. *V-Dem [Country-Year/Country-Date] Dataset v14*, Varieties of Democracy (V-Dem) Project.
- **License:** Creative Commons Attribution 4.0 International (CC BY 4.0)
- **Indicators Ingested:** Electoral democracy (`v2x_polyarchy`), liberal democracy (`v2x_libdem`), judicial constraints, civil liberties, and executive accountability indices (`276`–`314` and `900`–`1399` numeric ID blocks).

---

## 5. Uppsala Conflict Data Program (UCDP)

- **Provider:** Department of Peace and Conflict Research, Uppsala University
- **URL:** <https://ucdp.uu.se>
- **Citation:** Davies, Shawn, Therese Pettersson & Magnus Öberg (2024). *Organized violence 1989–2023, and the prevalence of organized crime groups.* Journal of Peace Research.
- **Indicators Ingested:** State-based, non-state, and one-sided organized violence intensity series (`400`–`449` numeric ID block).

---

## 6. Additional Open Institutional Providers

- **UNHCR Refugee Population Statistics Database:** Forced displacement and cross-border asylum flows (`450`–`499` numeric ID block).
- **FAOSTAT / ILOSTAT / UNDP / OECD:** Food security, labor market, human development, and fiscal structure series (`315`–`399` and `550`–`899` numeric ID blocks).
