"""
impact_analysis_591_filter.py — measure how many distinct indicator IDs
in qgi_data.recipes_aggregated.indicator_fingerprint would be filtered
out by the #591 allow-list-of-61.

Recurring CI regression role (per Phase 5 v0.0 Step 5 spec): this
script is invoked post-deploy on the staging recipes_aggregated table
to verify that the indicator_fingerprint distribution does not drift
outside the #591 allow-list-of-61 vocabulary. The original "1 = ship,
2 = ship + QA audit, 3 = HALT" rubric (Phase 5 v0.0 merge gate)
was a one-shot pre-merge use; the script has since graduated to a
recurring tool. THROWAWAY tag removed per #600 Finding 3.

Output: distinct indicator_id count in current fingerprint × per-event-
category breakdown × subset analysis vs allow-list. Joins to
indicator_map.csv to print id_strings (human-friendly, not just numbers).

Cost: ~$0.01 (recipes_aggregated is ~71 rows; indicator_fingerprint is
top-15 per row → ~1,065 unnested rows; trivial scan).

Usage:
  python qgi-ml/scripts/impact_analysis_591_filter.py \\
      --bucket qgi-data-lake-771606957899 \\
      --allow-list-path qgi-data/reference/indicator-allow-list.json
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
from pathlib import Path

import boto3

GLUE_DB = "qgi_data"
DEFAULT_WORKGROUP = "QGI-Lambda-Workgroup"
INDICATOR_MAP_S3_KEY = "pipeline-A-indicator-extractor/input/indicator_map.csv"


def athena_query(
    client, workgroup: str, sql: str, max_poll_iterations: int = 300,
) -> list[list[str]]:
    """Run an Athena query and return rows. Polls with a hard iteration
    cap so a stuck-in-RUNNING query doesn't hang the script forever
    (recurring CI role per #600 Finding 5). Default cap: 300 iterations
    × 1.5s = ~7.5 minutes — generous for the ~71-row recipes_aggregated
    table this script reads."""
    qid = client.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": GLUE_DB},
        WorkGroup=workgroup,
    )["QueryExecutionId"]
    state = "UNKNOWN"
    s = None
    for _ in range(max_poll_iterations):
        time.sleep(1.5)
        s = client.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        state = s["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
    else:
        raise TimeoutError(
            f"Athena {qid} still in state {state!r} after "
            f"{max_poll_iterations} poll iterations "
            f"(~{max_poll_iterations * 1.5:.0f}s). Aborting to avoid hang. "
            f"SQL: {sql[:300]}"
        )
    if state != "SUCCEEDED":
        raise RuntimeError(f"Athena {qid} {state}: "
                           f"{s['Status'].get('StateChangeReason', '')}\n{sql[:300]}")
    rows: list[list[str]] = []
    is_first = True
    for page in client.get_paginator("get_query_results").paginate(
        QueryExecutionId=qid
    ):
        for row in page["ResultSet"]["Rows"]:
            if is_first:
                is_first = False
                continue
            rows.append([col.get("VarCharValue", "") for col in row["Data"]])
    return rows


def fetch_id_string_map(bucket: str) -> dict[int, str]:
    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=bucket, Key=INDICATOR_MAP_S3_KEY)
    raw = obj["Body"].read().decode("utf-8")
    out: dict[int, str] = {}
    for row in csv.DictReader(io.StringIO(raw)):
        try:
            out[int(row["numeric_id"])] = row["id_string"].strip()
        except (ValueError, KeyError):
            continue
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--allow-list-path", required=True)
    parser.add_argument("--workgroup", default=DEFAULT_WORKGROUP)
    args = parser.parse_args()

    allow_list_path = Path(args.allow_list_path)
    payload = json.loads(allow_list_path.read_text(encoding="utf-8"))
    allow_set: set[int] = set(payload["allow_list_numeric_ids"])
    print(f"Loaded allow-list: {len(allow_set)} numeric_ids "
          f"(from {allow_list_path})")

    client = boto3.client("athena")

    # Q1: distinct indicator IDs in CURRENT fingerprint, with their TF-IDF
    # weight aggregated across categories (so we can see "high-impact
    # drops" not just "any drop").
    print("\n[Q1] Distinct indicator IDs in current "
          "qgi_data.recipes_aggregated.indicator_fingerprint")
    q1 = athena_query(client, args.workgroup, """
        WITH unnested AS (
            SELECT event_category,
                   t.row_field.indicator_id AS indicator_id,
                   t.row_field.frequency AS frequency,
                   t.row_field.tfidf_score AS tfidf_score
            FROM qgi_data.recipes_aggregated
            CROSS JOIN UNNEST(indicator_fingerprint) AS t (row_field)
        )
        SELECT cast(indicator_id AS bigint),
               count(distinct event_category) AS n_categories,
               cast(sum(tfidf_score) AS double) AS total_tfidf,
               cast(max(tfidf_score) AS double) AS max_tfidf
        FROM unnested
        GROUP BY indicator_id
        ORDER BY indicator_id
    """)
    fingerprint_ids: dict[int, dict] = {}
    for row in q1:
        fid = int(row[0])
        fingerprint_ids[fid] = {
            "n_categories": int(row[1]),
            "total_tfidf": float(row[2]),
            "max_tfidf": float(row[3]),
        }
    print(f"  {len(fingerprint_ids)} distinct indicator IDs currently in fingerprints")

    # Q2: total fingerprint cells (for context — Phase 4 v0.2 said 830/1069
    # were legacy)
    print("\n[Q2] Total fingerprint cells (event_category × indicator)")
    q2 = athena_query(client, args.workgroup, """
        SELECT count(*) AS n_cells, count(distinct event_category) AS n_cats
        FROM qgi_data.recipes_aggregated
        CROSS JOIN UNNEST(indicator_fingerprint) AS t (row_field)
    """)
    n_cells = int(q2[0][0])
    n_cats = int(q2[0][1])
    print(f"  Total cells: {n_cells:,}  Categories: {n_cats}")

    # Q3: cells in / out of allow-list (the 830-vs-239 reconciliation)
    in_allow_ids = sorted(set(fingerprint_ids) & allow_set)
    out_allow_ids = sorted(set(fingerprint_ids) - allow_set)
    cells_in = sum(d["n_categories"] for fid, d in fingerprint_ids.items()
                   if fid in allow_set)
    cells_out = sum(d["n_categories"] for fid, d in fingerprint_ids.items()
                    if fid not in allow_set)

    print("\n[Q3] Allow-list intersection")
    print(f"  In allow-list (would be KEPT):     {len(in_allow_ids)} unique IDs"
          f", {cells_in:,} cells")
    print(f"  Out of allow-list (would be DROPPED): {len(out_allow_ids)} "
          f"unique IDs, {cells_out:,} cells")
    print(f"  Total fingerprint cells:           {cells_in + cells_out:,}")
    if (cells_in + cells_out) > 0:
        print(f"  % cells dropped:                   "
              f"{100 * cells_out / (cells_in + cells_out):.1f}%")

    # Q4: name the would-be-dropped IDs by id_string (so we can spot-check
    # for "useful uncurated WB indicators").
    print("\n[Q4] Would-be-dropped indicators (sorted by total_tfidf desc)")
    print("  Higher TF-IDF = more impact on the fingerprint;")
    print("  prioritize these for Roshani's bucket-A consideration.")
    id_to_str = fetch_id_string_map(args.bucket)
    drop_rows = sorted(
        ((fid, fingerprint_ids[fid]) for fid in out_allow_ids),
        key=lambda x: -x[1]["total_tfidf"],
    )
    print(f"\n  {'numeric_id':>10}  {'n_cats':>7}  {'total_tfidf':>11}  "
          f"{'max_tfidf':>11}  id_string")
    print(f"  {'-' * 10}  {'-' * 7}  {'-' * 11}  {'-' * 11}  "
          f"{'-' * 30}")
    for fid, d in drop_rows:
        s = id_to_str.get(fid, "?")
        print(f"  {fid:>10}  {d['n_categories']:>7}  "
              f"{d['total_tfidf']:>11.4f}  {d['max_tfidf']:>11.4f}  {s}")

    # Q5: kept indicators (sanity — confirm catalog WB+VD codes show up)
    print("\n[Q5] Kept indicators (sorted by total_tfidf desc, top 20)")
    keep_rows = sorted(
        ((fid, fingerprint_ids[fid]) for fid in in_allow_ids),
        key=lambda x: -x[1]["total_tfidf"],
    )[:20]
    print(f"\n  {'numeric_id':>10}  {'n_cats':>7}  {'total_tfidf':>11}  "
          f"{'max_tfidf':>11}  id_string")
    print(f"  {'-' * 10}  {'-' * 7}  {'-' * 11}  {'-' * 11}  "
          f"{'-' * 30}")
    for fid, d in keep_rows:
        s = id_to_str.get(fid, "?")
        print(f"  {fid:>10}  {d['n_categories']:>7}  "
              f"{d['total_tfidf']:>11.4f}  {d['max_tfidf']:>11.4f}  {s}")

    # Outcome classification per founder rubric.
    print("\n--- OUTCOME ---")
    n_drop = len(out_allow_ids)
    print(f"  Distinct indicator IDs that would be dropped: {n_drop}")
    if n_drop <= 18:
        print("  Outcome 1: Only the 18 (or fewer). Ship; allow-list-of-61 "
              "== deny-list-of-18 in practice; no surprises.")
    elif n_drop < 30:
        print("  Outcome 2: 18 + a few more. Ship; document drops in PR "
              "description; QA audit.")
    else:
        print("  Outcome 3: Many more (50+ unique). HALT; the convening's "
              "contamination-scope understanding was incomplete; reconvene "
              "Majles before merging.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
