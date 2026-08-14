#!/usr/bin/env python3
"""
Generate baked frontend JSON data from Athena pipeline outputs.
Run after each pipeline completion alongside generate_country_risks.py.

Produces:
  1. country-partners-index.json — partner lookup for /patterns S1 (GH#274)
  2. Extends country-risks.json with pattern_density + top_partners (GH#275)

Usage:
    python generate_frontend_data.py \
        --bucket qgi-data-lake-771606957899 \
        --region eu-central-1 \
        --frontend-dir ../qgi-frontend/data
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import boto3


def run_athena_query(athena, query: str, workgroup: str, database: str) -> str:
    """Submit Athena query and wait for results. Returns query execution ID."""
    resp = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": database},
        WorkGroup=workgroup,
    )
    qid = resp["QueryExecutionId"]
    while True:
        status = athena.get_query_execution(QueryExecutionId=qid)
        state = status["QueryExecution"]["Status"]["State"]
        if state in ("SUCCEEDED",):
            return qid
        if state in ("FAILED", "CANCELLED"):
            reason = status["QueryExecution"]["Status"].get("StateChangeReason", "")
            raise RuntimeError(f"Athena query {state}: {reason}")
        time.sleep(2)


def get_athena_results(athena, qid: str) -> list[dict]:
    """Fetch all rows from an Athena query result."""
    rows = []
    paginator = athena.get_paginator("get_query_results")
    for page in paginator.paginate(QueryExecutionId=qid):
        result_rows = page["ResultSet"]["Rows"]
        if not rows:
            # First page: first row is header
            headers = [col["VarCharValue"] for col in result_rows[0]["Data"]]
            data_rows = result_rows[1:]
        else:
            data_rows = result_rows
        for row in data_rows:
            values = [col.get("VarCharValue", "") for col in row["Data"]]
            rows.append(dict(zip(headers, values)))
    return rows


def generate_partners_index(athena, s3, bucket: str, workgroup: str, database: str, frontend_dir: Path):
    """GH#274: Generate country-partners-index.json for /patterns S1."""
    print("\n=== Generating country-partners-index.json (GH#274) ===")

    query = """
    SELECT
        country_a_id,
        country_b_id,
        count(*) as window_count,
        max(pattern_power_score) as best_pps,
        avg(avg_correlation) as mean_corr,
        min(length) as min_length,
        max(length) as max_length,
        count(DISTINCT length) as length_count
    FROM qgi_data.patterns
    GROUP BY country_a_id, country_b_id
    """

    print("  Running Athena query (scanning patterns table)...")
    qid = run_athena_query(athena, query, workgroup, database)
    print(f"  Query completed: {qid}")

    rows = get_athena_results(athena, qid)
    print(f"  Got {len(rows)} country pairs")

    # Load country names
    countries_file = frontend_dir / "countries.json"
    if countries_file.exists():
        with open(countries_file) as f:
            countries_list = json.load(f)
        id_to_name = {str(c["id"]): c["name"] for c in countries_list}
        id_to_alpha2 = {str(c["id"]): c.get("alpha_2", "") for c in countries_list}
    else:
        id_to_name = {}
        id_to_alpha2 = {}

    # Build index: {country_a_id -> [{partner_id, partner_name, alpha2, window_count, best_pps, mean_corr, lengths}]}
    index: dict[str, list] = {}
    for row in rows:
        a_id = row["country_a_id"]
        b_id = row["country_b_id"]
        if a_id not in index:
            index[a_id] = []
        index[a_id].append({
            "p": int(b_id),
            "n": id_to_name.get(b_id, f"Country {b_id}"),
            "a2": id_to_alpha2.get(b_id, ""),
            "w": int(row["window_count"]),
            "pps": round(float(row["best_pps"]), 2),
            "c": round(float(row["mean_corr"]), 3),
            "lmin": int(row["min_length"]),
            "lmax": int(row["max_length"]),
            "lc": int(row["length_count"]),
        })

    # Sort each country's partners by best_pps descending
    for a_id in index:
        index[a_id].sort(key=lambda x: x["pps"], reverse=True)

    out_path = frontend_dir / "country-partners-index.json"
    with open(out_path, "w") as f:
        json.dump(index, f, separators=(",", ":"))
    size_kb = os.path.getsize(out_path) / 1024
    print(f"  Wrote {out_path} ({size_kb:.0f} KB, {len(index)} countries)")


def generate_pattern_density(athena, workgroup: str, database: str) -> dict:
    """GH#275: Query pattern density by year per country."""
    print("\n=== Generating pattern density data (GH#275) ===")

    query = """
    SELECT country_a_id, start_year_a as year, count(*) as cnt
    FROM qgi_data.patterns
    GROUP BY country_a_id, start_year_a
    ORDER BY country_a_id, start_year_a
    """

    print("  Running Athena query...")
    qid = run_athena_query(athena, query, workgroup, database)
    rows = get_athena_results(athena, qid)
    print(f"  Got {len(rows)} density rows")

    # Build {country_id -> {years: [...], counts: [...], total: N}}
    density: dict[str, dict] = {}
    for row in rows:
        cid = row["country_a_id"]
        if cid not in density:
            density[cid] = {"years": [], "counts": [], "total": 0}
        density[cid]["years"].append(int(row["year"]))
        cnt = int(row["cnt"])
        density[cid]["counts"].append(cnt)
        density[cid]["total"] += cnt

    print(f"  Pattern density computed for {len(density)} countries")
    return density


def generate_structural_twins(athena, workgroup: str, database: str) -> dict:
    """GH#275: Query top 5 structural twins per country from patterns table."""
    print("\n=== Generating structural twins data (GH#275) ===")

    query = """
    SELECT country_a_id, country_b_id, count(*) as pattern_count,
           avg(avg_correlation) as mean_corr,
           max(pattern_power_score) as best_pps
    FROM qgi_data.patterns
    GROUP BY country_a_id, country_b_id
    """

    print("  Running Athena query...")
    qid = run_athena_query(athena, query, workgroup, database)
    rows = get_athena_results(athena, qid)
    print(f"  Got {len(rows)} pair rows")

    # Build top 5 per country
    pairs: dict[str, list] = {}
    for row in rows:
        a_id = row["country_a_id"]
        if a_id not in pairs:
            pairs[a_id] = []
        pairs[a_id].append({
            "partner_id": int(row["country_b_id"]),
            "pattern_count": int(row["pattern_count"]),
            "mean_corr": round(float(row["mean_corr"]), 3),
            "best_pps": round(float(row["best_pps"]), 2),
        })

    twins: dict[str, list] = {}
    for a_id, partner_list in pairs.items():
        partner_list.sort(key=lambda x: x["pattern_count"], reverse=True)
        twins[a_id] = partner_list[:5]

    print(f"  Structural twins computed for {len(twins)} countries")
    return twins


def generate_pair_windows(athena, workgroup: str, database: str, frontend_dir: Path, limit: int | None = None):
    """GH#281: Pre-compute per-pair pattern windows as baked JSON files.

    Writes one file per predictor country to
    frontend_dir/pair-windows/{country_a_id}.json

    Each file is keyed by country_b_id and contains:
      "top"  — up to 200 windows sorted by pps desc
                (keys: l, sa, sb, ic, ac, pps)
      "hist" — {length: window_count} frequency map

    Args:
        limit: if set, appends LIMIT <n> to the query (useful for local
               testing against the full table without scanning 2 B rows).
    """
    print("\n=== Generating pair-windows files (GH#281) ===")

    limit_clause = f"\nLIMIT {limit}" if limit else ""
    query = f"""
    SELECT country_a_id, country_b_id, length, start_year_a, start_year_b,
           indicator_count, avg_correlation, pattern_power_score
    FROM qgi_data.patterns
    ORDER BY country_a_id, country_b_id, pattern_power_score DESC{limit_clause}
    """

    print("  Running Athena query (large scan — may take several minutes)...")
    qid = run_athena_query(athena, query, workgroup, database)
    print(f"  Query completed: {qid}. Streaming results...")

    out_dir = frontend_dir / "pair-windows"
    out_dir.mkdir(parents=True, exist_ok=True)

    TOP_N = 200
    current_a_id: str | None = None
    # {country_b_id: [window dicts]}
    pairs_buf: dict[str, list[dict]] = {}
    files_written = 0
    total_rows = 0

    def flush(a_id: str, buf: dict[str, list[dict]]) -> None:
        output: dict[str, dict] = {}
        for b_id, windows in buf.items():
            hist: dict[str, int] = {}
            for w in windows:
                if w["l"] is not None:
                    k = str(w["l"])
                    hist[k] = hist.get(k, 0) + 1
            output[b_id] = {"top": windows, "hist": hist}
        path = out_dir / f"{a_id}.json"
        with open(path, "w") as fp:
            json.dump(output, fp, separators=(",", ":"))

    # Paginate results
    headers = None
    next_token = None
    paginator = athena.get_paginator("get_query_results")
    pages = paginator.paginate(QueryExecutionId=qid, PaginationConfig={"PageSize": 1000})

    for page in pages:
        page_rows = page["ResultSet"]["Rows"]
        if headers is None:
            headers = [col["VarCharValue"] for col in page_rows[0]["Data"]]
            data_rows = page_rows[1:]
        else:
            data_rows = page_rows

        for raw in data_rows:
            cells = raw.get("Data", [])
            row = {headers[i]: cells[i].get("VarCharValue", "") if i < len(cells) else "" for i in range(len(headers))}
            total_rows += 1

            a_id = row["country_a_id"]
            b_id = row["country_b_id"]

            if current_a_id is not None and a_id != current_a_id:
                flush(current_a_id, pairs_buf)
                files_written += 1
                pairs_buf = {}

            current_a_id = a_id

            pair_list = pairs_buf.setdefault(b_id, [])
            if len(pair_list) < TOP_N:
                try:
                    pair_list.append({
                        "l":   int(float(row["length"])) if row["length"] else None,
                        "sa":  int(float(row["start_year_a"])) if row["start_year_a"] else None,
                        "sb":  int(float(row["start_year_b"])) if row["start_year_b"] else None,
                        "ic":  int(float(row["indicator_count"])) if row["indicator_count"] else None,
                        "ac":  round(float(row["avg_correlation"]), 3) if row["avg_correlation"] else 0.0,
                        "pps": round(float(row["pattern_power_score"]), 2) if row["pattern_power_score"] else 0.0,
                    })
                except (ValueError, TypeError):
                    pass

        if total_rows % 500_000 == 0 and total_rows > 0:
            print(f"    {total_rows:,} rows processed, {files_written} files written")

    if current_a_id is not None and pairs_buf:
        flush(current_a_id, pairs_buf)
        files_written += 1

    total_kb = sum(f.stat().st_size for f in out_dir.glob("*.json")) / 1024
    print(f"  Wrote {files_written} files to {out_dir}/ ({total_rows:,} rows, {total_kb:.0f} KB total)")


def generate_analogues(athena, workgroup: str, database: str, frontend_dir: Path, id_to_name: dict, id_to_alpha2: dict):
    """GH#280: Generate analogues.json — top 5 historical analogues per (country, category)."""
    print("\n=== Generating analogues.json (GH#280) ===")

    # #521 Fork B follow-up: read from recipes_deduped (bullet-6 longest-pattern
    # collapse view, #458) instead of qgi_data.recipes directly. Without this,
    # nested-length pattern instances (e.g. Saudi 2011/2010/2009 each match a
    # 3-yr/2-yr/1-yr pattern) inflate `recipe_count` by 3-5x in the analogues
    # output (analogues.json), which is consumed by the per-country precedent
    # cards on /countries/{id}/{category}. The view is a strict subset of the
    # table — same column shape, only fewer rows — so downstream JSON
    # consumers don't change.
    # NOTE: country-partners-index.json (the /patterns page input) is
    # generated by generate_partners_index() above, which reads
    # qgi_data.patterns directly and was never affected by this dedup.
    query = """
    WITH ranked AS (
        SELECT
            country_a_id,
            event_category,
            country_b_id,
            country_b_name,
            COUNT(*) AS recipe_count,
            AVG(avg_correlation) AS mean_corr,
            MAX(pps) AS best_pps,
            AVG(median_lead_time_b) AS avg_lead_years,
            ROW_NUMBER() OVER (
                PARTITION BY country_a_id, event_category
                ORDER BY COUNT(*) DESC, MAX(pps) DESC
            ) AS rn
        FROM qgi_data.recipes_deduped
        GROUP BY country_a_id, event_category, country_b_id, country_b_name
    )
    SELECT country_a_id, event_category, country_b_id, country_b_name,
           recipe_count, mean_corr, best_pps, avg_lead_years
    FROM ranked
    WHERE rn <= 5
    ORDER BY country_a_id, event_category, rn
    """

    print("  Running Athena query (scanning recipes_deduped view)...")
    qid = run_athena_query(athena, query, workgroup, database)
    rows = get_athena_results(athena, qid)
    print(f"  Got {len(rows)} analogue rows")

    # Build nested structure: {country_a_id: {event_category: [analogues]}}
    data: dict[str, dict[str, list]] = {}
    for row in rows:
        a_id = row["country_a_id"]
        cat = row["event_category"]
        b_id = row["country_b_id"]
        if a_id not in data:
            data[a_id] = {}
        if cat not in data[a_id]:
            data[a_id][cat] = []
        data[a_id][cat].append({
            "country_b_id": int(b_id),
            "country_b_name": row.get("country_b_name") or id_to_name.get(b_id, f"Country {b_id}"),
            "alpha2": id_to_alpha2.get(b_id, ""),
            "recipe_count": int(row["recipe_count"]),
            "mean_corr": round(float(row["mean_corr"]), 3),
            "best_pps": round(float(row["best_pps"]), 1),
            "avg_lead_years": round(float(row["avg_lead_years"]), 1) if row.get("avg_lead_years") else None,
        })

    out = frontend_dir / "analogues.json"
    with open(out, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    size_kb = os.path.getsize(out) / 1024
    total_countries = len(data)
    total_categories = sum(len(cats) for cats in data.values())
    print(f"  Wrote {out} ({size_kb:.0f} KB, {total_countries} countries, {total_categories} country-category pairs)")


# Top 6 indicators to include in trajectories (GH#287)
TRAJECTORY_INDICATORS = [
    {"id": "NY.GDP.PCAP.CD", "name": "GDP per capita (USD)", "unit": "USD"},
    {"id": "MS.MIL.XPND.GD.ZS", "name": "Military spending (% GDP)", "unit": "% GDP"},
    {"id": "SP.DYN.LE00.IN", "name": "Life expectancy (years)", "unit": "yrs"},
    {"id": "FP.CPI.TOTL.ZG", "name": "Inflation (CPI, annual %)", "unit": "%"},
    {"id": "NE.EXP.GNFS.ZS", "name": "Trade / exports (% GDP)", "unit": "% GDP"},
    {"id": "SP.POP.TOTL", "name": "Population, total", "unit": ""},
]


def generate_indicator_trajectories(
    athena,
    workgroup: str,
    database: str,
    frontend_dir: Path,
):
    """GH#287: Bake indicator trajectories with predicted points for country profiles.

    Queries Athena indicators_completed table once per indicator (6 total),
    groups by country, then writes indicator-trajectories.json.

    Output structure:
      {
        "<country_id>": {
          "years": [1960, ..., 2026],
          "indicators": [
            {"name": "...", "unit": "...", "data": [...], "predicted_from": 2024}
          ],
          "events": [{"year": 1991, "label": "..."}]
        }
      }
    """
    print("\n=== Generating indicator-trajectories.json (GH#287) ===")

    # Load events keyed by country name slug → [{"year":..., "title":...}]
    events_file = frontend_dir / "country-events.json"
    events_by_slug: dict[str, list[dict]] = {}
    if events_file.exists():
        with open(events_file, encoding="utf-8") as f:
            events_by_slug = json.load(f)
    print(f"  Loaded events for {len(events_by_slug)} countries")

    # Load country-risks.json to get country IDs and names for event lookup
    risks_file = frontend_dir / "country-risks.json"
    country_id_to_name: dict[str, str] = {}
    if risks_file.exists():
        with open(risks_file) as f:
            risks_raw = json.load(f)
        for cid, cdata in risks_raw.get("countries", {}).items():
            country_id_to_name[cid] = cdata["name"]
    print(f"  Loaded {len(country_id_to_name)} country IDs from country-risks.json")

    def name_to_slug(name: str) -> str:
        # #422 Bug 6 partial: this has diverged semantics from the canonical
        # `shared.slug.country_slug` (strips leading "the ", collapses
        # "of the" → "of") — curated-events lookups depend on both. A full
        # consolidation requires auditing every match site. Left as a
        # follow-up; shared implementation exists in qgi-ml/shared/slug.py.
        import re
        s = name.lower()
        s = re.sub(r"^the\s+", "", s)
        s = re.sub(r"\bof the\b", "of", s)
        s = re.sub(r"[-\s]+", "_", s)
        s = re.sub(r"[^a-z0-9_]", "", s)
        return s

    # Build {country_id -> [{"year": int, "label": str}]}
    country_events: dict[str, list[dict]] = {}
    for cid, cname in country_id_to_name.items():
        slug = name_to_slug(cname)
        raw_events = events_by_slug.get(slug, [])
        if raw_events:
            # Keep only year+title as label, deduplicate by year (keep first)
            seen_years: set[int] = set()
            compressed = []
            for ev in raw_events:
                yr = ev.get("year")
                if yr and yr not in seen_years:
                    seen_years.add(yr)
                    compressed.append({"year": yr, "label": ev.get("title", "")})
            country_events[cid] = compressed

    # Query each indicator from Athena once, accumulate per-country data
    # Structure: {country_id -> {indicator_idx -> {"data": {year: value}, "predicted": {year: bool}}}}
    country_indicator_data: dict[str, dict[int, dict]] = {}

    for idx, ind in enumerate(TRAJECTORY_INDICATORS):
        indicator_id = ind["id"]
        print(f"  Querying indicator {idx+1}/{len(TRAJECTORY_INDICATORS)}: {indicator_id}")

        query = f"""
        SELECT country, year, value, is_predicted
        FROM {database}.indicators_completed
        WHERE indicator_id = '{indicator_id}'
        ORDER BY country, year
        """

        try:
            qid = run_athena_query(athena, query, workgroup, database)
            rows = get_athena_results(athena, qid)
            print(f"    Got {len(rows)} rows")
        except RuntimeError as e:
            print(f"    WARN: Query failed for {indicator_id}: {e} — skipping")
            continue

        for row in rows:
            cid = row.get("country", "")
            if not cid:
                continue
            try:
                yr = int(float(row["year"])) if row.get("year") else None
                val_str = row.get("value", "")
                val = float(val_str) if val_str not in ("", None) else None
                is_pred = row.get("is_predicted", "false").lower() in ("true", "1", "t")
            except (ValueError, TypeError):
                continue
            if yr is None or val is None:
                continue

            if cid not in country_indicator_data:
                country_indicator_data[cid] = {}
            if idx not in country_indicator_data[cid]:
                country_indicator_data[cid][idx] = {"data": {}, "predicted": {}}
            country_indicator_data[cid][idx]["data"][yr] = val
            country_indicator_data[cid][idx]["predicted"][yr] = is_pred

    print(f"  Collected data for {len(country_indicator_data)} countries")

    # Determine global year range across all data
    all_years: set[int] = set()
    for ind_map in country_indicator_data.values():
        for ind_dict in ind_map.values():
            all_years.update(ind_dict["data"].keys())
    if not all_years:
        print("  WARN: No trajectory data found — skipping output")
        return

    year_min = min(all_years)
    year_max = max(all_years)
    year_range = list(range(year_min, year_max + 1))

    # Build name→ID lookup (reverse of country_id_to_name)
    country_name_to_id: dict[str, str] = {name: cid for cid, name in country_id_to_name.items()}

    # Build output: only include countries that appear in country-risks.json
    output: dict[str, dict] = {}
    for country_name, ind_map in country_indicator_data.items():
        cid = country_name_to_id.get(country_name)
        if not cid:
            continue  # no indicator data for this country

        indicators_out = []
        for idx, ind_meta in enumerate(TRAJECTORY_INDICATORS):
            if idx not in ind_map:
                continue
            ind_dict = ind_map[idx]
            data_map = ind_dict["data"]
            pred_map = ind_dict["predicted"]

            # Build aligned data array (null for missing years)
            data_arr = [data_map.get(yr) for yr in year_range]

            # Find first predicted year
            predicted_from = None
            for yr in year_range:
                if pred_map.get(yr):
                    predicted_from = yr
                    break

            entry: dict = {
                "name": ind_meta["name"],
                "unit": ind_meta["unit"],
                "data": data_arr,
            }
            if predicted_from is not None:
                entry["predicted_from"] = predicted_from

            indicators_out.append(entry)

        if not indicators_out:
            continue

        output[cid] = {
            "years": year_range,
            "indicators": indicators_out,
            "events": country_events.get(cid, []),
        }

    out_path = frontend_dir / "indicator-trajectories.json"
    with open(out_path, "w") as f:
        json.dump(output, f, separators=(",", ":"))
    size_kb = os.path.getsize(out_path) / 1024
    print(f"  Wrote {out_path} ({size_kb:.0f} KB, {len(output)} countries)")


def main():
    parser = argparse.ArgumentParser(description="Generate baked frontend JSON data")
    parser.add_argument("--bucket", required=True, help="S3 data lake bucket")
    parser.add_argument("--region", default="eu-central-1")
    parser.add_argument("--frontend-dir", required=True, help="Path to qgi-frontend/data/")
    parser.add_argument("--workgroup", default="QGI-Lambda-Workgroup")
    parser.add_argument("--database", default="qgi_data")
    parser.add_argument("--skip-partners", action="store_true", help="Skip partners index")
    parser.add_argument("--skip-density", action="store_true", help="Skip pattern density")
    parser.add_argument("--skip-twins", action="store_true", help="Skip structural twins")
    parser.add_argument("--skip-analogues", action="store_true", help="Skip analogues")
    parser.add_argument("--skip-pair-windows", action="store_true", help="Skip pair windows pre-compute")
    parser.add_argument("--skip-trajectories", action="store_true", help="Skip indicator trajectories")
    parser.add_argument("--pair-windows-limit", type=int, default=None,
                        help="LIMIT rows for pair-windows query (local testing only)")
    args = parser.parse_args()

    frontend_dir = Path(args.frontend_dir)
    if not frontend_dir.exists():
        print(f"ERROR: Frontend data dir not found: {frontend_dir}")
        sys.exit(1)

    athena = boto3.client("athena", region_name=args.region)
    s3 = boto3.client("s3", region_name=args.region)

    # GH#274: Partners index
    if not args.skip_partners:
        generate_partners_index(athena, s3, args.bucket, args.workgroup, args.database, frontend_dir)

    # GH#275: Pattern density + structural twins → embed in country-risks.json
    density = {}
    twins = {}

    if not args.skip_density:
        density = generate_pattern_density(athena, args.workgroup, args.database)

    if not args.skip_twins:
        twins = generate_structural_twins(athena, args.workgroup, args.database)

    # Load country names for twin enrichment
    countries_file = frontend_dir / "countries.json"
    id_to_name = {}
    id_to_alpha2 = {}
    if countries_file.exists():
        with open(countries_file) as f:
            for c in json.load(f):
                id_to_name[str(c["id"])] = c["name"]
                id_to_alpha2[str(c["id"])] = c.get("alpha_2", "")

    # Enrich twins with names
    for cid in twins:
        for t in twins[cid]:
            pid = str(t["partner_id"])
            t["partner_name"] = id_to_name.get(pid, f"Country {pid}")
            t["alpha2"] = id_to_alpha2.get(pid, "")

    # GH#281: Pair windows (per-country baked files)
    if not args.skip_pair_windows:
        generate_pair_windows(
            athena, args.workgroup, args.database, frontend_dir,
            limit=args.pair_windows_limit,
        )

    # GH#280: Analogues
    if not args.skip_analogues:
        generate_analogues(athena, args.workgroup, args.database, frontend_dir, id_to_name, id_to_alpha2)

    # GH#287: Indicator trajectories
    if not args.skip_trajectories:
        generate_indicator_trajectories(athena, args.workgroup, args.database, frontend_dir)

    # Write density and twins as separate files (cleaner than modifying country-risks.json)
    if density:
        out = frontend_dir / "pattern-density.json"
        with open(out, "w") as f:
            json.dump(density, f, separators=(",", ":"))
        size_kb = os.path.getsize(out) / 1024
        print(f"\n  Wrote {out} ({size_kb:.0f} KB)")

    if twins:
        out = frontend_dir / "structural-twins.json"
        with open(out, "w") as f:
            json.dump(twins, f, separators=(",", ":"))
        size_kb = os.path.getsize(out) / 1024
        print(f"  Wrote {out} ({size_kb:.0f} KB)")

    print("\n✓ Done!")


if __name__ == "__main__":
    main()
