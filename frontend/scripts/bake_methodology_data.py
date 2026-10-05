#!/usr/bin/env python3
"""
Bake all build-time JSON inputs the methodology page needs.

Reads from `qgi-data/events/` (curated + verification + taxonomy) and produces
five files under `qgi-frontend/data/`:

  taxonomy-with-counts.json   — taxonomy_hierarchy.json + verified-event count per leaf
  source-diversity.json       — top source domains across all verified events
  verified-events.json        — flat array of {country, year, title, category, source, sourceDomain}
  methodology-stats.json      — counts for the stat strip
  coverage-gap.json           — country coverage breakdown for the honesty panel

Run from anywhere in the repo:

    python qgi-frontend/scripts/bake_methodology_data.py

Idempotent. Safe to re-run after every verification pass.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

# ─── paths ───────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = SCRIPT_DIR.parent
REPO_ROOT = FRONTEND_DIR.parent
QGI_DATA = REPO_ROOT / "qgi-data"
EVENTS_CURATED = QGI_DATA / "events" / "curated"
EVENTS_VERIFICATION = QGI_DATA / "events" / "verification"
TAXONOMY = QGI_DATA / "events" / "taxonomy_hierarchy.json"

OUT = FRONTEND_DIR / "data"


# ─── helpers ─────────────────────────────────────────────────────────────────
def country_slug_to_name(slug: str) -> str:
    """afghanistan → Afghanistan; trinidad_and_tobago → Trinidad and Tobago."""
    return " ".join(w.capitalize() if w not in {"and", "of", "the"} else w
                    for w in slug.split("_"))


def normalize_domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        netloc = urlparse(url).netloc.lower()
        # Strip www.
        if netloc.startswith("www."):
            netloc = netloc[4:]
        # Collapse subdomains for big-name sources to their canonical domain
        # (en.wikipedia.org → wikipedia.org)
        for canonical in (
            "wikipedia.org", "imf.org", "worldbank.org", "hrw.org",
            "un.org", "icj-cij.org", "europa.eu", "history.state.gov",
            "britannica.com", "gov.uk", "rferl.org", "aljazeera.com",
            "bbc.com", "bbc.co.uk", "reuters.com", "ft.com", "nytimes.com",
            "washingtonpost.com", "theguardian.com", "economist.com",
        ):
            if netloc.endswith("." + canonical) or netloc == canonical:
                return canonical
        return netloc
    except Exception:
        return None


def load_curated_safe(path: Path) -> list:
    """Curated files mostly UTF-8 but some are latin-1 (per session memory:
    cameroon, central_african_republic, georgia, jordan)."""
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return json.load(open(path, encoding=encoding))
        except UnicodeDecodeError:
            continue
        except json.JSONDecodeError:
            return []
    return []


# ─── 1. Bake taxonomy with counts ────────────────────────────────────────────
def bake_taxonomy_with_counts() -> tuple[dict, Counter]:
    print(f"[1/5] Baking taxonomy with verified-event counts...")
    taxonomy = json.load(open(TAXONOMY, encoding="utf-8-sig"))

    # Count verified TRUE events per layer-3 category
    category_counts: Counter[str] = Counter()
    verification_files = sorted(EVENTS_VERIFICATION.glob("*.json"))
    print(f"  found {len(verification_files)} verification files")

    # Build (country, year, title) → verdict index from verification files
    verdict_idx: dict[tuple[str, int, str], str] = {}
    for vf in verification_files:
        slug = vf.stem
        try:
            entries = json.load(open(vf, encoding="utf-8"))
        except Exception:
            continue
        for e in entries:
            key = (slug, int(e.get("year", -1)), str(e.get("title", "")))
            verdict_idx[key] = e.get("verdict", "")

    # Walk curated events; for each TRUE-verdict event, increment its category
    curated_files = sorted(EVENTS_CURATED.glob("*.json"))
    for cf in curated_files:
        slug = cf.stem
        events = load_curated_safe(cf)
        for e in events:
            key = (slug, int(e.get("year", -1)), str(e.get("title", "")))
            verdict = verdict_idx.get(key)
            # Per #374: if no verification file or verdict != TRUE, drop
            if verdict != "TRUE":
                continue
            cat = e.get("category", "").strip()
            if cat:
                category_counts[cat] += 1

    # Annotate the taxonomy with counts
    for l1 in taxonomy.get("layer1", []):
        l1_total = 0
        for l2 in l1.get("layer2", []):
            l2_total = 0
            for cat in l2.get("layer3", []):
                count = category_counts.get(cat, 0)
                l2_total += count
            l2["event_count"] = l2_total
            l1_total += l2_total
        l1["event_count"] = l1_total

    # Also include a flat layer3 → count map for components that prefer it
    taxonomy["layer3_counts"] = dict(category_counts.most_common())

    out = OUT / "taxonomy-with-counts.json"
    out.write_text(json.dumps(taxonomy, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  → {out} ({sum(category_counts.values()):,} events across {len(category_counts)} categories)")
    return taxonomy, category_counts


# ─── 2. Bake source-domain diversity ─────────────────────────────────────────
def bake_source_diversity() -> dict:
    print(f"[2/5] Baking source-domain diversity...")
    domain_counts: Counter[str] = Counter()
    total_with_source = 0
    total_events = 0
    unique_urls: set[str] = set()

    for vf in sorted(EVENTS_VERIFICATION.glob("*.json")):
        try:
            entries = json.load(open(vf, encoding="utf-8"))
        except Exception:
            continue
        for e in entries:
            if e.get("verdict") != "TRUE":
                continue
            total_events += 1
            url = e.get("source")
            if not url:
                continue
            unique_urls.add(url)
            total_with_source += 1
            domain = normalize_domain(url)
            if domain:
                domain_counts[domain] += 1

    # Top 10 + Other
    top_n = 10
    top = domain_counts.most_common(top_n)
    other_count = sum(c for _, c in domain_counts.most_common()[top_n:])
    slices = [{"domain": d, "count": c} for d, c in top]
    if other_count > 0:
        slices.append({"domain": "Other", "count": other_count})

    payload = {
        "total_events": total_events,
        "events_with_source": total_with_source,
        "unique_urls": len(unique_urls),
        "unique_domains": len(domain_counts),
        "slices": slices,
    }
    out = OUT / "source-diversity.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  → {out} ({len(domain_counts)} domains, top: {top[:3]})")
    return payload


# ─── 3. Bake verified-events flat list ───────────────────────────────────────
def bake_verified_events() -> list[dict]:
    """One row per verified TRUE event for the events table."""
    print(f"[3/5] Baking verified-events flat list...")
    events: list[dict] = []
    verdict_idx: dict[tuple[str, int, str], dict] = {}

    # Index verification entries
    for vf in sorted(EVENTS_VERIFICATION.glob("*.json")):
        slug = vf.stem
        try:
            entries = json.load(open(vf, encoding="utf-8"))
        except Exception:
            continue
        for e in entries:
            key = (slug, int(e.get("year", -1)), str(e.get("title", "")))
            verdict_idx[key] = e

    # Walk curated, emit TRUE rows enriched with the verification source
    for cf in sorted(EVENTS_CURATED.glob("*.json")):
        slug = cf.stem
        country = country_slug_to_name(slug)
        for e in load_curated_safe(cf):
            year = int(e.get("year", -1))
            title = str(e.get("title", ""))
            key = (slug, year, title)
            ver = verdict_idx.get(key)
            if not ver or ver.get("verdict") != "TRUE":
                continue
            url = ver.get("source") or e.get("verification_source")
            domain = normalize_domain(url)
            events.append({
                "country": country,
                "year": year,
                "title": title,
                "category": e.get("category", ""),
                "source": url,
                "sourceDomain": domain,
            })

    # Sort by year desc, then country asc
    events.sort(key=lambda r: (-r["year"], r["country"]))
    out = OUT / "verified-events.json"
    out.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
    size_mb = out.stat().st_size / (1024 * 1024)
    print(f"  → {out} ({len(events):,} rows, {size_mb:.2f} MB)")
    return events


# ─── 4. Bake methodology stat strip data ─────────────────────────────────────
def bake_methodology_stats(taxonomy: dict, source: dict, events: list[dict]) -> dict:
    print(f"[4/5] Baking methodology stats...")
    countries = sorted({e["country"] for e in events})
    categories_used = sorted({e["category"] for e in events})
    payload = {
        "updated": date.today().isoformat(),
        "total_verified_events": len(events),
        "verified_countries": len(countries),
        "category_count": taxonomy.get("summary", {}).get("layer3_count", 71),
        "categories_with_data": len(categories_used),
        "unique_source_urls": source["unique_urls"],
        "unique_source_domains": source["unique_domains"],
        # Indicator stats — active panel is 250 across 8 providers: the 109
        # originally ingested (WB 69 + V-Dem 35 + FAOSTAT 5) + 136 activated from
        # the 250-run bench (qgi-ml/enrichment/250-run/selected-141.json,
        # post-license-audit; of the 141, 5 excluded = 1 already live + 4
        # same-measure duplicates) + 5 vetted top-ups from the reachable pool.
        # Breakdown keys must match the StatCards logo lookup ("V-Dem", not
        # "V-Dem v16"). These are a fallback — the live roster lives in
        # data/indicator-catalog.json.
        "indicator_count": 250,
        "indicator_breakdown": {
            "World Bank": 99,
            "V-Dem": 90,
            "UCDP": 19,
            "FAOSTAT": 13,
            "UNHCR": 11,
            "ILOSTAT": 8,
            "OWID": 5,
            "UNDP": 5,
        },
        "indicator_providers": [
            "World Bank", "V-Dem", "UCDP", "FAOSTAT",
            "UNHCR", "ILOSTAT", "OWID", "UNDP",
        ],
        "earliest_event_year": min((e["year"] for e in events), default=None),
        "latest_event_year": max((e["year"] for e in events), default=None),
    }
    out = OUT / "methodology-stats.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  → {out} ({payload['total_verified_events']:,} events / "
          f"{payload['verified_countries']} countries)")
    return payload


# ─── 5. Bake coverage-gap data ───────────────────────────────────────────────
def bake_coverage_gap(events: list[dict]) -> dict:
    """For the honesty panel + the world map choropleth."""
    print(f"[5/5] Baking coverage-gap + choropleth data...")
    counts: Counter[str] = Counter(e["country"] for e in events)
    # Region rough-bucket — approximate, no UN region API
    region_buckets = {
        "Europe": [
            "Albania", "Andorra", "Austria", "Belarus", "Belgium",
            "Bosnia and Herzegovina", "Bulgaria", "Croatia", "Cyprus",
            "Czechia", "Denmark", "Estonia", "Finland", "France", "Germany",
            "Greece", "Hungary", "Iceland", "Ireland", "Italy", "Latvia",
            "Liechtenstein", "Lithuania", "Luxembourg", "Malta", "Moldova",
            "Monaco", "Montenegro", "Netherlands", "North Macedonia", "Norway",
            "Poland", "Portugal", "Romania", "San Marino", "Serbia", "Slovakia",
            "Slovenia", "Spain", "Sweden", "Switzerland", "Turkiye", "Ukraine",
            "United Kingdom", "Vatican City",
        ],
        "MENA": [
            "Algeria", "Bahrain", "Egypt", "Iran", "Iraq", "Israel", "Jordan",
            "Kuwait", "Lebanon", "Libya", "Morocco", "Oman", "Palestine",
            "Qatar", "Saudi Arabia", "Syria", "Tunisia",
            "United Arab Emirates", "Yemen",
        ],
        "Sub-Saharan Africa": [
            "Angola", "Benin", "Botswana", "Burkina Faso", "Burundi", "Cabo Verde",
            "Cameroon", "Central African Republic", "Chad", "Comoros",
            "Cote D'Ivoire", "Cote D Ivoire", "Djibouti", "Equatorial Guinea",
            "Eritrea", "Eswatini", "Ethiopia", "Gabon", "Gambia", "Ghana",
            "Guinea", "Guinea Bissau", "Kenya", "Lesotho", "Liberia",
            "Madagascar", "Malawi", "Mali", "Mauritania", "Mauritius",
            "Mozambique", "Namibia", "Niger", "Nigeria",
            "Republic Of The Congo", "Rwanda", "Sao Tome And Principe",
            "Senegal", "Seychelles", "Sierra Leone", "Somalia", "South Africa",
            "South Sudan", "Sudan", "Tanzania",
            "The Democratic Republic Of The Congo", "Togo", "Uganda", "Zambia",
            "Zimbabwe",
        ],
        "Asia & Pacific": [
            "Afghanistan", "Australia", "Bangladesh", "Bhutan", "Brunei",
            "Cambodia", "China", "Fiji", "India", "Indonesia", "Japan",
            "Kazakhstan", "Kiribati", "Kyrgyzstan", "Laos", "Malaysia",
            "Maldives", "Marshall Islands", "Micronesia", "Mongolia", "Myanmar",
            "Nauru", "Nepal", "New Zealand", "North Korea", "Pakistan", "Palau",
            "Papua New Guinea", "Philippines", "Samoa", "Singapore",
            "Solomon Islands", "South Korea", "Sri Lanka", "Taiwan",
            "Tajikistan", "Thailand", "Timor Leste", "Tonga", "Turkmenistan",
            "Tuvalu", "Uzbekistan", "Vanuatu", "Vietnam",
        ],
        "Americas": [
            "Antigua And Barbuda", "Argentina", "Bahamas", "Barbados", "Belize",
            "Bolivia", "Brazil", "Canada", "Chile", "Colombia", "Costa Rica",
            "Cuba", "Dominica", "Dominican Republic", "Ecuador", "El Salvador",
            "Grenada", "Guatemala", "Guyana", "Haiti", "Honduras", "Jamaica",
            "Mexico", "Nicaragua", "Panama", "Paraguay", "Peru",
            "Saint Kitts And Nevis", "Saint Lucia",
            "Saint Vincent And The Grenadines", "Suriname",
            "Trinidad And Tobago", "United States Of America", "Uruguay",
            "Venezuela",
        ],
    }

    region_summary: dict[str, dict] = {}
    for region, members in region_buckets.items():
        verified_in_region = [m for m in members if counts.get(m, 0) > 0]
        unverified_in_region = [m for m in members if counts.get(m, 0) == 0]
        events_in_region = sum(counts.get(m, 0) for m in members)
        region_summary[region] = {
            "total_countries": len(members),
            "verified_countries": len(verified_in_region),
            "unverified_countries": unverified_in_region,
            "total_events": events_in_region,
            "coverage_pct": round(100 * len(verified_in_region) / max(len(members), 1), 1),
        }

    # Per-country counts for the choropleth
    country_event_counts = [
        {"country": country, "count": count}
        for country, count in sorted(counts.items(), key=lambda x: -x[1])
    ]

    payload = {
        "total_un_members": 195,
        "verified_countries": len(counts),
        "verified_pct": round(100 * len(counts) / 195, 1),
        "regions": region_summary,
        "per_country": country_event_counts,
    }
    out = OUT / "coverage-gap.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  → {out} ({len(counts)} verified countries / 195 UN members)")
    return payload


# ─── orchestrate ─────────────────────────────────────────────────────────────
def main():
    if not OUT.exists():
        print(f"creating {OUT}")
        OUT.mkdir(parents=True, exist_ok=True)
    if not QGI_DATA.exists():
        print(f"ERROR: qgi-data not found at {QGI_DATA}", file=sys.stderr)
        sys.exit(1)

    taxonomy, _ = bake_taxonomy_with_counts()
    source = bake_source_diversity()
    events = bake_verified_events()
    bake_methodology_stats(taxonomy, source, events)
    bake_coverage_gap(events)
    print("\nDone. All five files written under qgi-frontend/data/.")


if __name__ == "__main__":
    main()
