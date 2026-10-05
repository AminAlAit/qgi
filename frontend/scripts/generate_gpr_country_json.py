#!/usr/bin/env python3
"""
Generate data/gpr-country.json — the per-country QGI-GPR confirmation-layer
quality table that the /methodology/gpr page reads at build time.

QGI-GPR is QGI's own all-country geopolitical-risk index, built on the GDELT
Global Knowledge Graph and validated against Caldara & Iacoviello's published
Geopolitical Risk index (the 44 GPRC countries). This bakes each validated
country's SIGNAL-QUALITY TIER (how well our movements track the published
benchmark) into a small static file. It does NOT bake raw risk values — the
proxy is a movement tracker, not a levels replica.

Tiers — strict, pre-registered thresholds on the month-over-month change
Spearman (the de-trended headline metric):

    A  "Strong signal"     delta_spearman >= 0.50
    B  "Confirmed signal"  0.35 <= delta_spearman < 0.50
    C  "Weak signal"       delta_spearman <  0.35   (Colombia, 0.3463, is C)

Source of truth: qgi-ml/gpr-build/gpr-full-results.json (main_panel.per_country).
No GDELT scan, no AWS, no network. Per-month series are intentionally omitted
from v1: the methodology page renders a tier table, not sparklines. A later
country-page panel will regenerate this file with series.

Run:    python scripts/generate_gpr_country_json.py
Verify: python -m pytest scripts/test_generate_gpr_country_json.py -v
"""
from __future__ import annotations

import json
import os
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
FRONTEND = os.path.dirname(HERE)
REPO = os.path.dirname(FRONTEND)
RESULTS = os.path.join(REPO, "qgi-ml", "gpr-build", "gpr-full-results.json")
OUT = os.path.join(FRONTEND, "data", "gpr-country.json")

# All-country coverage; 44 of them carry a published academic answer key.
N_TOTAL = 215

# Tier thresholds on the change-Spearman headline. Pre-registered in the PoC
# protocol and carried unchanged to the full-method run.
TIER_A_MIN = 0.50
TIER_B_MIN = 0.35
TIER_LABEL = {
    "A": "Strong signal",
    "B": "Confirmed signal",
    "C": "Weak signal",
}

# ISO3 -> display name for the 44 validated (Caldara-Iacoviello GPRC) countries.
# Names from qgi-ml/gpr-build/gpr-full-validation-results.md, section 0.
NAMES = {
    "ARG": "Argentina", "AUS": "Australia", "BEL": "Belgium", "BRA": "Brazil",
    "CAN": "Canada", "CHE": "Switzerland", "CHL": "Chile", "CHN": "China",
    "COL": "Colombia", "DEU": "Germany", "DNK": "Denmark", "EGY": "Egypt",
    "ESP": "Spain", "FIN": "Finland", "FRA": "France", "GBR": "United Kingdom",
    "HKG": "Hong Kong", "HUN": "Hungary", "IDN": "Indonesia", "IND": "India",
    "ISR": "Israel", "ITA": "Italy", "JPN": "Japan", "KOR": "South Korea",
    "MEX": "Mexico", "MYS": "Malaysia", "NLD": "Netherlands", "NOR": "Norway",
    "PER": "Peru", "PHL": "Philippines", "POL": "Poland", "PRT": "Portugal",
    "RUS": "Russia", "SAU": "Saudi Arabia", "SWE": "Sweden", "THA": "Thailand",
    "TUN": "Tunisia", "TUR": "Turkey", "TWN": "Taiwan", "UKR": "Ukraine",
    "USA": "United States", "VEN": "Venezuela", "VNM": "Vietnam",
    "ZAF": "South Africa",
}

# Per-ISO3 monthly proxy series (QGI's own GPR movement) for the country-page
# sparkline. Lives on the founder's machine; CI overrides via GPR_PROXY_PATH
# (or skips the series — the committed data/gpr-country.json already carries it).
PROXY_PATH = os.environ.get("GPR_PROXY_PATH", "C:/tmp/gpr_proxy44_v2.json")


def load_proxy() -> dict:
    """Per-ISO3 {YYYY-MM: float} proxy series; {} when the file is absent."""
    try:
        with open(PROXY_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def series_for(proxy: dict, iso3: str) -> dict:
    """Ascending monthly movement series for the country-page sparkline."""
    months = proxy.get(iso3)
    if not months:
        return {"dates": [], "values": []}
    dates = sorted(months.keys())
    return {"dates": dates, "values": [round(float(months[d]), 3) for d in dates]}


def tier_for(delta_spearman: float) -> str:
    """Classify a country by its change-Spearman against the published GPR."""
    if delta_spearman >= TIER_A_MIN:
        return "A"
    if delta_spearman >= TIER_B_MIN:
        return "B"
    return "C"


def build(results: dict) -> dict:
    """Build the gpr-country.json payload from the full-validation results."""
    panel = results["main_panel"]
    # Rank by signal strength so the file is human-scannable and diffs stay
    # stable across regenerations.
    entries = sorted(
        panel["per_country"], key=lambda e: e["spearman_delta"], reverse=True
    )
    proxy = load_proxy()

    countries: dict[str, dict] = {}
    for e in entries:
        iso3 = e["iso3"]
        delta = e["spearman_delta"]
        t = tier_for(delta)
        countries[iso3] = {
            "iso3": iso3,
            "name": NAMES.get(iso3, iso3),
            "validated": True,
            "tier": t,
            "tier_label": TIER_LABEL[t],
            "delta_spearman": round(delta, 4),
            "spike_recall": round(e["spike_recall"], 4),
            "n_months": e["n"],
            "window": e.get("window", ""),
            "series": series_for(proxy, iso3),
        }

    tier_counts = {"A": 0, "B": 0, "C": 0}
    for c in countries.values():
        tier_counts[c["tier"]] += 1

    n_validated = len(countries)
    n_soft_pass = tier_counts["A"] + tier_counts["B"]

    meta = {
        "generated": date.today().isoformat(),
        "source": "qgi-ml/gpr-build/gpr-full-results.json",
        "n_validated": n_validated,
        "n_total": N_TOTAL,
        "headline_delta_spearman": round(panel["mean_spearman_delta"], 4),
        "mean_spike_recall": round(panel["mean_spike_recall"], 4),
        "pct_passing_soft_bar": round(n_soft_pass / n_validated, 4),
        "tier_counts": tier_counts,
        "tier_thresholds": {"A_min": TIER_A_MIN, "B_min": TIER_B_MIN},
    }
    return {"meta": meta, "countries": countries}


def main() -> None:
    with open(RESULTS, encoding="utf-8") as fh:
        results = json.load(fh)
    payload = build(results)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    c = payload["meta"]["tier_counts"]
    print(
        f"Wrote {OUT}\n"
        f"  validated={payload['meta']['n_validated']} / total={payload['meta']['n_total']}\n"
        f"  tiers A/B/C = {c['A']}/{c['B']}/{c['C']}  "
        f"soft-bar pass = {payload['meta']['pct_passing_soft_bar']:.4f}"
    )


if __name__ == "__main__":
    main()
