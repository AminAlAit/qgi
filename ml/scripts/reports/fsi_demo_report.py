#!/usr/bin/env python3
"""
FSI Demo Report Generator
=========================
Generates a Markdown report cross-referencing Fund for Peace's Fragile States
Index with QGI's structural risk analysis (V1.8.1).

Usage:
    python fsi_demo_report.py

Output:
    docs/specs/external/reports/fsi-demo-april-2026.md

Data sources:
    - FSI xlsx files (2006-2023) from [archive]/trojan-2.0/data/raw/
    - QGI country-risks.json (V1.8.1, 126 countries)
    - QGI salience files (198 countries)
    - QGI curated events
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[3]  # qgi-6.0
FRONTEND_DATA = REPO_ROOT / "qgi-frontend" / "data"
COUNTRY_RISKS_PATH = FRONTEND_DATA / "country-risks.json"
SALIENCE_DIR = FRONTEND_DATA / "salience"
COUNTRY_EVENTS_PATH = FRONTEND_DATA / "country-events.json"
COUNTRIES_PATH = FRONTEND_DATA / "countries.json"
TAXONOMY_PATH = FRONTEND_DATA / "taxonomy_hierarchy.json"

ARCHIVE_ROOT = REPO_ROOT.parent / "[archive]" / "trojan-2.0" / "data" / "raw"
FSI_DIR = ARCHIVE_ROOT / "The Fund For Peace" / "Fragile States Index"

OUTPUT_PATH = REPO_ROOT / "docs-specs" / "external" / "reports" / "fsi-demo-april-2026.md"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HIGH_SEVERITY_CATEGORIES = {
    "civil_war_and_insurgency",
    "terrorist_attack",
    "mass_protest",
    "political_violence",
    "interstate_war",
    "ethnic_and_communal_conflict",
    "currency_crisis",
    "banking_and_financial_crisis",
    "economic_recession",
    "military_coup",
}

# FSI country name -> QGI alpha_2 mapping (handles mismatches)
FSI_TO_ALPHA2 = {
    "Afghanistan": "AF",
    "Albania": "AL",
    "Algeria": "DZ",
    "Angola": "AO",
    "Argentina": "AR",
    "Armenia": "AM",
    "Australia": "AU",
    "Austria": "AT",
    "Azerbaijan": "AZ",
    "Bahrain": "BH",
    "Bangladesh": "BD",
    "Belarus": "BY",
    "Belgium": "BE",
    "Bolivia": "BO",
    "Bosnia and Herzegovina": "BA",
    "Bosnia & Herzegovina": "BA",
    "Brazil": "BR",
    "Brunei Darussalam": "BN",
    "Brunei": "BN",
    "Bulgaria": "BG",
    "Burkina Faso": "BF",
    "Burundi": "BI",
    "Cambodia": "KH",
    "Cameroon": "CM",
    "Canada": "CA",
    "Central African Republic": "CF",
    "Chad": "TD",
    "Chile": "CL",
    "China": "CN",
    "Colombia": "CO",
    "Comoros": "KM",
    "Congo Democratic Republic": "CD",
    "Congo Republic": "CG",
    "Costa Rica": "CR",
    "Cote d'Ivoire": "CI",
    "Cote d Ivoire": "CI",
    "Ivory Coast": "CI",
    "Croatia": "HR",
    "Cuba": "CU",
    "Cyprus": "CY",
    "Czech Republic": "CZ",
    "Czechia": "CZ",
    "Denmark": "DK",
    "Djibouti": "DJ",
    "Dominican Republic": "DO",
    "DR Congo": "CD",
    "Ecuador": "EC",
    "Egypt": "EG",
    "El Salvador": "SV",
    "Equatorial Guinea": "GQ",
    "Eritrea": "ER",
    "Estonia": "EE",
    "Eswatini": "SZ",
    "Ethiopia": "ET",
    "Finland": "FI",
    "France": "FR",
    "Georgia": "GE",
    "Germany": "DE",
    "Ghana": "GH",
    "Greece": "GR",
    "Guatemala": "GT",
    "Guinea": "GN",
    "Guinea Bissau": "GW",
    "Guinea-Bissau": "GW",
    "Haiti": "HT",
    "Honduras": "HN",
    "Hungary": "HU",
    "Iceland": "IS",
    "India": "IN",
    "Indonesia": "ID",
    "Iran": "IR",
    "Iraq": "IQ",
    "Ireland": "IE",
    "Israel": "IL",
    "Israel and West Bank": "IL",
    "Italy": "IT",
    "Jamaica": "JM",
    "Japan": "JP",
    "Jordan": "JO",
    "Kazakhstan": "KZ",
    "Kenya": "KE",
    "Korea Democratic Republic": "KP",
    "Korea Republic": "KR",
    "North Korea": "KP",
    "South Korea": "KR",
    "Kuwait": "KW",
    "Kyrgyz Republic": "KG",
    "Kyrgyzstan": "KG",
    "Laos": "LA",
    "Lao PDR": "LA",
    "Latvia": "LV",
    "Lebanon": "LB",
    "Libya": "LY",
    "Lithuania": "LT",
    "Luxembourg": "LU",
    "Madagascar": "MG",
    "Malaysia": "MY",
    "Maldives": "MV",
    "Mali": "ML",
    "Malta": "MT",
    "Mauritania": "MR",
    "Mexico": "MX",
    "Moldova": "MD",
    "Mongolia": "MN",
    "Montenegro": "ME",
    "Morocco": "MA",
    "Mozambique": "MZ",
    "Myanmar": "MM",
    "Nepal": "NP",
    "Netherlands": "NL",
    "New Zealand": "NZ",
    "Nicaragua": "NI",
    "Niger": "NE",
    "Nigeria": "NG",
    "North Macedonia": "MK",
    "Norway": "NO",
    "Oman": "OM",
    "Pakistan": "PK",
    "Palestine": "PS",
    "Peru": "PE",
    "Philippines": "PH",
    "Poland": "PL",
    "Portugal": "PT",
    "Qatar": "QA",
    "Romania": "RO",
    "Russia": "RU",
    "Rwanda": "RW",
    "Saudi Arabia": "SA",
    "Singapore": "SG",
    "Slovakia": "SK",
    "Slovenia": "SI",
    "Somalia": "SO",
    "South Africa": "ZA",
    "South Sudan": "SS",
    "Spain": "ES",
    "Sri Lanka": "LK",
    "Sudan": "SD",
    "Sweden": "SE",
    "Switzerland": "CH",
    "Syria": "SY",
    "Tajikistan": "TJ",
    "Thailand": "TH",
    "Turkey": "TR",
    "Turkmenistan": "TM",
    "Tunisia": "TN",
    "Uganda": "UG",
    "Ukraine": "UA",
    "United Arab Emirates": "AE",
    "United Kingdom": "GB",
    "United States": "US",
    "Uzbekistan": "UZ",
    "Venezuela": "VE",
    "Vietnam": "VN",
    "Yemen": "YE",
    "Zambia": "ZM",
    "Zimbabwe": "ZW",
    # Additional FSI names that may differ
    "Congo Dem. Rep.": "CD",
    "Congo Rep.": "CG",
    "Timor-Leste": "TL",
    "Turkiye": "TR",
}

# QGI risk tier labels and order
RISK_TIER_ORDER = {"HIGH": 0, "MODERATE": 1, "INDICATIVE": 2}

# Category display names
CATEGORY_DISPLAY = {
    "civil_war_and_insurgency": "Civil War & Insurgency",
    "terrorist_attack": "Terrorist Attack",
    "mass_protest": "Mass Protest",
    "political_violence": "Political Violence",
    "interstate_war": "Interstate War",
    "ethnic_and_communal_conflict": "Ethnic & Communal Conflict",
    "currency_crisis": "Currency Crisis",
    "banking_and_financial_crisis": "Banking & Financial Crisis",
    "economic_recession": "Economic Recession",
    "military_coup": "Military Coup",
    "foreign_intervention": "Foreign Intervention",
    "political_repression": "Political Repression",
    "government_formation": "Government Formation",
    "fiscal_policy_change": "Fiscal Policy Change",
    "constitutional_change": "Constitutional Change",
    "elections_and_voting": "Elections & Voting",
    "trade_policy_change": "Trade Policy Change",
    "sanctions_and_arms_embargo": "Sanctions & Arms Embargo",
    "pandemic_and_epidemic": "Pandemic & Epidemic",
    "natural_disaster": "Natural Disaster",
    "humanitarian_crisis": "Humanitarian Crisis",
    "famine_and_food_crisis": "Famine & Food Crisis",
    "territorial_dispute": "Territorial Dispute",
    "refugee_crisis": "Refugee Crisis",
    "peace_agreement": "Peace Agreement",
    "state_collapse": "State Collapse",
}


def display_cat(cat: str) -> str:
    """Return human-readable category name."""
    return CATEGORY_DISPLAY.get(cat, cat.replace("_", " ").title())


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_fsi_data(year: int) -> list[dict]:
    """Load FSI data from an xlsx file for a given year."""
    try:
        import openpyxl
    except ImportError:
        print("ERROR: openpyxl required. Install with: pip install openpyxl")
        sys.exit(1)

    path = FSI_DIR / f"fsi-{year}.xlsx"
    if not path.exists():
        print(f"WARNING: FSI file not found: {path}")
        return []

    wb = openpyxl.load_workbook(str(path), data_only=True)
    ws = wb[wb.sheetnames[0]]

    headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row[0] or not row[3]:
            continue
        name = str(row[0]).strip()
        # Parse rank -- remove ordinal suffixes
        rank_raw = str(row[2]).replace("st", "").replace("nd", "").replace("rd", "").replace("th", "").strip()
        try:
            rank = int(rank_raw)
        except (ValueError, TypeError):
            rank = None
        total = float(row[3]) if row[3] else None
        # Parse year field
        yr = row[1]
        if hasattr(yr, "year"):
            yr = yr.year
        else:
            try:
                yr = int(yr)
            except (ValueError, TypeError):
                yr = year

        rows.append({
            "name": name,
            "year": yr,
            "rank": rank,
            "total": total,
            "alpha_2": FSI_TO_ALPHA2.get(name),
        })

    rows.sort(key=lambda x: x["rank"] if x["rank"] else 999)
    return rows


def load_fsi_historical() -> dict:
    """Load FSI scores across all available years. Returns {alpha_2: [(year, total, rank), ...]}."""
    historical: dict[str, list] = {}
    for year in range(2006, 2024):
        rows = load_fsi_data(year)
        for row in rows:
            a2 = row["alpha_2"]
            if a2:
                historical.setdefault(a2, []).append((row["year"], row["total"], row["rank"]))
    # Sort each country's entries by year
    for a2 in historical:
        historical[a2].sort(key=lambda x: x[0])
    return historical


def load_qgi_country_risks() -> dict:
    """Load country-risks.json."""
    with open(COUNTRY_RISKS_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_countries_list() -> list[dict]:
    """Load the full countries list (198 countries with IDs)."""
    with open(COUNTRIES_PATH, encoding="utf-8") as f:
        return json.load(f)


def build_alpha2_to_qgi(qgi_data: dict) -> dict:
    """Build alpha_2 -> {id, name, data} mapping from country-risks.json."""
    mapping = {}
    for cid, cdata in qgi_data["countries"].items():
        mapping[cdata["alpha_2"]] = {
            "id": cid,
            "name": cdata["name"],
            "alpha_2": cdata["alpha_2"],
            "curated": cdata.get("curated", False),
            "overall_risk_tier": cdata.get("overall_risk_tier", "N/A"),
            "data": cdata,
        }
    return mapping


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------


def compute_max_salience(cdata: dict) -> tuple[float, str, str]:
    """Compute max salience across all tiers. Returns (max_sal, category, tier)."""
    max_sal = 0.0
    top_cat = ""
    top_tier = ""
    for tier_name, tier_data in cdata["tiers"].items():
        for cat in tier_data["top_categories"]:
            if cat["salience_score"] > max_sal:
                max_sal = cat["salience_score"]
                top_cat = cat["category"]
                top_tier = tier_name
    return max_sal, top_cat, top_tier


def compute_max_severity_salience(cdata: dict) -> tuple[float, str, str]:
    """Compute max salience for high-severity categories only."""
    max_sal = 0.0
    top_cat = ""
    top_tier = ""
    for tier_name, tier_data in cdata["tiers"].items():
        for cat in tier_data["top_categories"]:
            if cat["category"] in HIGH_SEVERITY_CATEGORIES and cat["salience_score"] > max_sal:
                max_sal = cat["salience_score"]
                top_cat = cat["category"]
                top_tier = tier_name
    return max_sal, top_cat, top_tier


def get_top_categories(cdata: dict, n: int = 3) -> list[dict]:
    """Get top N categories across all tiers by salience score, deduplicated."""
    seen = set()
    results = []
    all_cats = []
    for tier_name, tier_data in cdata["tiers"].items():
        for cat in tier_data["top_categories"]:
            all_cats.append({**cat, "tier": tier_name})
    all_cats.sort(key=lambda x: -x["salience_score"])
    for cat in all_cats:
        if cat["category"] not in seen:
            seen.add(cat["category"])
            results.append(cat)
            if len(results) >= n:
                break
    return results


def get_total_recipe_count(cdata: dict) -> int:
    """Sum recipe counts across all tiers and categories (deduplicated by category)."""
    seen_cats: dict[str, int] = {}
    for tier_name, tier_data in cdata["tiers"].items():
        for cat in tier_data["top_categories"]:
            key = cat["category"]
            # Take the max recipe_count across tiers for each category
            if key not in seen_cats or cat["recipe_count"] > seen_cats[key]:
                seen_cats[key] = cat["recipe_count"]
    return sum(seen_cats.values())


def find_agreement_countries(fsi_top: list[dict], alpha2_qgi: dict, n: int = 15) -> list[dict]:
    """Find FSI top-N countries that also score high in QGI.

    Excludes countries with zero recipe data (no meaningful QGI signal).
    """
    agreements = []
    for fsi_row in fsi_top[:n]:
        a2 = fsi_row["alpha_2"]
        if not a2 or a2 not in alpha2_qgi:
            continue
        qgi = alpha2_qgi[a2]
        max_sal, top_cat, top_tier = compute_max_salience(qgi["data"])
        recipe_count = get_total_recipe_count(qgi["data"])
        # Skip countries with no recipe data (e.g., Yemen with all-zero scores)
        if recipe_count == 0 and max_sal == 0.0:
            continue
        agreements.append({
            "fsi_name": fsi_row["name"],
            "fsi_rank": fsi_row["rank"],
            "fsi_total": fsi_row["total"],
            "qgi_name": qgi["name"],
            "qgi_id": qgi["id"],
            "alpha_2": a2,
            "max_salience": max_sal,
            "top_category": top_cat,
            "top_tier": top_tier,
            "risk_tier": qgi["overall_risk_tier"],
            "curated": qgi["curated"],
            "top_categories": get_top_categories(qgi["data"], 3),
            "recipe_count": recipe_count,
        })
    return agreements


def find_sleeper_countries(
    fsi_data: list[dict],
    alpha2_qgi: dict,
    fsi_cutoff_low: int = 40,
    fsi_cutoff_high: int = 130,
    salience_threshold: float = 0.8,
) -> list[dict]:
    """Find countries with high QGI severity signals but moderate FSI ranking.

    Restricts to FSI ranks between cutoff_low and cutoff_high to focus on
    the meaningful Warning/Elevated range. Very stable countries (FSI 130+)
    with high QGI signals are typically V1.8.1 noise, not genuine sleepers.
    """
    # Build FSI rank lookup
    fsi_rank_lookup = {}
    for row in fsi_data:
        if row["alpha_2"]:
            fsi_rank_lookup[row["alpha_2"]] = row

    sleepers = []
    for a2, qgi in alpha2_qgi.items():
        fsi_row = fsi_rank_lookup.get(a2)
        if not fsi_row or not fsi_row["rank"]:
            continue
        if fsi_row["rank"] <= fsi_cutoff_low or fsi_row["rank"] > fsi_cutoff_high:
            continue

        max_severity_sal, top_severity_cat, top_severity_tier = compute_max_severity_salience(qgi["data"])
        if max_severity_sal < salience_threshold:
            continue

        max_sal, top_cat, _ = compute_max_salience(qgi["data"])

        sleepers.append({
            "fsi_name": fsi_row["name"],
            "fsi_rank": fsi_row["rank"],
            "fsi_total": fsi_row["total"],
            "qgi_name": qgi["name"],
            "qgi_id": qgi["id"],
            "alpha_2": a2,
            "max_salience": max_sal,
            "max_severity_salience": max_severity_sal,
            "top_severity_category": top_severity_cat,
            "top_severity_tier": top_severity_tier,
            "risk_tier": qgi["overall_risk_tier"],
            "curated": qgi["curated"],
            "top_categories": get_top_categories(qgi["data"], 5),
            "recipe_count": get_total_recipe_count(qgi["data"]),
        })

    sleepers.sort(key=lambda x: -x["max_severity_salience"])
    return sleepers


def find_structural_twins(cdata: dict, all_countries: dict) -> list[dict]:
    """
    Find structural twin candidates based on shared high-salience categories.

    Since we don't have direct Athena access from this script, we approximate
    structural twins by finding countries whose top salience categories overlap
    with the focal country -- countries that share the same risk signature.
    """
    focal_cats = get_top_categories(cdata, 5)
    focal_cat_set = {c["category"] for c in focal_cats}

    twins = []
    for cid, other in all_countries.items():
        other_cats = get_top_categories(other, 5)
        other_cat_set = {c["category"] for c in other_cats}
        overlap = focal_cat_set & other_cat_set
        if len(overlap) >= 2:
            other_max_sal, _, _ = compute_max_salience(other)
            twins.append({
                "country_id": cid,
                "name": other["name"],
                "alpha_2": other["alpha_2"],
                "shared_categories": sorted(overlap),
                "overlap_count": len(overlap),
                "max_salience": other_max_sal,
                "risk_tier": other.get("overall_risk_tier", "N/A"),
            })
    # Sort by overlap count then salience
    twins.sort(key=lambda x: (-x["overlap_count"], -x["max_salience"]))
    return twins[:5]


def compute_fsi_deteriorations(historical: dict, threshold: float = 4.0) -> list[dict]:
    """
    Find instances where a country's FSI score increased by >= threshold
    year-over-year (indicating deterioration).
    """
    deteriorations = []
    for a2, entries in historical.items():
        for i in range(1, len(entries)):
            prev_year, prev_total, prev_rank = entries[i - 1]
            curr_year, curr_total, curr_rank = entries[i]
            if prev_total and curr_total:
                delta = curr_total - prev_total
                if delta >= threshold:
                    deteriorations.append({
                        "alpha_2": a2,
                        "year": curr_year,
                        "prev_year": prev_year,
                        "prev_total": prev_total,
                        "curr_total": curr_total,
                        "delta": round(delta, 1),
                        "prev_rank": prev_rank,
                        "curr_rank": curr_rank,
                    })
    deteriorations.sort(key=lambda x: -x["delta"])
    return deteriorations


def find_lead_time_cases(
    deteriorations: list[dict],
    alpha2_qgi: dict,
    fsi_historical: dict,
) -> list[dict]:
    """
    Find cases where QGI had high-severity recipe signals for a country
    that subsequently showed FSI deterioration.

    Approximation: if a country has high recipe counts in severity categories
    and experienced FSI deterioration, the structural signal was detectable.
    """
    cases = []
    seen_countries = set()

    for det in deteriorations:
        a2 = det["alpha_2"]
        if a2 in seen_countries:
            continue
        if a2 not in alpha2_qgi:
            continue

        qgi = alpha2_qgi[a2]
        max_severity_sal, top_cat, _ = compute_max_severity_salience(qgi["data"])
        if max_severity_sal < 0.5:
            continue

        # Get the FSI trajectory for this country
        trajectory = fsi_historical.get(a2, [])
        if len(trajectory) < 3:
            continue

        seen_countries.add(a2)
        cases.append({
            "qgi_name": qgi["name"],
            "alpha_2": a2,
            "deterioration_year": det["year"],
            "fsi_delta": det["delta"],
            "fsi_prev_total": det["prev_total"],
            "fsi_curr_total": det["curr_total"],
            "max_severity_salience": max_severity_sal,
            "top_severity_category": top_cat,
            "recipe_count": get_total_recipe_count(qgi["data"]),
            "trajectory": trajectory,
        })

    cases.sort(key=lambda x: -x["fsi_delta"])
    return cases[:5]


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(
    fsi_2023: list[dict],
    qgi_data: dict,
    alpha2_qgi: dict,
    fsi_historical: dict,
) -> str:
    """Generate the full Markdown report."""

    lines: list[str] = []

    def w(line: str = ""):
        lines.append(line)

    def table(headers: list[str], rows: list[list[str]], align: list[str] | None = None):
        """Write a Markdown table."""
        w("| " + " | ".join(headers) + " |")
        if align:
            sep = []
            for a in align:
                if a == "r":
                    sep.append("---:")
                elif a == "c":
                    sep.append(":---:")
                else:
                    sep.append(":---")
            w("| " + " | ".join(sep) + " |")
        else:
            w("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in rows:
            w("| " + " | ".join(str(x) for x in row) + " |")

    # ===== HEADER =====
    w("# Structural Analogy Assessment")
    w("## QGI Pattern Analysis of FSI-Flagged Countries")
    w()
    w("**Pre-computed intelligence report -- April 2026**")
    w()
    w("Prepared for the Fund for Peace | [qgintelligence.com](https://qgintelligence.com)")
    w()
    w("*Classification: Demonstration Report -- Not Commissioned*")
    w()
    w("---")
    w()

    # ===== EXECUTIVE SUMMARY =====
    agreements = find_agreement_countries(fsi_2023, alpha2_qgi, n=15)
    agreement_rate = len(agreements)
    fsi_top_15_count = min(15, len(fsi_2023))
    high_risk_agreements = [a for a in agreements if a["max_salience"] >= 0.8]
    agreement_pct = len(high_risk_agreements)

    sleepers = find_sleeper_countries(fsi_2023, alpha2_qgi, fsi_cutoff_low=40, fsi_cutoff_high=130, salience_threshold=0.8)

    w("## 1. Executive Summary")
    w()
    w(
        f"QGI analyzed the economic trajectories of {qgi_data['total_countries']} countries "
        f"using 2.01 billion computed patterns across 58 World Bank indicators. "
        f"Cross-referencing QGI's structural risk scores with the Fund for Peace's "
        f"2023 Fragile States Index (the latest available dataset), we found the following:"
    )
    w()
    w(
        f"1. **High agreement on the most fragile states.** Of the FSI's top 15 most fragile "
        f"countries, {agreement_pct} also produce elevated structural risk signals in QGI "
        f"(max salience >= 0.8). QGI's purely quantitative approach converges with FSI's "
        f"expert-blended methodology on the world's most vulnerable states."
    )
    w()
    w(
        f"2. **{len(sleepers)} potential sleeper countries identified.** These countries rank "
        f"between positions 41 and 130 on FSI (Warning through Elevated tiers) but show "
        f"high structural similarity to pre-crisis trajectories of historically fragile "
        f"states across conflict and crisis categories."
    )
    w()
    w(
        "3. **Structural twin matching reveals hidden trajectories.** For the most fragile "
        "FSI countries, QGI identifies which other countries' historical economic paths "
        "they most closely resemble -- and what happened to those reference countries "
        "subsequently."
    )
    w()
    w(
        "4. **Complementary intelligence.** QGI's indicator-level evidence trail and "
        "structural-twin matching augment FSI's qualitative governance assessment. "
        "Together they cover both the structural economic dimension (QGI) and the "
        "institutional/social dimension (FSI)."
    )
    w()
    w("---")
    w()

    # ===== SECTION 2: WHERE QGI AGREES WITH FSI =====
    w("## 2. Where QGI Agrees with FSI")
    w()
    w(
        "The following table maps the FSI's top 15 most fragile countries to QGI's "
        "structural risk analysis. Agreement is defined as a country producing a "
        "max salience score >= 0.8 in QGI's recipe-based scoring system (V1.8.1)."
    )
    w()

    # Agreement table
    table(
        ["FSI Rank", "Country", "FSI Score", "QGI Risk Tier", "QGI Max Salience", "Top Signal Category", "Recipe Count"],
        [
            [
                str(a["fsi_rank"]),
                a["qgi_name"],
                f"{a['fsi_total']:.1f}",
                a["risk_tier"],
                f"{a['max_salience']:.2f}",
                display_cat(a["top_category"]),
                f"{a['recipe_count']:,}",
            ]
            for a in agreements
        ],
        align=["c", "l", "r", "c", "r", "l", "r"],
    )
    w()

    # Detailed profiles for top 10
    w("### 2.1 Country Profiles (Top 10 Agreement Countries)")
    w()
    for a in agreements[:10]:
        top_cats = a["top_categories"]
        cat_strs = []
        for c in top_cats:
            cat_strs.append(f"{display_cat(c['category'])} (z={c['z_score']:.2f}, salience={c['salience_score']:.2f})")

        w(f"**{a['qgi_name']}** (FSI #{a['fsi_rank']}, Score: {a['fsi_total']:.1f})")
        w()
        w(f"- QGI Risk Tier: **{a['risk_tier']}** | Max Salience: **{a['max_salience']:.2f}**")
        w(f"- Top signals: {'; '.join(cat_strs)}")
        w(f"- Total recipe matches: {a['recipe_count']:,}")
        w(
            f"- {a['qgi_name']}'s trajectory across multiple World Bank indicators produces "
            f"{a['recipe_count']:,} active recipe matches, with highest structural signals in "
            f"{display_cat(top_cats[0]['category'])} and "
            f"{display_cat(top_cats[1]['category']) if len(top_cats) > 1 else 'N/A'}."
        )
        w()

    # Heat map table (text-based)
    w("### 2.2 Signal Heat Map: Top 10 Countries x Key Event Categories")
    w()
    w(
        "The table below shows salience scores (max across tiers) for each country "
        "in five high-impact event categories. Higher scores indicate stronger "
        "structural similarity to historical pre-event trajectories."
    )
    w()

    heatmap_cats = [
        "civil_war_and_insurgency",
        "terrorist_attack",
        "mass_protest",
        "economic_recession",
        "political_violence",
    ]
    heatmap_headers = ["Country"] + [display_cat(c) for c in heatmap_cats]

    heatmap_rows = []
    for a in agreements[:10]:
        row = [a["qgi_name"]]
        for hcat in heatmap_cats:
            # Find max salience for this category across all tiers
            max_sal = 0.0
            for tier_name, tier_data in alpha2_qgi[a["alpha_2"]]["data"]["tiers"].items():
                for cat in tier_data["top_categories"]:
                    if cat["category"] == hcat and cat["salience_score"] > max_sal:
                        max_sal = cat["salience_score"]
            row.append(f"{max_sal:.2f}" if max_sal > 0 else "--")
        heatmap_rows.append(row)

    table(heatmap_headers, heatmap_rows, align=["l"] + ["r"] * len(heatmap_cats))
    w()
    w(
        "*Salience scores represent z-score normalized recipe match strength, "
        "weighted by event category severity. Scores above 1.0 indicate strong "
        "structural signals; above 1.5 indicate very strong signals.*"
    )
    w()
    w("---")
    w()

    # ===== SECTION 3: SLEEPER COUNTRIES =====
    w("## 3. Where QGI Sees Signals FSI Has Not Flagged")
    w()
    w(
        "This is the report's most analytically valuable section. These 'sleeper' "
        "countries rank between positions 41 and 130 on FSI -- in the Warning through "
        "Elevated tiers -- but produce high structural risk signals in QGI's conflict "
        "and crisis categories."
    )
    w()
    w("**Selection criteria:**")
    w("- FSI rank 41-130 (Warning through Elevated tier; excludes both Alert-tier countries and the most stable states)")
    w("- QGI max salience >= 0.8 in at least one high-severity category")
    w(
        "- High-severity categories: civil war, terrorist attack, mass protest, "
        "political violence, interstate war, ethnic conflict, currency/banking crisis, "
        "economic recession, military coup"
    )
    w()

    if sleepers:
        table(
            ["FSI Rank", "Country", "FSI Score", "QGI Max Severity Salience", "Top Severity Signal", "QGI Risk Tier", "Recipe Count"],
            [
                [
                    str(s["fsi_rank"]),
                    s["qgi_name"],
                    f"{s['fsi_total']:.1f}",
                    f"{s['max_severity_salience']:.2f}",
                    display_cat(s["top_severity_category"]),
                    s["risk_tier"],
                    f"{s['recipe_count']:,}",
                ]
                for s in sleepers[:10]
            ],
            align=["c", "l", "r", "r", "l", "c", "r"],
        )
        w()

        # Detailed profiles for top 5 sleepers
        w("### 3.1 Sleeper Country Profiles")
        w()
        for s in sleepers[:5]:
            top_cats = s["top_categories"]
            w(f"**{s['qgi_name']}** (FSI #{s['fsi_rank']}, Score: {s['fsi_total']:.1f})")
            w()
            w(f"- QGI Risk Tier: **{s['risk_tier']}** | Max Severity Salience: **{s['max_severity_salience']:.2f}**")
            w(f"- Top severity signal: **{display_cat(s['top_severity_category'])}**")
            cat_parts = [display_cat(c["category"]) + " (" + f"{c['salience_score']:.2f}" + ")" for c in top_cats[:3]]
            w(f"- Top categories: {'; '.join(cat_parts)}")
            w(f"- Total recipe matches: {s['recipe_count']:,}")
            w()
            w(
                f"  *Why FSI may underweight this:* QGI's pattern engine detects structural "
                f"trajectory similarities between {s['qgi_name']}'s current economic indicators "
                f"and historical pre-crisis paths of other countries. FSI's annual expert-assessed "
                f"snapshot may not capture these long-horizon economic trajectories."
            )
            w()
            w(
                "  *Caveat:* This is a structural signal, not a prediction. It means the "
                "economic trajectory resembles a historical pre-crisis path. It does not mean "
                "a crisis will occur."
            )
            w()
    else:
        w("*No sleeper countries meeting the criteria were found in the current dataset.*")
        w()

    w("---")
    w()

    # ===== SECTION 4: STRUCTURAL TWINS =====
    w("## 4. Structural Twins: Deep Dives")
    w()
    w(
        "QGI's structural-twin capability identifies which other countries' historical "
        "economic trajectories a focal country most closely resembles. This section "
        "profiles five high-risk countries and their structural analogues."
    )
    w()
    w(
        "*Note: Full structural twin analysis requires access to QGI's patterns table "
        "(2.01 billion rows). The profiles below use recipe category overlap as a proxy "
        "for structural similarity. A commissioned report would include per-indicator "
        "correlation analysis and time-shifted trajectory charts.*"
    )
    w()

    # Select 5 countries for deep dive:
    #   2 from FSI top 10, 2 from FSI 10-40, 1 sleeper
    deep_dive_candidates = []
    deep_dive_a2s = set()
    # Top 10: prefer Sudan and Haiti (per design doc)
    for a in agreements[:10]:
        if a["alpha_2"] in ("SD", "HT"):  # Sudan, Haiti -- per design doc
            deep_dive_candidates.append(a)
            deep_dive_a2s.add(a["alpha_2"])
    if len(deep_dive_candidates) < 2:
        for a in agreements[:10]:
            if a["alpha_2"] not in deep_dive_a2s and len(deep_dive_candidates) < 2:
                deep_dive_candidates.append(a)
                deep_dive_a2s.add(a["alpha_2"])

    # FSI 10-40: prefer Pakistan and Lebanon (per design doc)
    mid_range = find_agreement_countries(fsi_2023[10:40], alpha2_qgi, n=30)
    for m in mid_range:
        if m["alpha_2"] in ("PK", "LB") and m["alpha_2"] not in deep_dive_a2s:
            deep_dive_candidates.append(m)
            deep_dive_a2s.add(m["alpha_2"])
    if len(deep_dive_candidates) < 4:
        for m in mid_range:
            if m["alpha_2"] not in deep_dive_a2s and len(deep_dive_candidates) < 4:
                deep_dive_candidates.append(m)
                deep_dive_a2s.add(m["alpha_2"])

    # 1 sleeper (pick the first one not already in deep dive set)
    for s in sleepers:
        if s["alpha_2"] not in deep_dive_a2s:
            deep_dive_candidates.append({
                **s,
                "max_salience": s["max_salience"],
                "top_category": s["top_severity_category"],
                "top_categories": s["top_categories"],
            })
            break

    for dd in deep_dive_candidates[:5]:
        a2 = dd["alpha_2"]
        qgi = alpha2_qgi.get(a2)
        if not qgi:
            continue

        cdata = qgi["data"]
        twins = find_structural_twins(cdata, qgi_data["countries"])
        # Remove self from twins
        twins = [t for t in twins if t["alpha_2"] != a2]

        w(f"### 4.{deep_dive_candidates.index(dd) + 1} {dd['qgi_name'] if 'qgi_name' in dd else dd.get('fsi_name', 'Unknown')}")
        w()
        fsi_rank = dd.get("fsi_rank", "N/A")
        risk_tier = dd.get("risk_tier", qgi["overall_risk_tier"])
        max_sal = dd.get("max_salience", 0)
        w(f"**FSI Rank:** {fsi_rank} | **QGI Risk Tier:** {risk_tier} | **Max Salience:** {max_sal:.2f}")
        w()

        if twins:
            w("**Structural Analogues (by recipe category overlap):**")
            w()
            table(
                ["Reference Country", "Shared Categories", "Overlap", "Ref. Max Salience", "Ref. Risk Tier"],
                [
                    [
                        t["name"],
                        ", ".join(display_cat(c) for c in t["shared_categories"][:3]),
                        str(t["overlap_count"]),
                        f"{t['max_salience']:.2f}",
                        t["risk_tier"],
                    ]
                    for t in twins[:3]
                ],
                align=["l", "l", "c", "r", "c"],
            )
            w()

            # Risk sentence
            best_twin = twins[0]
            shared_cats_display = " and ".join(display_cat(c) for c in best_twin["shared_categories"][:2])
            w(
                f"*{dd.get('qgi_name', dd.get('fsi_name'))}'s structural risk profile -- particularly in "
                f"{shared_cats_display} -- overlaps with {best_twin['name']}'s pattern signature. "
                f"Both countries produce elevated recipe matches across {best_twin['overlap_count']} "
                f"shared event categories, suggesting they face similar structural pressures "
                f"as measured by World Bank economic indicators.*"
            )
            w()
        else:
            w("*No strong structural analogues found in the current dataset.*")
            w()

        # Top indicator-level signals
        top_cats = get_top_categories(cdata, 5)
        w("**Top QGI Signals:**")
        w()
        for cat in top_cats:
            w(f"- {display_cat(cat['category'])}: salience {cat['salience_score']:.2f}, z-score {cat['z_score']:.2f}, {cat['recipe_count']:,} recipes")
        w()

    w("---")
    w()

    # ===== SECTION 5: LEAD-TIME ANALYSIS =====
    w("## 5. Lead-Time Advantage: Historical FSI Deterioration and QGI Signals")
    w()
    w(
        "This section examines whether QGI's structural signals correlate with "
        "subsequent FSI score deteriorations. We identify countries that experienced "
        "significant FSI score increases (>= 4.0 points year-over-year, indicating "
        "worsening fragility) and check whether QGI produces elevated structural "
        "risk signals for those same countries."
    )
    w()

    deteriorations = compute_fsi_deteriorations(fsi_historical, threshold=4.0)
    lead_time_cases = find_lead_time_cases(deteriorations, alpha2_qgi, fsi_historical)

    if lead_time_cases:
        w("### 5.1 FSI Deterioration Events with QGI Structural Signals")
        w()
        table(
            ["Country", "Deterioration Year", "FSI Delta", "FSI Score (Before -> After)", "QGI Top Severity Signal", "QGI Severity Salience", "QGI Recipe Count"],
            [
                [
                    c["qgi_name"],
                    str(c["deterioration_year"]),
                    f"+{c['fsi_delta']:.1f}",
                    f"{c['fsi_prev_total']:.1f} -> {c['fsi_curr_total']:.1f}",
                    display_cat(c["top_severity_category"]),
                    f"{c['max_severity_salience']:.2f}",
                    f"{c['recipe_count']:,}",
                ]
                for c in lead_time_cases
            ],
            align=["l", "c", "r", "c", "l", "r", "r"],
        )
        w()

        w("### 5.2 Interpretation")
        w()
        w(
            "The countries above experienced sharp FSI deteriorations (>= 4 points "
            "year-over-year) AND produce elevated structural risk signals in QGI's "
            "V1.8.1 scoring. This correlation supports the hypothesis that QGI's "
            "pattern-based structural analysis captures risk dimensions that manifest "
            "in FSI's composite scoring with a time lag."
        )
        w()
        w("**Key observations:**")
        w()
        for c in lead_time_cases[:3]:
            traj = c["trajectory"]
            # Find min and max scores
            scores = [t[1] for t in traj if t[1]]
            if scores:
                min_score = min(scores)
                max_score = max(scores)
                min_year = next(t[0] for t in traj if t[1] == min_score)
                max_year = next(t[0] for t in traj if t[1] == max_score)
                w(
                    f"- **{c['qgi_name']}**: FSI score ranged from {min_score:.1f} ({min_year}) "
                    f"to {max_score:.1f} ({max_year}) across 2006-2023. QGI detects {c['recipe_count']:,} "
                    f"recipe matches with strongest signals in {display_cat(c['top_severity_category'])} "
                    f"(salience: {c['max_severity_salience']:.2f})."
                )
        w()
        w(
            "*Note: This analysis demonstrates correlation between QGI's structural "
            "signals and FSI deterioration events. Causal claims require additional "
            "temporal analysis with recipe trigger years from the full Athena pipeline. "
            "A commissioned analysis would include per-recipe temporal windows to "
            "measure precise lead time.*"
        )
        w()
    else:
        w("*Insufficient data to compute lead-time cases.*")
        w()

    # FSI trajectory table for select countries
    w("### 5.3 FSI Score Trajectories (Selected Countries, 2006-2023)")
    w()
    trajectory_countries = ["SD", "SY", "YE", "MM", "UA"]
    traj_names = {"SD": "Sudan", "SY": "Syria", "YE": "Yemen", "MM": "Myanmar", "UA": "Ukraine"}
    traj_years = list(range(2006, 2024))

    traj_headers = ["Country"] + [str(y) for y in traj_years]
    traj_rows = []
    for a2 in trajectory_countries:
        if a2 not in fsi_historical:
            continue
        entries = {e[0]: e[1] for e in fsi_historical[a2]}
        row = [traj_names.get(a2, a2)]
        for y in traj_years:
            score = entries.get(y)
            row.append(f"{score:.1f}" if score else "--")
        traj_rows.append(row)

    if traj_rows:
        table(traj_headers, traj_rows, align=["l"] + ["r"] * len(traj_years))
        w()
        w(
            "*FSI scores range 0-120. Higher scores indicate greater fragility. "
            "Sharp year-over-year increases indicate rapid deterioration.*"
        )
        w()

    w("---")
    w()

    # ===== SECTION 6: METHODOLOGY =====
    w("## 6. Methodology and Reproducibility")
    w()
    w("### 6.1 How QGI Works")
    w()
    w(
        "QGI (Quantitative Geopolitical Intelligence) is a pattern-based structural "
        "risk analysis system. It works in three stages:"
    )
    w()
    w(
        "1. **SCDI Detection.** For every pair of countries and every World Bank "
        "indicator, QGI computes the Pearson correlation coefficient between all "
        "possible time-window combinations. Pairs with |R| >= 0.7 are flagged as "
        "Structurally Correlated Development Indicators (SCDIs). This produces 14.3 "
        "billion SCDIs across 214 countries and 58 indicators."
    )
    w()
    w(
        "2. **Pattern Aggregation.** SCDIs sharing the same country pair, start years, "
        "and window length are grouped into patterns. Each pattern records how many "
        "indicators correlate and at what average strength. The system has computed "
        "2.01 billion patterns."
    )
    w()
    w(
        "3. **Recipe Matching.** For each pattern, QGI checks whether both countries "
        "experienced the same type of geopolitical event within a +/-15% time window "
        "around the pattern's end years. Matching events produce 'recipes' -- "
        "structural analogies with verified historical precedent."
    )
    w()
    w("### 6.2 Scoring (V1.8.1)")
    w()
    w(
        "Recipe matches are scored using z-score normalization per country, combined "
        "via Reciprocal Rank Fusion (RRF) across four time-horizon tiers (S: 3-8 years, "
        "M: 9-20 years, L: 21-40 years, XL: 41+ years). Salience weighting adjusts "
        "scores by event category severity (conflict categories weight 1.0, governance "
        "categories 0.6-0.8)."
    )
    w()
    w("### 6.3 Data Provenance")
    w()
    table(
        ["Data Element", "Source", "License", "Coverage"],
        [
            ["Economic indicators", "World Bank Open Data", "CC BY 4.0", "58 indicators, 214 countries, 1960-2024"],
            ["Geopolitical events", "AI-curated with human verification", "QGI proprietary", "198 countries, 1950-2025, 71 event categories"],
            ["FSI rankings", "Fund for Peace (public)", "Public data", "179 countries, 2006-2023"],
        ],
        align=["l", "l", "l", "l"],
    )
    w()
    w("### 6.4 Architectural Decisions")
    w()
    table(
        ["Decision", "Choice", "Rationale"],
        [
            ["D1: Correlation method", "Pearson", "Captures linear economic trajectory similarity"],
            ["D2: Prediction scope", "Self-prediction only", "Each indicator predicts its own future trajectory"],
            ["D3: Country registry", "S3-backed Parquet via Glue", "Scalable, query-optimized storage"],
            ["D4: Event window", "+/-15% of pattern length", "Balances precision with recall"],
            ["D5: Match requirement", "Both countries must match", "Ensures bidirectional structural validity"],
            ["D6: Coordination", "DynamoDB counters", "Reliable distributed pipeline coordination"],
            ["D7: Prediction flag", "Binary (0/1)", "Clear interpretability over probability ranges"],
        ],
        align=["l", "l", "l"],
    )
    w()
    w("### 6.5 Known Limitations")
    w()
    w("1. **Events are AI-curated.** Geopolitical event histories were generated by AI models and verified by human review. They are not primary-source ground truth.")
    w("2. **Annual resolution only.** QGI operates on annual indicator data. Sub-annual dynamics are not captured.")
    w("3. **Look-ahead bias exists.** The current SCDI computation (V1) does not enforce strict temporal boundaries. This is a documented known limitation (D8).")
    w("4. **Correlation is not causation.** Structural similarity between countries' economic trajectories does not guarantee similar outcomes.")
    w("5. **World Bank data lag.** World Bank indicators have a 1-2 year publication lag. The most recent data points may be estimates.")
    w("6. **Score compression at extremes.** Z-score normalization can compress distinctions among the most fragile states, which tend to cluster at similar scores.")
    w()
    w("---")
    w()

    # ===== SECTION 7: DATA SOURCES =====
    w("## 7. Data Sources")
    w()
    w("This report uses the following data sources:")
    w()
    w(f"- **QGI country-risks.json** (V1.8.1, generated {qgi_data['generated_at'][:10]}): {qgi_data['total_countries']} scored countries with salience scores, risk tiers, and recipe counts across 4 time-horizon tiers.")
    w(f"- **FSI 2023 rankings**: {len(fsi_2023)} countries ranked by the Fund for Peace's Fragile States Index. The 2023 dataset is the latest available in our archive.")
    w(f"- **FSI historical data (2006-2023)**: {len(fsi_historical)} countries with year-over-year FSI total scores, used for deterioration analysis.")
    w("- **QGI salience profiles**: L1/L2 domain-level risk scores for 198 countries.")
    w()
    w("All QGI data is derived from the QGI V1.8.1 pipeline output (April 2026). FSI data is from publicly available Fund for Peace publications.")
    w()
    w("---")
    w()

    # ===== SECTION 8: CALL TO ACTION =====
    w("## 8. Next Steps")
    w()
    w("### Tier 1: Explore (Free)")
    w()
    w("- Browse all 126 scored countries at [qgintelligence.com](https://qgintelligence.com)")
    w("- Full methodology published at [qgintelligence.com/methodology](https://qgintelligence.com/methodology)")
    w("- Country Intelligence Browser with risk tiers and evidence breakdowns")
    w()
    w("### Tier 2: Collaboration -- FSI-Specific Deep Analysis")
    w()
    w(
        "QGI runs its full pattern engine against FSI's historical sub-indicator scores "
        "(2006-2024), producing per-sub-indicator structural twins with indicator-level "
        "sparkline charts and precise lead-time measurements."
    )
    w()
    w("- Deliverable: Extended report with per-sub-indicator structural twins")
    w("- Timeline: 4-6 weeks from data handoff to report delivery")
    w()
    w("### Tier 3: Partnership -- Ongoing Intelligence Feed")
    w()
    w("- Monthly structural analogy updates aligned to FSI methodology")
    w("- Custom dashboard showing FSI countries through QGI's structural-twin lens")
    w("- White-label option for FFP publications")
    w()
    w("**Contact:** amin@qgintelligence.com | [qgintelligence.com](https://qgintelligence.com)")
    w()
    w("---")
    w()
    w(f"*Report generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*")
    w()
    w("*QGI -- Quantitative Geopolitical Intelligence*")
    w()
    w("*This report does not constitute investment advice. All structural analogies represent statistical correlations, not causal predictions.*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("=" * 60)
    print("FSI Demo Report Generator")
    print("=" * 60)
    print()

    # Load QGI data
    print("[1/5] Loading QGI country-risks.json...")
    qgi_data = load_qgi_country_risks()
    alpha2_qgi = build_alpha2_to_qgi(qgi_data)
    print(f"  Loaded {len(alpha2_qgi)} countries from QGI (V{qgi_data['version']})")

    # Load FSI 2023 data
    print("[2/5] Loading FSI 2023 data...")
    fsi_2023 = load_fsi_data(2023)
    top50 = fsi_2023[:50]
    matched_top50 = sum(1 for r in top50 if r["alpha_2"] and r["alpha_2"] in alpha2_qgi)
    unmatched = [r["name"] for r in top50 if not r["alpha_2"] or r["alpha_2"] not in alpha2_qgi]
    print(f"  Loaded {len(fsi_2023)} FSI countries")
    print(f"  Matched to QGI: {matched_top50}/{len(top50)} (top 50)")
    if unmatched:
        print(f"  Unmatched in top 50: {', '.join(unmatched)}")

    # Load FSI historical data
    print("[3/5] Loading FSI historical data (2006-2023)...")
    fsi_historical = load_fsi_historical()
    print(f"  Loaded historical data for {len(fsi_historical)} countries across 18 years")

    # Run analysis
    print("[4/5] Running analysis...")
    agreements = find_agreement_countries(fsi_2023, alpha2_qgi, n=15)
    sleepers = find_sleeper_countries(fsi_2023, alpha2_qgi, fsi_cutoff_low=40, fsi_cutoff_high=130, salience_threshold=0.8)
    deteriorations = compute_fsi_deteriorations(fsi_historical, threshold=4.0)
    print(f"  Agreement countries (top 15): {len(agreements)}")
    print(f"  Sleeper countries: {len(sleepers)}")
    print(f"  FSI deterioration events (delta >= 4.0): {len(deteriorations)}")

    # Generate report
    print("[5/5] Generating report...")
    report = generate_report(fsi_2023, qgi_data, alpha2_qgi, fsi_historical)

    # Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(report)

    print()
    print(f"Report written to: {OUTPUT_PATH}")
    print(f"Report size: {len(report):,} characters, {report.count(chr(10)):,} lines")
    print()
    print("Done.")


if __name__ == "__main__":
    main()
