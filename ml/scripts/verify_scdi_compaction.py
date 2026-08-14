"""
verify_scdi_compaction.py — confirm scdis-compacted/ has identical row
counts to scdis/ before swapping the Glue catalog table location.

# THROWAWAY — run once after compaction, before Glue table swap.

Approach: register a TEMPORARY Athena external table pointing at the
compacted prefix, then COUNT(*) per country_a_id partition on both
source and compacted, compare. Aborts on first mismatch.

Cost: ~$0.75-1.00. Dominated by S3 GET REQUESTS not scan bytes —
COUNT(*) GROUP BY country_a_id touches every parquet footer in the
1.65M-file source table (roughly 1.65M GETs × $0.43/M ≈ $0.71). The
compacted side adds only ~200 GETs. Scan-byte cost is negligible
(~50-100 MB total). QA review 2026-05-03 corrected the original
$0.005-0.01 estimate which only counted scan bytes.

Usage:
  python scripts/verify_scdi_compaction.py \\
      --bucket qgi-data-lake-771606957899 \\
      --workgroup QGI-Lambda-Workgroup
  # (default --output-prefix uses workgroup-default if omitted; see notes)

Returns exit code 0 if all partitions match, 1 if any mismatch found.

Why a temporary table instead of just using `scdis_compacted` Glue
metadata? We don't want a permanent second Glue table — that would
require a Terraform PR for a one-time verification. Athena's
CREATE/DROP EXTERNAL TABLE is fast and reversible.
"""
from __future__ import annotations

import argparse
import sys
import time

import boto3

GLUE_DB = "qgi_data"
TEMP_TABLE = "scdis_compacted_verify"
DEFAULT_SOURCE_PREFIX = "pipeline-B-scdi-finder/scdis/"
DEFAULT_TARGET_PREFIX = "pipeline-B-scdi-finder/scdis-compacted/"


def athena_query(client, workgroup: str, output: str | None, sql: str) -> list[list[str]]:
    """Run a query, block until done, return rows (excluding header) as
    list of cell-string lists.

    `output` may be None when the workgroup has EnforceWorkGroupConfiguration
    with a centralized OutputLocation; in that case we omit ResultConfiguration
    and the workgroup applies its default.
    """
    kwargs = {
        "QueryString": sql,
        "QueryExecutionContext": {"Database": GLUE_DB},
        "WorkGroup": workgroup,
    }
    if output:
        kwargs["ResultConfiguration"] = {"OutputLocation": output}

    qid = client.start_query_execution(**kwargs)["QueryExecutionId"]
    while True:
        time.sleep(2.0)
        s = client.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        state = s["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
    if state != "SUCCEEDED":
        reason = s["Status"].get("StateChangeReason", "")
        raise RuntimeError(f"Athena query {qid} {state}: {reason}\nSQL: {sql[:200]}")

    rows: list[list[str]] = []
    paginator = client.get_paginator("get_query_results")
    is_first = True
    for page in paginator.paginate(QueryExecutionId=qid):
        for row in page["ResultSet"]["Rows"]:
            if is_first:
                is_first = False
                continue  # skip header
            rows.append([col.get("VarCharValue", "") for col in row["Data"]])
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--workgroup", default="QGI-Lambda-Workgroup")
    parser.add_argument("--output-prefix", default=None,
                        help="Athena query output S3 prefix. Omit if workgroup "
                             "has EnforceWorkGroupConfiguration (most QGI envs do).")
    parser.add_argument("--source-prefix", default=DEFAULT_SOURCE_PREFIX)
    parser.add_argument("--target-prefix", default=DEFAULT_TARGET_PREFIX)
    args = parser.parse_args()

    client = boto3.client("athena")
    tgt_location = f"s3://{args.bucket}/{args.target_prefix}"

    # Step 1: drop any leftover temp table (defensive — last run may have
    # crashed before cleanup).
    print(f"[1/4] Dropping any prior temp table {GLUE_DB}.{TEMP_TABLE}")
    try:
        athena_query(client, args.workgroup, args.output_prefix,
                     f"DROP TABLE IF EXISTS {GLUE_DB}.{TEMP_TABLE}")
    except Exception as exc:
        print(f"  warning: drop failed (continuing): {exc}")

    # Steps 2-4 wrapped in try/finally so the temp table is dropped even
    # if the COUNT(*) queries crash (e.g. Athena timeout, network error).
    # Without the finally, a query crash leaves a stale Glue catalog
    # entry pointing at scdis-compacted/ — confusing for any downstream
    # tooling that does SHOW TABLES. QA review 2026-05-03 (MINOR #3).
    src_map: dict[int, int] = {}
    tgt_map: dict[int, int] = {}
    try:
        # Step 2: create a temp Athena external table pointing at the
        # compacted prefix. Schema must match the production scdis Glue
        # table.
        print(f"[2/4] Creating temp table {GLUE_DB}.{TEMP_TABLE} -> {tgt_location}")
        create_sql = f"""
        CREATE EXTERNAL TABLE {GLUE_DB}.{TEMP_TABLE} (
            country_b_id          smallint,
            length                smallint,
            start_year_a          smallint,
            start_year_b          smallint,
            correlation           float,
            indicator_numeric_id  smallint,
            contains_predicted    boolean
        )
        PARTITIONED BY (country_a_id smallint)
        STORED AS PARQUET
        LOCATION '{tgt_location}'
        TBLPROPERTIES ('parquet.compress' = 'SNAPPY')
        """
        athena_query(client, args.workgroup, args.output_prefix, create_sql)
        athena_query(client, args.workgroup, args.output_prefix,
                     f"MSCK REPAIR TABLE {GLUE_DB}.{TEMP_TABLE}")

        # Step 3: count rows per country_a_id on BOTH tables
        print("[3/4] Querying row counts (source vs compacted)")
        print("  ...source table qgi_data.scdis")
        src_rows = athena_query(
            client, args.workgroup, args.output_prefix,
            "SELECT country_a_id, COUNT(*) FROM qgi_data.scdis "
            "GROUP BY country_a_id ORDER BY country_a_id"
        )
        print("  ...compacted table " + TEMP_TABLE)
        tgt_rows = athena_query(
            client, args.workgroup, args.output_prefix,
            f"SELECT country_a_id, COUNT(*) FROM {GLUE_DB}.{TEMP_TABLE} "
            f"GROUP BY country_a_id ORDER BY country_a_id"
        )

        src_map = {int(r[0]): int(r[1]) for r in src_rows}
        tgt_map = {int(r[0]): int(r[1]) for r in tgt_rows}
    finally:
        # Step 4: drop the temp table no matter what happened above.
        print(f"[4/4] Dropping temp table {GLUE_DB}.{TEMP_TABLE}")
        try:
            athena_query(client, args.workgroup, args.output_prefix,
                         f"DROP TABLE IF EXISTS {GLUE_DB}.{TEMP_TABLE}")
        except Exception as exc:
            print(f"  warning: drop failed: {exc}")

    # Compare
    all_ids = sorted(set(src_map) | set(tgt_map))
    print(f"\n  {'country_a_id':>14}  {'src_count':>12}  {'tgt_count':>12}  match")
    print("  " + "-" * 56)
    mismatches = []
    for cid in all_ids:
        s = src_map.get(cid, 0)
        t = tgt_map.get(cid, 0)
        ok = s == t
        marker = "YES" if ok else "NO  <----"
        print(f"  {cid:>12}  {s:>12,}  {t:>12,}  {marker}")
        if not ok:
            mismatches.append((cid, s, t))

    if mismatches:
        print(f"\nFAIL: {len(mismatches)} mismatches found. DO NOT swap Glue table location.")
        for cid, s, t in mismatches:
            print(f"  country_a_id={cid}: src={s} tgt={t} (delta={t - s})")
        return 1

    print(f"\nPASS: all {len(all_ids)} country partitions match. Safe to swap Glue location.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
