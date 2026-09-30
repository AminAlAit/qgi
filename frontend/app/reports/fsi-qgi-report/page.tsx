import type { Metadata } from "next";
import Link from "next/link";
import PrintButton from "./PrintButton";
import { Wordmark } from "@/components/brand/Wordmark";

// T19 #312: the most share-worthy page on the site — full OG + Article
// JSON-LD added so journalists' link unfurls render a proper preview card.
export const metadata: Metadata = {
  title: "FSI Risk Analysis Report · QG Intelligence",
  description:
    "QGI pattern analysis of FSI-flagged countries. Structural analogy assessment across 126 countries and 2.01 billion computed patterns.",
  alternates: {
    canonical: "https://qgintelligence.com/reports/fsi-qgi-report",
  },
  openGraph: {
    title: "FSI Risk Analysis Report · QG Intelligence",
    description:
      "QGI pattern analysis of FSI-flagged countries. Structural analogy assessment across 126 countries.",
    url: "https://qgintelligence.com/reports/fsi-qgi-report",
    siteName: "QG Intelligence",
    type: "article",
    authors: ["Amin Al-Ait"],
  },
  twitter: {
    card: "summary_large_image",
    title: "FSI Risk Analysis Report · QG Intelligence",
    description:
      "QGI pattern analysis of FSI-flagged countries. Structural analogy assessment.",
  },
};

/* ---------------------------------------------------------------------------
 * Inline Markdown content — the FSI demo report.
 * Inlined to avoid cross-repo fs.readFile issues at Vercel build time.
 * Source: docs/specs/external/reports/fsi-demo-april-2026.md
 * --------------------------------------------------------------------------- */

const REPORT_MD = `# Structural Analogy Assessment
## QGI Pattern Analysis of FSI-Flagged Countries

**Pre-computed intelligence report -- April 2026**

Prepared for the [Fund for Peace](https://www.fundforpeace.org/) | [qgintelligence.com](https://qgintelligence.com)

*Classification: Demonstration Report -- Not Commissioned*

---

## 1. Executive Summary

QGI analyzed the economic trajectories of 126 countries using 2.01 billion computed patterns across 58 [World Bank](https://data.worldbank.org/) indicators. Cross-referencing QGI's structural risk scores with the [Fund for Peace's](https://www.fundforpeace.org/) 2023 [Fragile States Index](https://fragilestatesindex.org/) (the latest available dataset), we found the following:

1. **High agreement on the most fragile states.** Of the FSI's top 15 most fragile countries, 11 also produce elevated structural risk signals in QGI (max salience >= 0.8). QGI's purely quantitative approach converges with FSI's expert-blended methodology on the world's most vulnerable states.

2. **10 potential sleeper countries identified.** These countries rank between positions 41 and 130 on FSI (Warning through Elevated tiers) but show high structural similarity to pre-crisis trajectories of historically fragile states across conflict and crisis categories.

3. **Structural twin matching reveals hidden trajectories.** For the most fragile FSI countries, QGI identifies which other countries' historical economic paths they most closely resemble -- and what happened to those reference countries subsequently.

4. **Complementary intelligence.** QGI's indicator-level evidence trail and structural-twin matching augment FSI's qualitative governance assessment. Together they cover both the structural economic dimension (QGI) and the institutional/social dimension (FSI).

---

## 2. Where QGI Agrees with FSI

The following table maps the FSI's top 15 most fragile countries to QGI's structural risk analysis. Agreement is defined as a country producing a max salience score >= 0.8 in QGI's recipe-based scoring system (V1.8.1).

| FSI Rank | Country | FSI Score | QGI Risk Tier | QGI Max Salience | Top Signal Category | Recipe Count |
| :---: | :--- | ---: | :---: | ---: | :--- | ---: |
| 1 | Somalia | 111.9 | HIGH | 2.01 | Civil War & Insurgency | 30,710 |
| 5 | Syria | 107.1 | HIGH | 1.80 | Civil War & Insurgency | 35,620 |
| 6 | Afghanistan | 106.6 | HIGH | 2.00 | Civil War & Insurgency | 326,903 |
| 7 | Sudan | 106.2 | HIGH | 1.68 | Civil War & Insurgency | 29,441 |
| 8 | Central African Republic | 105.7 | MODERATE | 1.18 | Fiscal Policy Change | 373,196 |
| 9 | Chad | 104.6 | HIGH | 1.21 | Civil War & Insurgency | 330,491 |
| 10 | Haiti | 102.9 | HIGH | 1.42 | Political Repression | 181,027 |
| 11 | Ethiopia | 100.4 | HIGH | 1.86 | Civil War & Insurgency | 265,545 |
| 12 | Myanmar | 100.2 | HIGH | 1.88 | Civil War & Insurgency | 73,149 |
| 13 | Mali | 99.5 | MODERATE | 1.07 | Civil War & Insurgency | 79,149 |
| 15 | Nigeria | 98.0 | HIGH | 1.36 | Civil War & Insurgency | 83,574 |

### 2.1 Country Profiles (Top 10 Agreement Countries)

**Somalia** (FSI #1, Score: 111.9)

- QGI Risk Tier: **HIGH** | Max Salience: **2.01**
- Top signals: Civil War & Insurgency (z=2.01, salience=2.01); Terrorist Attack (z=1.19, salience=1.19); Political Repression (z=1.19, salience=0.95)
- Total recipe matches: 30,710
- Somalia's trajectory across multiple World Bank indicators produces 30,710 active recipe matches, with highest structural signals in Civil War & Insurgency and Terrorist Attack.

**Syria** (FSI #5, Score: 107.1)

- QGI Risk Tier: **HIGH** | Max Salience: **1.80**
- Top signals: Civil War & Insurgency (z=1.80, salience=1.80); Terrorist Attack (z=1.44, salience=1.44); Bilateral Treaty (z=2.05, salience=0.82)
- Total recipe matches: 35,620
- Syria's trajectory across multiple World Bank indicators produces 35,620 active recipe matches, with highest structural signals in Civil War & Insurgency and Terrorist Attack.

**Afghanistan** (FSI #6, Score: 106.6)

- QGI Risk Tier: **HIGH** | Max Salience: **2.00**
- Top signals: Civil War & Insurgency (z=2.00, salience=2.00); Terrorist Attack (z=1.77, salience=1.77); Foreign Intervention (z=1.59, salience=1.59)
- Total recipe matches: 326,903
- Afghanistan's trajectory across multiple World Bank indicators produces 326,903 active recipe matches, with highest structural signals in Civil War & Insurgency and Terrorist Attack.

**Sudan** (FSI #7, Score: 106.2)

- QGI Risk Tier: **HIGH** | Max Salience: **1.68**
- Top signals: Civil War & Insurgency (z=1.68, salience=1.68); Military Coup (z=1.20, salience=1.20); Human Rights Violation (z=1.20, salience=0.96)
- Total recipe matches: 29,441
- Sudan's trajectory across multiple World Bank indicators produces 29,441 active recipe matches, with highest structural signals in Civil War & Insurgency and Military Coup.

**Central African Republic** (FSI #8, Score: 105.7)

- QGI Risk Tier: **MODERATE** | Max Salience: **1.18**
- Top signals: Fiscal Policy Change (z=1.96, salience=1.18); Civil War & Insurgency (z=1.09, salience=1.09); Epidemic And Pandemic (z=1.29, salience=1.03)
- Total recipe matches: 373,196
- Central African Republic's trajectory across multiple World Bank indicators produces 373,196 active recipe matches, with highest structural signals in Fiscal Policy Change and Civil War & Insurgency.

**Chad** (FSI #9, Score: 104.6)

- QGI Risk Tier: **HIGH** | Max Salience: **1.21**
- Top signals: Civil War & Insurgency (z=1.21, salience=1.21); Fiscal Policy Change (z=1.38, salience=0.83); Government Formation (z=1.45, salience=0.58)
- Total recipe matches: 330,491
- Chad's trajectory across multiple World Bank indicators produces 330,491 active recipe matches, with highest structural signals in Civil War & Insurgency and Fiscal Policy Change.

**Haiti** (FSI #10, Score: 102.9)

- QGI Risk Tier: **HIGH** | Max Salience: **1.42**
- Top signals: Political Repression (z=1.78, salience=1.42); Migration And Refugees (z=1.64, salience=1.31); Democratic Transition (z=1.59, salience=0.95)
- Total recipe matches: 181,027
- Haiti's trajectory across multiple World Bank indicators produces 181,027 active recipe matches, with highest structural signals in Political Repression and Migration And Refugees.

**Ethiopia** (FSI #11, Score: 100.4)

- QGI Risk Tier: **HIGH** | Max Salience: **1.86**
- Top signals: Civil War & Insurgency (z=1.86, salience=1.86); Migration And Refugees (z=1.15, salience=0.92); Government Formation (z=2.22, salience=0.89)
- Total recipe matches: 265,545
- Ethiopia's trajectory across multiple World Bank indicators produces 265,545 active recipe matches, with highest structural signals in Civil War & Insurgency and Migration And Refugees.

**Myanmar** (FSI #12, Score: 100.2)

- QGI Risk Tier: **HIGH** | Max Salience: **1.88**
- Top signals: Civil War & Insurgency (z=1.88, salience=1.88); Human Rights Violation (z=1.37, salience=1.10); Political Repression (z=1.35, salience=1.08)
- Total recipe matches: 73,149
- Myanmar's trajectory across multiple World Bank indicators produces 73,149 active recipe matches, with highest structural signals in Civil War & Insurgency and Human Rights Violation.

**Mali** (FSI #13, Score: 99.5)

- QGI Risk Tier: **MODERATE** | Max Salience: **1.07**
- Top signals: Civil War & Insurgency (z=1.07, salience=1.07); Fiscal Policy Change (z=1.13, salience=0.68); Government Formation (z=1.46, salience=0.58)
- Total recipe matches: 79,149
- Mali's trajectory across multiple World Bank indicators produces 79,149 active recipe matches, with highest structural signals in Civil War & Insurgency and Fiscal Policy Change.

### 2.2 Signal Heat Map: Top 10 Countries x Key Event Categories

The table below shows salience scores (max across tiers) for each country in five high-impact event categories. Higher scores indicate stronger structural similarity to historical pre-event trajectories.

| Country | Civil War & Insurgency | Terrorist Attack | Mass Protest | Economic Recession | Political Violence |
| :--- | ---: | ---: | ---: | ---: | ---: |
| Somalia | 2.01 | 1.19 | -- | 0.34 | -- |
| Syria | 1.80 | 1.44 | 0.31 | 0.79 | -- |
| Afghanistan | 2.00 | 1.77 | -- | 0.50 | -- |
| Sudan | 1.68 | 0.44 | 0.77 | 0.74 | 0.48 |
| Central African Republic | 1.09 | -- | -- | -- | -- |
| Chad | 1.21 | -- | -- | -- | -- |
| Haiti | 0.82 | -- | 0.66 | -- | -- |
| Ethiopia | 1.86 | 0.55 | 0.39 | 0.53 | -- |
| Myanmar | 1.88 | -- | 0.93 | 0.62 | -- |
| Mali | 1.07 | -- | -- | -- | -- |

*Salience scores represent z-score normalized recipe match strength, weighted by event category severity. Scores above 1.0 indicate strong structural signals; above 1.5 indicate very strong signals.*

---

## 3. Where QGI Sees Signals FSI Has Not Flagged

This is the report's most analytically valuable section. These 'sleeper' countries rank between positions 41 and 130 on FSI -- in the Warning through Elevated tiers -- but produce high structural risk signals in QGI's conflict and crisis categories.

**Selection criteria:**
- FSI rank 41-130 (Warning through Elevated tier; excludes both Alert-tier countries and the most stable states)
- QGI max salience >= 0.8 in at least one high-drama category
- High-drama categories: civil war, terrorist attack, mass protest, political violence, interstate war, ethnic conflict, currency/banking crisis, economic recession, military coup

| FSI Rank | Country | FSI Score | QGI Max Drama Salience | Top Drama Signal | QGI Risk Tier | Recipe Count |
| :---: | :--- | ---: | ---: | :--- | :---: | ---: |
| 53 | Russia | 80.7 | 1.80 | Civil War & Insurgency | HIGH | 79,714 |
| 52 | Turkiye | 81.2 | 1.67 | Civil War & Insurgency | HIGH | 14,966 |
| 100 | Saudi Arabia | 65.3 | 1.62 | Civil War & Insurgency | HIGH | 63,630 |
| 73 | India | 74.1 | 1.56 | Civil War & Insurgency | HIGH | 206,225 |
| 91 | Thailand | 68.0 | 1.51 | Mass Protest | HIGH | 21,540 |
| 50 | Egypt | 81.6 | 1.49 | Terrorist Attack | HIGH | 243,835 |
| 94 | Moldova | 67.4 | 1.43 | Economic Recession | HIGH | 36,153 |
| 98 | Indonesia | 65.6 | 1.43 | Civil War & Insurgency | HIGH | 127,796 |
| 90 | Morocco | 68.2 | 1.31 | Mass Protest | HIGH | 78,314 |
| 79 | Georgia | 71.9 | 1.28 | Civil War & Insurgency | HIGH | 264,059 |

### 3.1 Sleeper Country Profiles

**Russia** (FSI #53, Score: 80.7)

- QGI Risk Tier: **HIGH** | Max Drama Salience: **1.80**
- Top drama signal: **Civil War & Insurgency**
- Top categories: Civil War & Insurgency (1.80); Political Repression (1.44); Terrorist Attack (1.27)
- Total recipe matches: 79,714

  *Why FSI may underweight this:* QGI's pattern engine detects structural trajectory similarities between Russia's current economic indicators and historical pre-crisis paths of other countries. FSI's annual expert-assessed snapshot may not capture these long-horizon economic trajectories.

  *Caveat:* This is a structural signal, not a prediction. It means the economic trajectory resembles a historical pre-crisis path. It does not mean a crisis will occur.

**Turkiye** (FSI #52, Score: 81.2)

- QGI Risk Tier: **HIGH** | Max Drama Salience: **1.67**
- Top drama signal: **Civil War & Insurgency**
- Top categories: Civil War & Insurgency (1.67); Political Repression (1.10); Terrorist Attack (0.92)
- Total recipe matches: 14,966

  *Why FSI may underweight this:* QGI's pattern engine detects structural trajectory similarities between Turkiye's current economic indicators and historical pre-crisis paths of other countries. FSI's annual expert-assessed snapshot may not capture these long-horizon economic trajectories.

  *Caveat:* This is a structural signal, not a prediction. It means the economic trajectory resembles a historical pre-crisis path. It does not mean a crisis will occur.

**Saudi Arabia** (FSI #100, Score: 65.3)

- QGI Risk Tier: **HIGH** | Max Drama Salience: **1.62**
- Top drama signal: **Civil War & Insurgency**
- Top categories: Civil War & Insurgency (1.62); Terrorist Attack (1.16); Bilateral Treaty (0.98)
- Total recipe matches: 63,630

  *Why FSI may underweight this:* QGI's pattern engine detects structural trajectory similarities between Saudi Arabia's current economic indicators and historical pre-crisis paths of other countries. FSI's annual expert-assessed snapshot may not capture these long-horizon economic trajectories.

  *Caveat:* This is a structural signal, not a prediction. It means the economic trajectory resembles a historical pre-crisis path. It does not mean a crisis will occur.

**India** (FSI #73, Score: 74.1)

- QGI Risk Tier: **HIGH** | Max Drama Salience: **1.56**
- Top drama signal: **Civil War & Insurgency**
- Top categories: Civil War & Insurgency (1.56); Terrorist Attack (1.22); Elections & Voting (1.12)
- Total recipe matches: 206,225

  *Why FSI may underweight this:* QGI's pattern engine detects structural trajectory similarities between India's current economic indicators and historical pre-crisis paths of other countries. FSI's annual expert-assessed snapshot may not capture these long-horizon economic trajectories.

  *Caveat:* This is a structural signal, not a prediction. It means the economic trajectory resembles a historical pre-crisis path. It does not mean a crisis will occur.

**Thailand** (FSI #91, Score: 68.0)

- QGI Risk Tier: **HIGH** | Max Drama Salience: **1.51**
- Top drama signal: **Mass Protest**
- Top categories: Mass Protest (1.51); Constitutional Change (1.18); Military Coup (1.13)
- Total recipe matches: 21,540

  *Why FSI may underweight this:* QGI's pattern engine detects structural trajectory similarities between Thailand's current economic indicators and historical pre-crisis paths of other countries. FSI's annual expert-assessed snapshot may not capture these long-horizon economic trajectories.

  *Caveat:* This is a structural signal, not a prediction. It means the economic trajectory resembles a historical pre-crisis path. It does not mean a crisis will occur.

---

## 4. Structural Twins: Deep Dives

QGI's structural-twin capability identifies which other countries' historical economic trajectories a focal country most closely resembles. This section profiles five high-risk countries and their structural analogues.

*Note: Full structural twin analysis requires access to QGI's patterns table (2.01 billion rows). The profiles below use recipe category overlap as a proxy for structural similarity. A commissioned report would include per-indicator correlation analysis and time-shifted trajectory charts.*

### 4.1 Sudan

**FSI Rank:** 7 | **QGI Risk Tier:** HIGH | **Max Salience:** 1.68

**Structural Analogues (by recipe category overlap):**

| Reference Country | Shared Categories | Overlap | Ref. Max Salience | Ref. Risk Tier |
| :--- | :--- | :---: | ---: | :---: |
| Myanmar | Civil War & Insurgency, Human Rights Violation, Mass Protest | 3 | 1.88 | HIGH |
| Thailand | Civil War & Insurgency, Mass Protest, Military Coup | 3 | 1.51 | HIGH |
| Egypt | Civil War & Insurgency, Economic Recession, Mass Protest | 3 | 1.49 | HIGH |

*Sudan's structural risk profile -- particularly in Civil War & Insurgency and Human Rights Violation -- overlaps with Myanmar's pattern signature. Both countries produce elevated recipe matches across 3 shared event categories, suggesting they face similar structural pressures as measured by World Bank economic indicators.*

**Top QGI Signals:**

- Civil War & Insurgency: salience 1.68, z-score 1.68, 961 recipes
- Military Coup: salience 1.20, z-score 1.20, 715 recipes
- Human Rights Violation: salience 0.96, z-score 1.20, 576 recipes
- Mass Protest: salience 0.77, z-score 0.97, 2,179 recipes
- Economic Recession: salience 0.74, z-score 0.93, 1,464 recipes

### 4.2 Haiti

**FSI Rank:** 10 | **QGI Risk Tier:** HIGH | **Max Salience:** 1.42

**Structural Analogues (by recipe category overlap):**

| Reference Country | Shared Categories | Overlap | Ref. Max Salience | Ref. Risk Tier |
| :--- | :--- | :---: | ---: | :---: |
| Ethiopia | Civil War & Insurgency, Epidemic And Pandemic, Migration And Refugees | 3 | 1.86 | HIGH |
| Eritrea | Civil War & Insurgency, Migration And Refugees, Political Repression | 3 | 1.85 | HIGH |
| Central African Republic | Civil War & Insurgency, Epidemic And Pandemic, Migration And Refugees | 3 | 1.18 | MODERATE |

*Haiti's structural risk profile -- particularly in Civil War & Insurgency and Epidemic And Pandemic -- overlaps with Ethiopia's pattern signature. Both countries produce elevated recipe matches across 3 shared event categories, suggesting they face similar structural pressures as measured by World Bank economic indicators.*

**Top QGI Signals:**

- Political Repression: salience 1.42, z-score 1.78, 7,652 recipes
- Migration And Refugees: salience 1.31, z-score 1.64, 5,150 recipes
- Democratic Transition: salience 0.95, z-score 1.59, 4,525 recipes
- Epidemic And Pandemic: salience 0.91, z-score 1.13, 3,306 recipes
- Civil War & Insurgency: salience 0.82, z-score 0.82, 7,912 recipes

### 4.3 Lebanon

**FSI Rank:** 25 | **QGI Risk Tier:** HIGH | **Max Salience:** 2.20

**Structural Analogues (by recipe category overlap):**

| Reference Country | Shared Categories | Overlap | Ref. Max Salience | Ref. Risk Tier |
| :--- | :--- | :---: | ---: | :---: |
| Syria | Bilateral Treaty, Civil War & Insurgency, Economic Recession | 4 | 1.80 | HIGH |
| United States | Bilateral Treaty, Civil War & Insurgency, Economic Recession | 4 | 1.15 | MODERATE |
| Israel | Civil War & Insurgency, Government Formation, Terrorist Attack | 3 | 2.14 | HIGH |

*Lebanon's structural risk profile -- particularly in Bilateral Treaty and Civil War & Insurgency -- overlaps with Syria's pattern signature. Both countries produce elevated recipe matches across 4 shared event categories, suggesting they face similar structural pressures as measured by World Bank economic indicators.*

**Top QGI Signals:**

- Civil War & Insurgency: salience 2.20, z-score 2.20, 7,590 recipes
- Terrorist Attack: salience 0.89, z-score 0.89, 5,418 recipes
- Government Formation: salience 0.87, z-score 2.18, 14,890 recipes
- Economic Recession: salience 0.77, z-score 0.97, 1,786 recipes
- Bilateral Treaty: salience 0.62, z-score 1.55, 9,740 recipes

### 4.4 Pakistan

**FSI Rank:** 32 | **QGI Risk Tier:** HIGH | **Max Salience:** 2.05

**Structural Analogues (by recipe category overlap):**

| Reference Country | Shared Categories | Overlap | Ref. Max Salience | Ref. Risk Tier |
| :--- | :--- | :---: | ---: | :---: |
| Russia | Civil War & Insurgency, Elections & Voting, Political Repression | 4 | 1.80 | HIGH |
| Turkiye | Civil War & Insurgency, Elections & Voting, Political Repression | 4 | 1.67 | HIGH |
| Somalia | Civil War & Insurgency, Political Repression, Terrorist Attack | 3 | 2.01 | HIGH |

*Pakistan's structural risk profile -- particularly in Civil War & Insurgency and Elections & Voting -- overlaps with Russia's pattern signature. Both countries produce elevated recipe matches across 4 shared event categories, suggesting they face similar structural pressures as measured by World Bank economic indicators.*

**Top QGI Signals:**

- Civil War & Insurgency: salience 2.05, z-score 2.05, 3,944 recipes
- Terrorist Attack: salience 1.22, z-score 1.22, 5,922 recipes
- Military Coup: salience 1.21, z-score 1.21, 1,991 recipes
- Political Repression: salience 1.02, z-score 1.28, 1,870 recipes
- Elections & Voting: salience 0.84, z-score 1.41, 5,232 recipes

### 4.5 Russia

**FSI Rank:** 53 | **QGI Risk Tier:** HIGH | **Max Salience:** 1.80

**Structural Analogues (by recipe category overlap):**

| Reference Country | Shared Categories | Overlap | Ref. Max Salience | Ref. Risk Tier |
| :--- | :--- | :---: | ---: | :---: |
| Turkiye | Bilateral Treaty, Civil War & Insurgency, Elections & Voting | 5 | 1.67 | HIGH |
| Pakistan | Civil War & Insurgency, Elections & Voting, Political Repression | 4 | 2.05 | HIGH |
| Syria | Bilateral Treaty, Civil War & Insurgency, Political Repression | 4 | 1.80 | HIGH |

*Russia's structural risk profile -- particularly in Bilateral Treaty and Civil War & Insurgency -- overlaps with Turkiye's pattern signature. Both countries produce elevated recipe matches across 5 shared event categories, suggesting they face similar structural pressures as measured by World Bank economic indicators.*

**Top QGI Signals:**

- Civil War & Insurgency: salience 1.80, z-score 1.80, 8,611 recipes
- Political Repression: salience 1.44, z-score 1.80, 3,983 recipes
- Terrorist Attack: salience 1.27, z-score 1.27, 4,536 recipes
- Bilateral Treaty: salience 0.86, z-score 2.16, 5,850 recipes
- Elections & Voting: salience 0.83, z-score 1.39, 2,147 recipes

---

## 5. Lead-Time Advantage: Historical FSI Deterioration and QGI Signals

This section examines whether QGI's structural signals correlate with subsequent FSI score deteriorations. We identify countries that experienced significant FSI score increases (>= 4.0 points year-over-year, indicating worsening fragility) and check whether QGI produces elevated structural risk signals for those same countries.

### 5.1 FSI Deterioration Events with QGI Structural Signals

| Country | Deterioration Year | FSI Delta | FSI Score (Before -> After) | QGI Top Drama Signal | QGI Drama Salience | QGI Recipe Count |
| :--- | :---: | ---: | :---: | :--- | ---: | ---: |
| Libya | 2012 | +16.2 | 68.7 -> 84.9 | Civil War & Insurgency | 2.00 | 84,083 |
| Lebanon | 2007 | +11.9 | 80.5 -> 92.4 | Civil War & Insurgency | 2.20 | 115,965 |
| Mali | 2013 | +11.4 | 77.9 -> 89.3 | Civil War & Insurgency | 1.07 | 79,149 |
| Sri Lanka | 2023 | +11.0 | 79.3 -> 90.3 | Civil War & Insurgency | 0.73 | 27,143 |
| Syria | 2012 | +8.6 | 85.9 -> 94.5 | Civil War & Insurgency | 1.80 | 35,620 |

### 5.2 Interpretation

The countries above experienced sharp FSI deteriorations (>= 4 points year-over-year) AND produce elevated structural risk signals in QGI's V1.8.1 scoring. This correlation supports the hypothesis that QGI's pattern-based structural analysis captures risk dimensions that manifest in FSI's composite scoring with a time lag.

**Key observations:**

- **Libya**: FSI score ranged from 68.5 (2006) to 97.0 (2021) across 2006-2023. QGI detects 84,083 recipe matches with strongest signals in Civil War & Insurgency (salience: 2.00).
- **Lebanon**: FSI score ranged from 80.5 (2006) to 95.7 (2008) across 2006-2023. QGI detects 115,965 recipe matches with strongest signals in Civil War & Insurgency (salience: 2.20).
- **Mali**: FSI score ranged from 74.6 (2006) to 99.5 (2023) across 2006-2023. QGI detects 79,149 recipe matches with strongest signals in Civil War & Insurgency (salience: 1.07).

*Note: This analysis demonstrates correlation between QGI's structural signals and FSI deterioration events. Causal claims require additional temporal analysis with recipe trigger years from the full Athena pipeline. A commissioned analysis would include per-recipe temporal windows to measure precise lead time.*

### 5.3 FSI Score Trajectories (Selected Countries, 2006-2023)

| Country | 2006 | 2007 | 2008 | 2009 | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Sudan | 112.3 | 113.7 | 113.0 | 112.4 | 111.8 | 108.7 | 109.4 | 111.0 | 110.1 | 110.8 | 111.5 | 110.6 | 108.7 | 108.0 | 104.8 | 105.2 | 107.1 | 106.2 |
| Syria | 88.6 | 88.6 | 90.1 | 89.8 | 87.9 | 85.9 | 94.5 | 97.4 | 101.6 | 107.8 | 110.8 | 110.6 | 111.4 | 111.5 | 110.7 | 110.7 | 108.4 | 107.1 |
| Yemen | 96.6 | 93.2 | 95.4 | 98.1 | 100.0 | 100.3 | 104.8 | 107.0 | 105.4 | 108.2 | 111.5 | 111.1 | 112.7 | 113.5 | 112.4 | 111.7 | 111.7 | 108.9 |
| Myanmar | 96.5 | 97.0 | 100.3 | 101.5 | 99.4 | 98.3 | 96.2 | 94.6 | 94.3 | 94.7 | 96.3 | 95.7 | 96.1 | 94.3 | 94.0 | 93.8 | 100.0 | 100.2 |
| Ukraine | 72.9 | 71.4 | 70.8 | 69.7 | 69.5 | 69.0 | 67.2 | 65.9 | 67.2 | 76.3 | 75.5 | 74.0 | 72.6 | 71.0 | 69.0 | 69.8 | 68.6 | 95.9 |

*FSI scores range 0-120. Higher scores indicate greater fragility. Sharp year-over-year increases indicate rapid deterioration.*

---

## 6. Methodology and Reproducibility

### 6.1 How QGI Works

QGI (Quantitative Geopolitical Intelligence) is a pattern-based structural risk analysis system. It works in three stages:

1. **SCDI Detection.** For every pair of countries and every World Bank indicator, QGI computes the Pearson correlation coefficient between all possible time-window combinations. Pairs with |R| >= 0.7 are flagged as Structurally Correlated Development Indicators (SCDIs). This produces 14.3 billion SCDIs across 214 countries and 58 indicators (as of April 2026).

2. **Pattern Aggregation.** SCDIs sharing the same country pair, start years, and window length are grouped into patterns. Each pattern records how many indicators correlate and at what average strength. The system has computed 2.01 billion patterns.

3. **Recipe Matching.** For each pattern, QGI checks whether both countries experienced the same type of geopolitical event within a +/-15% time window around the pattern's end years. Matching events produce 'recipes' -- structural analogies with verified historical precedent.

### 6.2 Scoring (V1.8.1)

Recipe matches are scored using z-score normalization per country, combined via Reciprocal Rank Fusion (RRF) across four time-horizon tiers (S: 3-8 years, M: 9-20 years, L: 21-40 years, XL: 41+ years). Salience weighting adjusts scores by event category severity (conflict categories weight 1.0, governance categories 0.6-0.8).

### 6.3 Data Provenance

| Data Element | Source | License | Coverage |
| :--- | :--- | :--- | :--- |
| Economic indicators | World Bank Open Data | CC BY 4.0 | 58 indicators, 214 countries, 1960-2024 |
| Geopolitical events | AI-curated with human verification | QGI proprietary | 198 countries, 1950-2025, 71 event categories |
| FSI rankings | [Fund for Peace](https://www.fundforpeace.org/) (public) | Public data | 179 countries, 2006-2023 |

### 6.4 Architectural Decisions

| Decision | Choice | Rationale |
| :--- | :--- | :--- |
| D1: Correlation method | Pearson | Captures linear economic trajectory similarity |
| D2: Prediction scope | Self-prediction only | Each indicator predicts its own future trajectory |
| D3: Country registry | S3-backed Parquet via Glue | Scalable, query-optimized storage |
| D4: Event window | +/-15% of pattern length | Balances precision with recall |
| D5: Match requirement | Both countries must match | Ensures bidirectional structural validity |
| D6: Coordination | DynamoDB counters | Reliable distributed pipeline coordination |
| D7: Prediction flag | Binary (0/1) | Clear interpretability over probability ranges |

### 6.5 Known Limitations

1. **Events are AI-curated.** Geopolitical event histories were generated by AI models and verified by human review. They are not primary-source ground truth.
2. **Annual resolution only.** QGI operates on annual indicator data. Sub-annual dynamics are not captured.
3. **Look-ahead bias exists.** The current SCDI computation (V1) does not enforce strict temporal boundaries. This is a documented known limitation (D8).
4. **Correlation is not causation.** Structural similarity between countries' economic trajectories does not guarantee similar outcomes.
5. **World Bank data lag.** World Bank indicators have a 1-2 year publication lag. The most recent data points may be estimates.
6. **Score compression at extremes.** Z-score normalization can compress distinctions among the most fragile states, which tend to cluster at similar scores.

---

## 7. Data Sources

This report uses the following data sources:

- **QGI country-risks.json** (V1.8.1, generated 2026-04-13): 126 scored countries with salience scores, risk tiers, and recipe counts across 4 time-horizon tiers.
- **FSI 2023 rankings**: 179 countries ranked by the Fund for Peace's [Fragile States Index](https://fragilestatesindex.org/). The 2023 dataset is the latest available in our archive.
- **FSI historical data (2006-2023)**: 145 countries with year-over-year FSI total scores, used for deterioration analysis.
- **QGI salience profiles**: L1/L2 domain-level risk scores for 198 countries.

All QGI data is derived from the QGI V1.8.1 pipeline output (April 2026). FSI data is from publicly available Fund for Peace publications.

---

## 8. Next Steps

### Tier 1: Explore (Free)

- Browse all 126 scored countries at [qgintelligence.com](https://qgintelligence.com)
- Full methodology published at [qgintelligence.com/methodology](https://qgintelligence.com/methodology)
- Country Intelligence Browser with risk tiers and evidence breakdowns

### Tier 2: Collaboration -- FSI-Specific Deep Analysis

QGI runs its full pattern engine against FSI's historical sub-indicator scores (2006-2024), producing per-sub-indicator structural twins with indicator-level sparkline charts and precise lead-time measurements.

- Deliverable: Extended report with per-sub-indicator structural twins
- Timeline: 4-6 weeks from data handoff to report delivery

### Tier 3: Partnership -- Ongoing Intelligence Feed

- Monthly structural analogy updates aligned to FSI methodology
- Custom dashboard showing FSI countries through QGI's structural-twin lens
- White-label option for FFP publications

**Contact:** amin@qgintelligence.com | [qgintelligence.com](https://qgintelligence.com)

---

*Report generated: 2026-04-17 00:10 UTC*

*QGI -- Quantitative Geopolitical Intelligence*

*This report does not constitute investment advice. All structural analogies represent statistical correlations, not causal predictions.*`;

/* ---------------------------------------------------------------------------
 * Minimal Markdown -> HTML parser
 * Handles: h1-h3, bold, italic, tables, unordered/ordered lists,
 * paragraphs, horizontal rules, links, inline code
 * --------------------------------------------------------------------------- */

interface TocEntry {
  id: string;
  title: string;
}

function parseMarkdown(md: string): { html: string; toc: TocEntry[] } {
  const toc: TocEntry[] = [];
  const lines = md.split("\n");
  const htmlParts: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Horizontal rule
    if (/^---+\s*$/.test(line)) {
      htmlParts.push('<hr class="rpt-hr" />');
      i++;
      continue;
    }

    // Headers
    const h1Match = line.match(/^# (.+)$/);
    if (h1Match) {
      htmlParts.push(`<h1 class="rpt-h1">${inline(h1Match[1])}</h1>`);
      i++;
      continue;
    }
    const h2Match = line.match(/^## (.+)$/);
    if (h2Match) {
      const id = slug(h2Match[1]);
      toc.push({ id, title: h2Match[1] });
      htmlParts.push(`<h2 class="rpt-h2" id="${id}">${inline(h2Match[1])}</h2>`);
      i++;
      continue;
    }
    const h3Match = line.match(/^### (.+)$/);
    if (h3Match) {
      htmlParts.push(`<h3 class="rpt-h3">${inline(h3Match[1])}</h3>`);
      i++;
      continue;
    }

    // Table
    if (line.includes("|") && line.trim().startsWith("|")) {
      const tableLines: string[] = [];
      while (
        i < lines.length &&
        lines[i].includes("|") &&
        lines[i].trim().startsWith("|")
      ) {
        tableLines.push(lines[i]);
        i++;
      }
      htmlParts.push(parseTable(tableLines));
      continue;
    }

    // Ordered list (numbered)
    if (/^\d+\.\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s/, ""));
        i++;
      }
      htmlParts.push(
        `<ol class="rpt-ol">${items.map((it) => `<li>${inline(it)}</li>`).join("")}</ol>`
      );
      continue;
    }

    // Unordered list
    if (/^[-*]\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*]\s/.test(lines[i])) {
        items.push(lines[i].replace(/^[-*]\s/, ""));
        i++;
      }
      htmlParts.push(
        `<ul class="rpt-ul">${items.map((it) => `<li>${inline(it)}</li>`).join("")}</ul>`
      );
      continue;
    }

    // Indented list items (starting with spaces then -)
    if (/^\s+[-*]\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s+[-*]\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\s+[-*]\s/, ""));
        i++;
      }
      htmlParts.push(
        `<ul class="rpt-ul rpt-ul-indent">${items.map((it) => `<li>${inline(it)}</li>`).join("")}</ul>`
      );
      continue;
    }

    // Empty line
    if (line.trim() === "") {
      i++;
      continue;
    }

    // Paragraph (collect consecutive non-empty non-special lines)
    const paraLines: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^#{1,3}\s/.test(lines[i]) &&
      !/^---/.test(lines[i]) &&
      !(lines[i].includes("|") && lines[i].trim().startsWith("|")) &&
      !/^\d+\.\s/.test(lines[i]) &&
      !/^[-*]\s/.test(lines[i])
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    if (paraLines.length > 0) {
      htmlParts.push(`<p class="rpt-p">${inline(paraLines.join(" "))}</p>`);
    }
  }

  return { html: htmlParts.join("\n"), toc };
}

/** Inline formatting: bold, italic, links, inline code */
function inline(text: string): string {
  let s = text;
  // Escape HTML entities
  s = s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  // Inline code
  s = s.replace(/`([^`]+)`/g, '<code class="rpt-code">$1</code>');
  // Links [text](url)
  s = s.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" class="rpt-link" target="_blank" rel="noopener noreferrer">$1</a>'
  );
  // Bold+italic
  s = s.replace(/\*\*\*([^*]+)\*\*\*/g, "<strong><em>$1</em></strong>");
  // Bold
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  // Italic
  s = s.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  // -- to em-dash
  s = s.replace(/ -- /g, " &mdash; ");
  return s;
}

function slug(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function parseTable(lines: string[]): string {
  if (lines.length < 2) return "";
  const parseRow = (row: string) =>
    row
      .split("|")
      .map((c) => c.trim())
      .filter((c) => c !== "");

  const headers = parseRow(lines[0]);
  // lines[1] is the separator (alignment) row
  const alignRow = parseRow(lines[1]);
  const aligns = alignRow.map((a) => {
    if (/^:.*:$/.test(a)) return "center";
    if (/.*:$/.test(a)) return "right";
    return "left";
  });
  const bodyRows = lines.slice(2).map(parseRow);

  const thCells = headers
    .map((h, idx) => `<th style="text-align:${aligns[idx] || "left"}">${inline(h)}</th>`)
    .join("");
  const tbodyRows = bodyRows
    .map(
      (row) =>
        `<tr>${row
          .map(
            (cell, idx) =>
              `<td style="text-align:${aligns[idx] || "left"}">${inline(cell)}</td>`
          )
          .join("")}</tr>`
    )
    .join("");

  // Outer .rpt-table-scroll (position:relative, NO overflow) carries the
  // right-edge scroll-fade so it stays pinned at the visible edge; the inner
  // .rpt-table-wrap is the overflow-x:auto scroller. (A fade placed inside the
  // scroller would scroll away with the table and never signal overflow.)
  // The fade is gated to .rpt-table-wide (>3 columns) so narrow 2-3 column
  // tables that fit on a phone never get a content-dimming gradient.
  const wideClass = headers.length > 3 ? " rpt-table-wide" : "";
  return `<div class="rpt-table-scroll${wideClass}"><div class="rpt-table-wrap"><table class="rpt-table"><thead><tr>${thCells}</tr></thead><tbody>${tbodyRows}</tbody></table></div></div>`;
}

/* ---------------------------------------------------------------------------
 * Page component
 * --------------------------------------------------------------------------- */

export default function FSIReportPage() {
  const { html, toc } = parseMarkdown(REPORT_MD);

  return (
    <div
      className="min-h-full"
      style={{ backgroundColor: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      {/* Print stylesheet */}
      <style
        dangerouslySetInnerHTML={{
          __html: `
@media print {
  .print\\:hidden, .rpt-toc-sidebar, header, footer { display: none !important; }
  body, .rpt-page-root { background: #fff !important; color: #111 !important; }
  .rpt-article { max-width: 100% !important; padding: 0 !important; }
  .rpt-h1, .rpt-h2, .rpt-h3 { color: #111 !important; }
  .rpt-table { border-color: #ccc !important; }
  .rpt-table th, .rpt-table td { border-color: #ccc !important; color: #111 !important; background: #fff !important; }
  .rpt-p, .rpt-ul li, .rpt-ol li, em { color: #333 !important; }
  a { color: #111 !important; text-decoration: underline !important; }
  .rpt-hr { border-color: #ccc !important; }
}
          `,
        }}
      />

      {/* Navbar */}
      <header
        className="sticky top-0 z-50 border-b backdrop-blur-md print:hidden"
        style={{
          borderColor: "var(--qgi-border)",
          backgroundColor: "var(--qgi-bg-translucent)",
        }}
      >
        <div className="mx-auto max-w-4xl flex items-center justify-between px-6 py-4">
          <Wordmark variant="report" href="/" title="Home" />
          <nav className="flex items-center gap-4">
            <Link
              href="/methodology"
              className="text-xs tracking-wider uppercase transition-colors hover:text-[var(--qgi-accent)]"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              Methodology
            </Link>
            <Link
              href="/dashboard"
              className="text-xs tracking-wider uppercase px-4 py-2 rounded transition-colors"
              style={{
                backgroundColor: "var(--qgi-accent)",
                color: "var(--qgi-bg)",
              }}
            >
              Open Dashboard
            </Link>
          </nav>
        </div>
      </header>

      {/* Layout: sidebar TOC + main content */}
      <div className="flex justify-center w-full min-w-0">
        {/* Table of Contents sidebar */}
        <aside className="rpt-toc-sidebar hidden xl:block fixed left-0 top-16 w-56 h-[calc(100vh-4rem)] overflow-y-auto px-4 py-8 print:hidden">
          <div
            className="text-[9px] tracking-[0.2em] uppercase mb-4 font-semibold"
            style={{ color: "var(--qgi-accent)" }}
          >
            Contents
          </div>
          <nav className="space-y-1">
            {toc.map((entry) => (
              <a
                key={entry.id}
                href={`#${entry.id}`}
                className="block text-[11px] leading-snug py-1 transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-text-dim)" }}
              >
                {entry.title}
              </a>
            ))}
          </nav>
        </aside>

        {/* Main content */}
        <article
          className="rpt-article mx-auto w-full min-w-0 py-12"
          style={{
            maxWidth: "800px",
            paddingLeft: "clamp(16px,4vw,24px)",
            paddingRight: "clamp(16px,4vw,24px)",
          }}
        >
          {/* Top bar */}
          <div className="flex items-center justify-between mb-8 print:hidden">
            <Link
              href="/reports"
              className="text-xs tracking-wider transition-colors hover:text-[var(--qgi-accent)] flex items-center gap-1"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              &larr; Back to Reports
            </Link>
            <div className="flex items-center gap-3">
              <PrintButton />
            </div>
          </div>

          {/* Rendered report */}
          <div className="rpt-content" dangerouslySetInnerHTML={{ __html: html }} />

          {/* Footer */}
          <div
            className="mt-16 pt-8 border-t text-center"
            style={{ borderColor: "var(--qgi-border)" }}
          >
            <p
              className="text-[10px] tracking-wider"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              Pattern Recurrence Intelligence
            </p>
            <div className="mt-4 flex justify-center gap-4">
              <Link
                href="/reports"
                className="text-xs transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-text-muted)" }}
              >
                Reports
              </Link>
              <Link
                href="/methodology"
                className="text-xs transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-text-muted)" }}
              >
                Methodology
              </Link>
              <Link
                href="/"
                className="text-xs transition-colors hover:text-[var(--qgi-accent)]"
                style={{ color: "var(--qgi-text-muted)" }}
              >
                Home
              </Link>
            </div>
          </div>
        </article>
      </div>

      {/* Global report styles */}
      <style
        dangerouslySetInnerHTML={{
          __html: `
/* Content container — long words/URLs wrap instead of stretching the article.
   break-word (not anywhere) so only over-long tokens break, never mid-word in
   normal prose. */
.rpt-content {
  overflow-wrap: break-word;
  min-width: 0;
}

/* Report typography */
.rpt-h1 {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--qgi-text);
  margin-bottom: 0.25rem;
  line-height: 1.3;
}
.rpt-h2 {
  font-size: 1.35rem;
  font-weight: 600;
  color: var(--qgi-accent);
  margin-top: 3rem;
  margin-bottom: 1rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--qgi-border);
  scroll-margin-top: 5rem;
}
.rpt-h3 {
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--qgi-text);
  margin-top: 2rem;
  margin-bottom: 0.75rem;
}
.rpt-p {
  font-size: 0.875rem;
  line-height: 1.75;
  color: var(--qgi-text-muted);
  margin-bottom: 0.75rem;
}
.rpt-p strong {
  color: var(--qgi-text);
}
.rpt-p em {
  color: var(--qgi-text-dim);
  font-style: italic;
}
.rpt-hr {
  border: none;
  border-top: 1px solid var(--qgi-border);
  margin: 2.5rem 0;
}

/* Lists */
.rpt-ul, .rpt-ol {
  font-size: 0.875rem;
  line-height: 1.75;
  color: var(--qgi-text-muted);
  margin-bottom: 0.75rem;
  padding-left: 1.5rem;
}
.rpt-ul { list-style-type: disc; }
.rpt-ol { list-style-type: decimal; }
.rpt-ul li, .rpt-ol li {
  margin-bottom: 0.25rem;
}
.rpt-ul li strong, .rpt-ol li strong {
  color: var(--qgi-text);
}
.rpt-ul-indent {
  padding-left: 2.5rem;
  margin-top: -0.25rem;
}

/* Links */
.rpt-link {
  color: var(--qgi-accent);
  text-decoration: none;
  border-bottom: 1px solid transparent;
  transition: border-color 0.15s;
}
.rpt-link:hover {
  border-bottom-color: var(--qgi-accent);
}

/* Inline code */
.rpt-code {
  background: var(--qgi-surface-2);
  padding: 0.15em 0.4em;
  border-radius: 3px;
  font-size: 0.85em;
  font-family: var(--font-geist-mono), monospace;
}

/* Tables */
/* Outer wrapper: position anchor for the fade, NO overflow of its own. */
.rpt-table-scroll {
  position: relative;
  margin: 1rem 0 1.5rem;
  max-width: 100%;
}
.rpt-table-wrap {
  overflow-x: auto;
  border-radius: 6px;
  border: 1px solid var(--qgi-border);
  max-width: 100%;
}
/* Right-edge fade scroll affordance — ONLY on wide (>3 column) tables, which
   are the ones that actually overflow a phone. Lives on the NON-scrolling outer
   wrapper so it stays pinned at the visible right edge instead of scrolling off
   with the table. Narrow 2-3 column tables (.rpt-table-scroll without
   .rpt-table-wide) get no fade, so their last column is never dimmed. */
.rpt-table-scroll.rpt-table-wide::after {
  content: '';
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 24px;
  pointer-events: none;
  background: linear-gradient(to right, transparent, var(--qgi-surface, #0d1117));
  border-radius: 0 6px 6px 0;
}
/* Phone-only affordance: hide from ~640px up, where the article is wide enough
   that tables fit and the overlay would otherwise dim real content on desktop. */
@media (min-width: 640px) {
  .rpt-table-scroll.rpt-table-wide::after {
    display: none;
  }
}
.rpt-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
  line-height: 1.5;
}
.rpt-table th {
  background: var(--qgi-surface-2);
  color: var(--qgi-text);
  font-weight: 600;
  padding: 0.6rem 0.75rem;
  border-bottom: 1px solid var(--qgi-border);
  white-space: nowrap;
  font-size: 0.75rem;
  letter-spacing: 0.02em;
}
.rpt-table td {
  background: var(--qgi-surface);
  color: var(--qgi-text-muted);
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--qgi-border);
}
.rpt-table tbody tr:last-child td {
  border-bottom: none;
}
.rpt-table tbody tr:hover td {
  background: var(--qgi-surface-2);
}
.rpt-table td strong {
  color: var(--qgi-text);
}
/* Mobile table density */
@media (max-width: 420px) {
  .rpt-table th,
  .rpt-table td {
    padding: 0.4rem 0.5rem;
  }
  .rpt-table td {
    white-space: normal;
  }
  .rpt-table {
    font-size: 0.72rem;
  }
}

/* TOC sidebar */
.rpt-toc-sidebar {
  border-right: 1px solid var(--qgi-border);
}
          `,
        }}
      />
    </div>
  );
}
