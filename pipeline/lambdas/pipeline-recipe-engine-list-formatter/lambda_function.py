"""
Phase 5b step 3: Recipe Engine list formatter — finer length-axis edition (#534).

History
-------
#490 (2026-04-29) introduced chunked INSERTs to clear Athena's 30-min DML wall.
#533 (2026-04-29) added size-tiered per-country chunking (Tier-1/2/3/4) so
tiny countries skip per-chunk overhead.
#534 (2026-04-30) replaces the 4-bucket pattern_tier (S/M/L/XL) chunking axis
with a 12-bucket length axis (5-year-wide bands: b03_07, b08_12, ..., b58_plus).
This gives ~3× finer granularity along the length dimension, cutting projected
megachunk runtime ~3× at 200-indicator scale (#510 follow-up).

Chunking strategy
-----------------
Axes available: event_category × length_bucket
  - event_category: 71 layer-3 values — natural join axis, already used as
    the GROUP BY key in recipes_aggregated.
  - length_bucket: 12 values (b03_07 .. b58_plus) derived from p.length.
    5-year-wide bands except b58_plus catch-all for length >= 58.
  - Combined ceiling: 71 × 12 = 852 chunks per Tier-3+ country.

Country tiers (size-tiered chunking, unchanged from #533):
  Tier-1 (<100K patterns post-JOIN): 1 INSERT per country, no filter.
  Tier-2 (100K - 1M):  chunk by event_category only.
  Tier-3 (1M - 10M):   chunk by (event_category × length_bucket).
  Tier-4 (>10M):       falls through to Tier-3; flagged as monitoring target.

Note on tier boundary calibration
---------------------------------
The 100K/1M/10M boundaries were set against JOIN-inflated post-enumerate counts
(see #534 ticket). Real underlying pattern volumes are ~5-50× smaller after
Athena Parquet predicate pushdown (empirically verified 2026-04-29 by shadow
query of the largest chunk: 263M reported, 22 MB actual scan, 76 s wall-clock
vs 30-min ceiling). At today's scale this means most countries fall through to
Tier-3+ — which is SAFE (everyone gets max granularity) but produces a skewed
tier_distribution. Recalibration is tracked separately as a #534 follow-up.

Recipe-identity contract preserved
----------------------------------
recipe_id = country_a + country_b + start_year_a + length + event_category.
Splitting on length_bucket (a recipe_id component, since pattern_tier S/M/L/XL
was itself derived from length) produces strictly disjoint recipes — no recipe
spans two chunks. GROUP BY recipe_id aggregation is per-recipe-local. Output
recipes table is byte-identical to the unchunked baseline, modulo PPS values
(chunk-local global_stats normalization, accepted upstream — see #532).

The output recipe row STILL contains a `pattern_tier` column (S/M/L/XL),
computed from `length` via the existing CASE in raw_recipes — the frontend
schema is untouched. length_bucket is purely an internal chunking dimension.

Output shape
------------
insert_items: list of {
    country_a_id: int,
    event_category: str | None,    # None for Tier-1 (no chunking)
    length_bucket: str | None,     # None for Tier-1 / Tier-2
    chunk_id: str,                 # "{cid}_{cat or *}_{bucket or *}"
    pattern_count: int,
    drop_partition_sql: str,       # 'SELECT 1' no-op (#14)
    insert_sql: str,               # INSERT with WHERE filters from this chunk's axes
}
"""

import os
import json
import time
import logging

import boto3

# #558: pattern_tier S/M/L/XL bucketing — single source of truth at
# lambdas/_shared/pattern_tier.py. The deploy workflow copies _shared/
# into each Lambda's bundle before zipping. NOTE: this is distinct
# from the 12-bucket LENGTH_BUCKETS axis defined below (#534) — the
# 12-bucket axis is for chunking strategy; pattern_tier is the
# user-facing 4-tier label.
from _shared.pattern_tier import pattern_tier_case_sql

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ATHENA_DB = os.environ.get("ATHENA_DATABASE", "qgi_data")
ATHENA_WG = os.environ.get("ATHENA_WORKGROUP", "QGI-Lambda-Workgroup")
S3_BUCKET = os.environ.get("S3_BUCKET", "")
S3_OUTPUT = os.environ.get("S3_OUTPUT_LOCATION", "")

# ─── Length-bucket axis (#534) ─────────────────────────────────────────────
# 12 buckets, each 5 years wide except the b58_plus catch-all. Pattern lengths
# in this pipeline start at 3 (the SCDI minimum) and run up to ~120 (full V-Dem
# historical span). The SQL CASE expression and Python length_to_bucket() must
# stay in lockstep — see test_length_to_bucket_python_matches_sql for the
# regression guard.
LENGTH_BUCKETS = (
    "b03_07",
    "b08_12",
    "b13_17",
    "b18_22",
    "b23_27",
    "b28_32",
    "b33_37",
    "b38_42",
    "b43_47",
    "b48_52",
    "b53_57",
    "b58_plus",
)

# Reverse mapping: bucket → (min_length_inclusive, max_length_inclusive).
#
# Note (#534 QA review CR-1): b03_07's lower bound is 0, not 3, even
# though SCDI floor is 3 by design. The enumerate query's CASE has a
# defensive `WHEN p.length < 3 THEN 'b03_07'` rule; if any sub-floor
# pattern slips through, the INSERT filter `p.length BETWEEN 0 AND 7`
# catches it instead of silently dropping the row. Defense-in-depth.
#
# b58_plus is unbounded above and special-cased in build_recipe_query to
# emit `p.length >= 58` rather than BETWEEN — keeps the query plan clean.
# The high upper-bound here is dead documentation (never substituted into
# any SQL); the tuple shape is preserved for symmetry.
BUCKET_RANGES = {
    "b03_07": (0, 7),
    "b08_12": (8, 12),
    "b13_17": (13, 17),
    "b18_22": (18, 22),
    "b23_27": (23, 27),
    "b28_32": (28, 32),
    "b33_37": (33, 37),
    "b38_42": (38, 42),
    "b43_47": (43, 47),
    "b48_52": (48, 52),
    "b53_57": (53, 57),
    "b58_plus": (58, None),  # upper bound unused — see >= filter in build_recipe_query
}

# SQL CASE expression that maps p.length to a length_bucket label. Used in
# both the enumerate query (for GROUP BY) and the chunk INSERTs (no — the
# INSERT uses a simpler `length BETWEEN lo AND hi` filter, see
# build_recipe_query). Keep this in sync with length_to_bucket() below.
LENGTH_BUCKET_CASE_SQL = """
            CASE
                WHEN p.length < 3 THEN 'b03_07'
                WHEN p.length BETWEEN 3 AND 7 THEN 'b03_07'
                WHEN p.length BETWEEN 8 AND 12 THEN 'b08_12'
                WHEN p.length BETWEEN 13 AND 17 THEN 'b13_17'
                WHEN p.length BETWEEN 18 AND 22 THEN 'b18_22'
                WHEN p.length BETWEEN 23 AND 27 THEN 'b23_27'
                WHEN p.length BETWEEN 28 AND 32 THEN 'b28_32'
                WHEN p.length BETWEEN 33 AND 37 THEN 'b33_37'
                WHEN p.length BETWEEN 38 AND 42 THEN 'b38_42'
                WHEN p.length BETWEEN 43 AND 47 THEN 'b43_47'
                WHEN p.length BETWEEN 48 AND 52 THEN 'b48_52'
                WHEN p.length BETWEEN 53 AND 57 THEN 'b53_57'
                ELSE 'b58_plus'
            END
"""


def length_to_bucket(length: int) -> str:
    """Map a pattern length (in years) to its 5-year-wide bucket label.

    Mirrors LENGTH_BUCKET_CASE_SQL exactly — any change in one MUST be
    reflected in the other (regression-tested).

    Length < 3 is theoretically impossible (SCDI floor) but defaults to the
    smallest bucket for safety. Length >= 58 falls into the b58_plus catch-all.
    """
    if length < 3:
        return "b03_07"
    if length >= 58:
        return "b58_plus"
    bin_start = 3 + ((length - 3) // 5) * 5
    bin_end = bin_start + 4
    return f"b{bin_start:02d}_{bin_end:02d}"


# ─── Smart-chunking thresholds (#533, calibration TODO #534-followup) ──────
# Per-country pattern_count buckets that decide chunking shape. These count
# JOIN-inflated pattern_counts from the enumerate query (NOT raw pattern rows
# — recalibration to underlying counts is a #534 follow-up).
TIER1_MAX_PATTERNS = 100_000  # below: single INSERT, no chunking
TIER2_MAX_PATTERNS = 1_000_000  # below: chunk by event_category only
TIER3_MAX_PATTERNS = 10_000_000  # below: chunk by (event_category, length_bucket)
# Tier 4 above TIER3_MAX_PATTERNS: future axis (e.g., decade buckets); for now
# Tier 4 falls through to Tier 3 chunking with a warning logged. With #534's
# 12-bucket length axis, even Tier-4 countries get ~10× finer granularity than
# pre-#534, so the urgency of a 4th axis has dropped significantly.


def classify_country_tier(total_pattern_count: int) -> str:
    """Return 'tier1' / 'tier2' / 'tier3' / 'tier4' based on the country's
    total pattern count. See module-level threshold comments for rationale.
    """
    if total_pattern_count < TIER1_MAX_PATTERNS:
        return "tier1"
    if total_pattern_count < TIER2_MAX_PATTERNS:
        return "tier2"
    if total_pattern_count < TIER3_MAX_PATTERNS:
        return "tier3"
    return "tier4"


athena = boto3.client("athena")
s3 = boto3.client("s3")


def _s3_delete_prefix(prefix: str) -> None:
    """Delete all S3 objects under the given prefix in the data-lake bucket.

    Used pre-DDL to clear any stale partition files at
    RECIPES_STABLE_PREFIX so `CREATE EXTERNAL TABLE IF NOT EXISTS` (SF
    state 5b.3a) attaches to a CLEAN prefix and the downstream INSERTs
    don't duplicate rows from a prior run's partitions.

    Mirrors the canonical paginated-delete helper in
    `pipeline-recipe-engine-finalize/lambda_function.py:1037-1052`.
    Batches deletes in groups of 1000 (S3 API max).

    Idempotent: returns silently on an empty prefix.

    Why this lives HERE (not in SF as a separate Lambda state):
    Adding a dedicated Lambda + SF state for a 200ms paginated-delete
    would add ~1s of cold-start + state-transition overhead per run.
    The list-formatter already has the S3 client and the stable-prefix
    constant. Calling it inline is the cheapest correct option.

    Race-safety: this Lambda runs once per pipeline run as the first
    interactive step in Phase 5b (5b.3, immediately after 5b.1 DROP).
    There's no concurrent writer at this point in the workflow — the
    paginated-delete-then-INSERT-INTO sequence is single-threaded by
    the SF state ordering.
    """
    paginator = s3.get_paginator("list_objects_v2")
    keys_to_delete = []
    total_deleted = 0
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys_to_delete.append({"Key": obj["Key"]})
            if len(keys_to_delete) >= 1000:
                s3.delete_objects(Bucket=S3_BUCKET, Delete={"Objects": keys_to_delete})
                total_deleted += len(keys_to_delete)
                keys_to_delete = []
    if keys_to_delete:
        s3.delete_objects(Bucket=S3_BUCKET, Delete={"Objects": keys_to_delete})
        total_deleted += len(keys_to_delete)
    logger.info(f"Cleared s3://{S3_BUCKET}/{prefix} — deleted {total_deleted} objects (pre-DDL clean per #622).")


def lambda_handler(event, context):
    run_id = event.get("run_id", "manual")
    cutoff_year = event.get("cutoff_year")

    logger.info(
        f"Recipe engine list formatter (#534 length-bucket edition) starting. "
        f"run_id={run_id}, cutoff_year={cutoff_year}"
    )

    # #622 (2026-05-16): clear the stable S3 prefix BEFORE generating
    # ddl_sql. Sequence guarantees:
    #   1. 5b.1 DROP TABLE — removes Glue catalog entry only (Athena
    #      DROP doesn't touch S3 files).
    #   2. THIS LAMBDA STEP 0 — paginated-delete every object under
    #      pipeline-recipe-engine/output/recipes/. Without this step,
    #      stale partition files from prior runs survive at the stable
    #      prefix, get re-attached by 5b.3a's `CREATE EXTERNAL TABLE
    #      IF NOT EXISTS`, and downstream INSERTs append on top of
    #      them — producing duplicate rows after the 2nd pipeline run.
    #      This is the data-correctness fix QA review on qgi-infra
    #      PR #25 surfaced as BLOCK-level.
    #   3. 5b.3a (qgi-infra) — CREATE EXTERNAL TABLE IF NOT EXISTS at
    #      the now-empty stable prefix.
    #   4. 5b.4 + 5b.5 — INSERT INTO writes fresh partitions.
    _s3_delete_prefix(RECIPES_STABLE_PREFIX)

    # Step 1: enumerate (country_a_id, event_category, length_bucket, count)
    # combos that actually exist. Sorted ASC by count so the smallest chunk
    # becomes the seed (keeps the INSERT fast regardless of country size).
    query_id = _run_enumerate_query(cutoff_year)

    # Step 2: fetch results
    chunks = _fetch_chunk_rows(query_id)
    if not chunks:
        raise RuntimeError(
            "No (country_a_id, event_category, length_bucket) combos returned "
            "from the enumerate query. Phase 4 must have failed to populate "
            "the patterns table, or the upstream query is malformed."
        )

    # Step 2.5: aggregate per country, classify each country's tier, emit
    # adaptively-shaped chunks. See module-level threshold comments (#533).
    country_totals: dict[int, int] = {}
    for c in chunks:
        country_totals[c["country_a_id"]] = country_totals.get(c["country_a_id"], 0) + c["pattern_count"]
    country_tiers: dict[int, str] = {cid: classify_country_tier(total) for cid, total in country_totals.items()}
    tier_distribution = {
        t: sum(1 for tt in country_tiers.values() if tt == t) for t in ("tier1", "tier2", "tier3", "tier4")
    }
    logger.info(
        f"Fetched {len(chunks)} (country, cat, length_bucket) combos across "
        f"{len(country_totals)} countries. Tier distribution: {tier_distribution}. "
        f"Smallest combo: country_a_id={chunks[0]['country_a_id']} "
        f"cat={chunks[0]['event_category']} bucket={chunks[0]['length_bucket']} "
        f"({chunks[0]['pattern_count']} patterns). "
        f"Largest combo: country_a_id={chunks[-1]['country_a_id']} "
        f"cat={chunks[-1]['event_category']} bucket={chunks[-1]['length_bucket']} "
        f"({chunks[-1]['pattern_count']} patterns)."
    )

    # Build adaptive chunks per country. emit_chunks is the deduplicated
    # list of {country_a_id, event_category|None, length_bucket|None,
    # pattern_count} dicts for the SF Map state. Sorted ASC by pattern
    # count so the smallest chunk lands as the seed CTAS.
    emit_chunks: list[dict] = []

    # Group raw enumerate results by country
    by_country: dict[int, list[dict]] = {}
    for c in chunks:
        by_country.setdefault(c["country_a_id"], []).append(c)

    for cid, country_combos in by_country.items():
        tier = country_tiers[cid]
        country_total = country_totals[cid]

        if tier == "tier1":
            # No chunking: 1 INSERT per country with no category/bucket filter.
            emit_chunks.append(
                {
                    "country_a_id": cid,
                    "event_category": None,
                    "length_bucket": None,
                    "pattern_count": country_total,
                }
            )
        elif tier == "tier2":
            # Aggregate combos by category; emit 1 chunk per (country, category).
            by_cat: dict[str, int] = {}
            for combo in country_combos:
                by_cat[combo["event_category"]] = by_cat.get(combo["event_category"], 0) + combo["pattern_count"]
            for cat, count in by_cat.items():
                emit_chunks.append(
                    {
                        "country_a_id": cid,
                        "event_category": cat,
                        "length_bucket": None,
                        "pattern_count": count,
                    }
                )
        else:
            # Tier 3 (and Tier 4 for now — see module-level comment): emit
            # the raw enumerate combos as-is, one chunk per (cat × bucket).
            if tier == "tier4":
                logger.warning(
                    f"country_a_id={cid} has {country_total} patterns — "
                    f"Tier-4 (further axis like decade buckets) is not yet "
                    f"implemented; falling through to Tier-3 (event_category "
                    f"× length_bucket = {len(country_combos)} chunks). With "
                    f"#534's 12-bucket length axis, individual chunks should "
                    f"still be tractable; monitor runtimes."
                )
            for combo in country_combos:
                emit_chunks.append(
                    {
                        "country_a_id": cid,
                        "event_category": combo["event_category"],
                        "length_bucket": combo["length_bucket"],
                        "pattern_count": combo["pattern_count"],
                    }
                )

    # Sort ASC by pattern count so the smallest chunk becomes the seed
    # INSERT (was seed CTAS pre-#622, but the smallest-chunk-as-seed
    # invariant is unchanged — the SQL emitted just happens to be
    # INSERT INTO now rather than CREATE TABLE AS).
    emit_chunks.sort(key=lambda c: c["pattern_count"])

    logger.info(
        f"Smart-chunking emitted {len(emit_chunks)} chunks "
        f"(was {len(chunks)} before tier-classification — "
        f"{(1 - len(emit_chunks) / max(len(chunks), 1)) * 100:.1f}% reduction)."
    )

    # Step 3: seed = smallest emitted chunk. Post-#622 (2026-05-16) this is
    # an INSERT INTO (not CTAS) — the new SF state `5b.3a Create External
    # Table` runs the DDL emitted as `ddl_sql` below, creating the table
    # at the stable prefix `s3://{bucket}/{RECIPES_STABLE_PREFIX}`.
    # The previous CTAS path landed data in `query_results/tables/<uuid>/`
    # with 1-day expiry, driving the May 2-5 cost spikes (~$13/day GETs).
    #
    # The seed-chunk pattern_count guard protects against future
    # degradations of the smart-chunking math sending a Tier-3+ slice
    # through the seed slot — that would expose the seed INSERT to
    # Athena's 30-min DML wall. The chunks list is sorted ASC at line
    # 305 so a healthy seed is far below 100K.
    seed = emit_chunks[0]
    if seed["pattern_count"] > SEED_CHUNK_PATTERN_COUNT_GUARD:
        raise RuntimeError(
            f"Seed chunk pattern_count={seed['pattern_count']} exceeds the "
            f"guard ({SEED_CHUNK_PATTERN_COUNT_GUARD}); the smart-chunking "
            f"math has degraded. Seed chunk metadata: country_a_id="
            f"{seed['country_a_id']}, event_category={seed['event_category']!r}, "
            f"length_bucket={seed['length_bucket']!r}. Refusing to emit a "
            "seed INSERT that risks the 30-min Athena DML wall."
        )
    seed_sql = build_recipe_query(
        cutoff_year,
        country_a_id=seed["country_a_id"],
        event_category=seed["event_category"],
        length_bucket=seed["length_bucket"],
        mode="insert",
    )

    # Step 4: all remaining chunks → INSERT items
    insert_items = []
    for chunk in emit_chunks[1:]:
        cid = chunk["country_a_id"]
        cat = chunk["event_category"]  # may be None for Tier-1 chunks
        bucket = chunk["length_bucket"]  # may be None for Tier-1 / Tier-2 chunks
        # chunk_id encodes the chunk's filter shape — None → '*' for legibility
        chunk_id = f"{cid}_{cat if cat is not None else '*'}_{bucket if bucket is not None else '*'}"
        insert_items.append(
            {
                "country_a_id": cid,
                "event_category": cat,
                "length_bucket": bucket,
                "chunk_id": chunk_id,
                "pattern_count": chunk["pattern_count"],
                # NO-OP DROP per #14 (a42b178): the SF state `5b.1 Drop Recipes
                # Table` already dropped the whole `recipes` table before the
                # Map state began, and `5b.4 Seed CTAS` recreated it fresh.
                # Per-chunk `DROP PARTITION IF EXISTS` was redundant *and*
                # dangerous (parallel Glue:BatchDeletePartition contention).
                # SELECT 1 keeps the SF schema unchanged while never touching Glue.
                "drop_partition_sql": "SELECT 1",
                "insert_sql": build_recipe_query(
                    cutoff_year,
                    country_a_id=cid,
                    event_category=cat,
                    length_bucket=bucket,
                    mode="insert",
                ),
            }
        )

    # #622 (2026-05-16): generate the DDL inline so the SF state can run
    # CREATE EXTERNAL TABLE before the seed INSERT lands. DDL is
    # co-located with the SELECT-list it must match — schema drift is
    # caught at test time via test_ddl_select_column_parity, not at run
    # time via a cryptic Athena schema-mismatch error.
    ddl_sql = build_external_table_ddl(S3_BUCKET)

    logger.info(
        f"Generated seed INSERT for chunk "
        f"country_a_id={seed['country_a_id']}, "
        f"cat={seed['event_category']}, bucket={seed['length_bucket']} "
        f"({len(seed_sql)} chars), DDL ({len(ddl_sql)} chars) at stable "
        f"prefix s3://{S3_BUCKET}/{RECIPES_STABLE_PREFIX}, and "
        f"{len(insert_items)} chunk INSERT items."
    )

    # Step 5: write insert_items to S3 (payload exceeds SF 256KB limit).
    items_key = f"recipe-engine/insert-items-{run_id}.json"
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=items_key,
        Body=json.dumps(insert_items),
        ContentType="application/json",
    )
    logger.info(f"Wrote {len(insert_items)} insert items to s3://{S3_BUCKET}/{items_key}")

    return {
        "statusCode": 200,
        "run_id": run_id,
        "cutoff_year": cutoff_year,
        "seed_country_id": seed["country_a_id"],
        "seed_pattern_count": seed["pattern_count"],
        "seed_sql": seed_sql,
        # #622: DDL string consumed by SF state `5b.3a Create External
        # Table` to create the recipes table at the stable prefix
        # before the seed INSERT runs.
        "ddl_sql": ddl_sql,
        "insert_items_bucket": S3_BUCKET,
        "insert_items_key": items_key,
        # partitions_total = total emitted chunks after smart-chunking
        # (1 seed + N insert items). Used by 5b.6 Finalize for logging.
        "partitions_total": len(emit_chunks),
        # tier_distribution surfaces the size-tier classification for ops
        # observability — first place to look if a future run looks slow.
        "tier_distribution": tier_distribution,
    }


def _run_enumerate_query(cutoff_year=None):
    """Run a GROUP BY query that returns (country_a_id, event_category,
    length_bucket, count) for every combo that actually exists in patterns,
    sorted ASC by count.

    Returns the query execution ID. Polls until SUCCEEDED.
    """
    cutoff_filter = ""
    if cutoff_year:
        cutoff_filter = (
            f"AND (p.start_year_a + p.length) <= {cutoff_year} AND (p.start_year_b + p.length) <= {cutoff_year}"
        )

    sql = f"""
        SELECT
            p.country_a_id,
            ea.category_normalized AS event_category,
            {LENGTH_BUCKET_CASE_SQL.strip()} AS length_bucket,
            count(*) AS pc
        FROM {ATHENA_DB}.patterns p
        INNER JOIN {ATHENA_DB}.events ea
            ON ea.country_id = p.country_a_id
            AND ea.year BETWEEN
                (p.start_year_a + p.length - greatest(1, cast(ceil(p.length * 0.15) as integer)))
                AND
                (p.start_year_a + p.length + greatest(1, cast(ceil(p.length * 0.15) as integer)))
        WHERE p.country_a_id IS NOT NULL
        {cutoff_filter}
        GROUP BY p.country_a_id, ea.category_normalized,
            {LENGTH_BUCKET_CASE_SQL.strip()}
        ORDER BY pc ASC
    """
    response = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": ATHENA_DB},
        WorkGroup=ATHENA_WG,
    )
    query_id = response["QueryExecutionId"]
    logger.info(f"Enumerate (length-bucket) query {query_id}: started")

    while True:
        status = athena.get_query_execution(QueryExecutionId=query_id)
        state = status["QueryExecution"]["Status"]["State"]
        if state == "SUCCEEDED":
            logger.info(f"Enumerate query {query_id}: SUCCEEDED")
            return query_id
        if state in ("FAILED", "CANCELLED"):
            reason = status["QueryExecution"]["Status"].get("StateChangeReason", "unknown")
            raise RuntimeError(f"Enumerate query {state}: {reason}")
        time.sleep(1)


def _fetch_chunk_rows(query_id):
    """Page through Athena query results and return a list of dicts:
    [{'country_a_id': int, 'event_category': str,
      'length_bucket': str, 'pattern_count': int}, ...]
    sorted ASC by pattern_count (the upstream query already orders this way).
    """
    rows = []
    headers_seen = False
    next_token = None
    while True:
        kwargs = {"QueryExecutionId": query_id}
        if next_token:
            kwargs["NextToken"] = next_token
        result = athena.get_query_results(**kwargs)
        result_rows = result["ResultSet"]["Rows"]
        if not headers_seen:
            result_rows = result_rows[1:]  # skip header row
            headers_seen = True
        for row in result_rows:
            cells = row.get("Data", [])
            if len(cells) < 4:
                continue
            raw_id = cells[0].get("VarCharValue")
            raw_cat = cells[1].get("VarCharValue")
            raw_bucket = cells[2].get("VarCharValue")
            raw_cnt = cells[3].get("VarCharValue")
            if not all([raw_id, raw_cat, raw_bucket, raw_cnt]):
                continue
            try:
                rows.append(
                    {
                        "country_a_id": int(raw_id),
                        "event_category": raw_cat,
                        "length_bucket": raw_bucket,
                        "pattern_count": int(raw_cnt),
                    }
                )
            except ValueError:
                logger.warning(
                    f"Skipping non-parseable row: id={raw_id!r} cat={raw_cat!r} bucket={raw_bucket!r} cnt={raw_cnt!r}"
                )
        next_token = result.get("NextToken")
        if not next_token:
            break
    return rows


def build_recipe_query(
    cutoff_year=None,
    country_a_id=None,
    event_category=None,
    length_bucket=None,
    mode="insert",
):
    """Build the per-chunk recipe SQL.

    Post-#622 (2026-05-16) the production seed path emits INSERT INTO
    instead of CTAS — see SF state 5b.4 (formerly "Seed CTAS", now
    "Seed INSERT") and the new 5b.3a "Create External Table" state
    that runs the DDL emitted at $.recipe_list.ddl_sql. The default
    `mode='insert'` reflects the new path; `mode='ctas'` is retained
    for backward-compat with any out-of-band tooling that still calls
    this function with the explicit CTAS flag.

    Filters applied to the patterns scan / events JOIN (each chunk scans only
    its slice; total scan across all chunks equals the original single-country
    scan with no duplication):
      - AND p.country_a_id = N                              (mandatory)
      - AND ea.category_normalized = '<event_category>'    (Tier-2+ only)
      - AND p.length BETWEEN lo AND hi                      (Tier-3+ only)

    The recipe-identity contract holds because recipe_id includes
    {country_a, country_b, start_year_a, length, event_category} — splitting
    on length (a recipe_id component) produces strictly disjoint recipes.
    GROUP BY recipe_id is per-recipe-local; same answer regardless of chunking.
    Output recipe row STILL has pattern_tier (S/M/L/XL) column, derived from
    length via the existing CASE expression in the raw_recipes CTE.

    Parameters
    ----------
    cutoff_year   : int | None
    country_a_id  : int          — MANDATORY
    event_category: str | None   — None for Tier-1 only
    length_bucket : str | None   — None for Tier-1 / Tier-2; one of LENGTH_BUCKETS
    mode          : 'ctas' | 'insert'
    """
    if country_a_id is None:
        raise ValueError("country_a_id is mandatory for build_recipe_query.")

    pattern_filters = [f"p.country_a_id = {int(country_a_id)}"]
    event_filter_a = ""
    event_filter_b = ""

    if cutoff_year:
        pattern_filters.append(
            f"(p.start_year_a + p.length) <= {cutoff_year} AND (p.start_year_b + p.length) <= {cutoff_year}"
        )
        event_filter_a = f"AND ea.year <= {cutoff_year}"
        event_filter_b = f"AND eb.year <= {cutoff_year}"

    # Chunk filters — both optional in the new path (Tier-1/2 may omit).
    if event_category is not None:
        # Single-quote escape: event category names are underscore-delimited
        # ASCII identifiers from the taxonomy; no quotes expected, but be safe.
        safe_cat = event_category.replace("'", "''")
        event_filter_a += f"\n            AND ea.category_normalized = '{safe_cat}'"

    if length_bucket is not None:
        if length_bucket not in BUCKET_RANGES:
            raise ValueError(f"Unknown length_bucket: {length_bucket!r}. Valid: {LENGTH_BUCKETS!r}")
        lo, hi = BUCKET_RANGES[length_bucket]
        if length_bucket == "b58_plus":
            # Open-ended upper bound — use >= rather than BETWEEN to avoid
            # leaning on the 999999 sentinel (and keep the query plan clean).
            pattern_filters.append(f"p.length >= {lo}")
        else:
            pattern_filters.append(f"p.length BETWEEN {lo} AND {hi}")

    pattern_where = "WHERE " + " AND ".join(f"({f})" for f in pattern_filters)

    select_body = f"""
    WITH raw_recipes AS (
        SELECT
            concat(cast(p.country_a_id as varchar), '-',
                   cast(p.country_b_id as varchar), '-',
                   cast(p.start_year_a as varchar), '-',
                   cast(p.length as varchar), '-',
                   ea.category_normalized) as recipe_id,
            ea.category_normalized as event_category,
            p.pattern_id,
            p.country_a_id,
            p.country_b_id,
            ca.name_1 as country_a_name,
            cb.name_1 as country_b_name,
            p.start_year_a,
            p.start_year_b,
            p.length,
            p.avg_correlation,
            cast(p.start_year_a + p.length as smallint) as end_year_a,
            cast(p.start_year_b + p.length as smallint) as end_year_b,
            cast(greatest(1, cast(ceil(p.length * 0.15) as integer)) as smallint) as event_window,
            ea.year as event_year_a,
            eb.year as event_year_b,
            ea.title as event_title_a,
            eb.title as event_title_b,
            p.indicator_count,
            p.pattern_power_score,
            -- #558: pattern_tier SQL centralized in _shared/pattern_tier.py
            COALESCE(p.pattern_tier, {pattern_tier_case_sql("p.length")}) AS pattern_tier,
            COALESCE(p.contains_predicted, FALSE) AS contains_predicted
        FROM {ATHENA_DB}.patterns p
        INNER JOIN {ATHENA_DB}.events ea
            ON ea.country_id = p.country_a_id
            AND ea.year BETWEEN
                (p.start_year_a + p.length - greatest(1, cast(ceil(p.length * 0.15) as integer)))
                AND
                (p.start_year_a + p.length + greatest(1, cast(ceil(p.length * 0.15) as integer)))
            {event_filter_a}
        INNER JOIN {ATHENA_DB}.events eb
            ON eb.country_id = p.country_b_id
            AND eb.category_normalized = ea.category_normalized
            AND eb.year BETWEEN
                (p.start_year_b + p.length - greatest(1, cast(ceil(p.length * 0.15) as integer)))
                AND
                (p.start_year_b + p.length + greatest(1, cast(ceil(p.length * 0.15) as integer)))
            {event_filter_b}
        LEFT JOIN {ATHENA_DB}.countries ca ON cast(ca.id as integer) = p.country_a_id
        LEFT JOIN {ATHENA_DB}.countries cb ON cast(cb.id as integer) = p.country_b_id
        {pattern_where}
    ),
    recipes_aggregated AS (
        SELECT
            recipe_id,
            arbitrary(event_category)        AS event_category,
            arbitrary(pattern_id)            AS pattern_id,
            arbitrary(country_b_id)          AS country_b_id,
            arbitrary(country_a_name)        AS country_a_name,
            arbitrary(country_b_name)        AS country_b_name,
            arbitrary(start_year_a)          AS start_year_a,
            arbitrary(start_year_b)          AS start_year_b,
            arbitrary(length)                AS length,
            arbitrary(avg_correlation)       AS avg_correlation,
            arbitrary(end_year_a)            AS end_year_a,
            arbitrary(end_year_b)            AS end_year_b,
            arbitrary(event_window)          AS event_window,
            min(event_year_a)                AS event_year_a,
            min(event_year_b)                AS event_year_b,
            arbitrary(event_title_a)         AS event_title_a,
            arbitrary(event_title_b)         AS event_title_b,
            arbitrary(indicator_count)       AS indicator_count,
            arbitrary(pattern_power_score)   AS pattern_power_score,
            arbitrary(pattern_tier)          AS pattern_tier,
            bool_or(contains_predicted)      AS contains_predicted,
            cast(count(*) as bigint)         AS instance_count,
            cast(approx_percentile(cast(event_year_b - end_year_b as double), 0.5) as smallint)
                AS median_lead_time_b,
            cast(min(event_year_b - end_year_b) as smallint) AS min_lead_time_b,
            cast(max(event_year_b - end_year_b) as smallint) AS max_lead_time_b,
            cast(approx_percentile(cast(event_year_a - end_year_a as double), 0.5) as smallint)
                AS median_lead_time_a,
            country_a_id
        FROM raw_recipes
        GROUP BY recipe_id, country_a_id
    ),
    global_stats AS (
        SELECT
            cast(max(instance_count) as double)  AS max_inst,
            cast(max(indicator_count) as double) AS max_ind
        FROM recipes_aggregated
    )
    SELECT
        r.recipe_id,
        r.event_category,
        r.pattern_id,
        r.country_b_id,
        r.country_a_name,
        r.country_b_name,
        r.start_year_a,
        r.start_year_b,
        r.length,
        r.avg_correlation,
        r.end_year_a,
        r.end_year_b,
        r.event_window,
        r.event_year_a,
        r.event_year_b,
        r.event_title_a,
        r.event_title_b,
        r.indicator_count,
        r.pattern_power_score,
        r.instance_count,
        r.pattern_tier,
        r.median_lead_time_b,
        r.min_lead_time_b,
        r.max_lead_time_b,
        r.median_lead_time_a,
        cast(
            (
                0.35 * r.avg_correlation
                + 0.30 * (ln(cast(r.instance_count as double) + 1.0)
                          / nullif(ln(g.max_inst + 1.0), 0.0))
                + 0.20 * (ln(cast(r.indicator_count as double) + 1.0)
                          / nullif(ln(g.max_ind + 1.0), 0.0))
                + 0.15 * (1.0 / (1.0 + 0.05 * greatest(0, cast(r.length as double) - 10.0)))
            ) * 100.0
            AS double
        ) AS pps,
        r.contains_predicted,
        -- Partition column MUST be last (Athena CTAS requirement, #145)
        r.country_a_id
    FROM recipes_aggregated r
    CROSS JOIN global_stats g
    """

    if mode == "ctas":
        # NOTE (#622, 2026-05-16): the 'ctas' mode is retained for
        # backward-compat but is no longer used by the production path —
        # the seed chunk flips to 'insert' after the new SF 5b.2 state
        # creates the external table at the stable prefix. Live SF
        # workflows that still reference build_recipe_query(mode='ctas')
        # land at query_results/tables/<uuid>/ with 1-day expiry, which
        # caused the $13/day cost leak.
        return f"""
        CREATE TABLE {ATHENA_DB}.recipes
        WITH (
            format = 'PARQUET',
            write_compression = 'SNAPPY',
            partitioned_by = ARRAY['country_a_id']
        ) AS
        {select_body}
        """.strip()
    elif mode == "insert":
        return f"INSERT INTO {ATHENA_DB}.recipes\n{select_body}".strip()
    else:
        raise ValueError(f"Unknown build_recipe_query mode: {mode!r}")


# ─── #622 (2026-05-16) ──────────────────────────────────────────────────────
# Stable S3 prefix for the recipes table (replaces the CTAS-into-
# query_results/tables/<uuid>/ pattern that had 1-day expiry and drove
# the May 2-5 cost spikes — see qgi-aws-tf#622, #739).
#
# The Lambda emits the DDL alongside seed_sql / insert_items so SF state
# `5b.3a Create External Table` can execute it BEFORE 5b.4 Seed INSERT.
# DDL is co-located with the SELECT-list it must match, so schema-drift
# between INSERT shape and table definition is caught at test time
# (test_ddl_select_column_parity) rather than at runtime.
RECIPES_STABLE_PREFIX = "pipeline-recipe-engine/output/recipes/"

# Recipes-table schema. ORDER MUST MATCH the SELECT in build_recipe_query
# exactly. Types are derived from the source-table schemas defined in
# qgi-infra/modules/storage/main.tf (patterns / events / countries), plus
# the explicit CASTs in the SELECT body. See
# test_ddl_select_column_parity for the regression guard that catches
# any drift between this list and the SELECT.
#
# Partition column `country_a_id` (smallint) is NOT in this list — it
# lives in the partitioned-by clause of the DDL.
RECIPES_COLUMNS = (
    ("recipe_id", "string"),  # concat(...) -> string
    ("event_category", "string"),  # events.category_normalized
    ("pattern_id", "string"),  # patterns.pattern_id
    ("country_b_id", "smallint"),  # patterns.country_b_id
    ("country_a_name", "string"),  # countries.name_1
    ("country_b_name", "string"),  # countries.name_1
    ("start_year_a", "smallint"),  # patterns.start_year_a
    ("start_year_b", "smallint"),  # patterns.start_year_b
    ("length", "smallint"),  # patterns.length
    ("avg_correlation", "double"),  # patterns.avg_correlation
    ("end_year_a", "smallint"),  # cast(... as smallint)
    ("end_year_b", "smallint"),  # cast(... as smallint)
    ("event_window", "smallint"),  # cast(... as smallint)
    ("event_year_a", "smallint"),  # events.year
    ("event_year_b", "smallint"),  # events.year
    ("event_title_a", "string"),  # events.title
    ("event_title_b", "string"),  # events.title
    ("indicator_count", "bigint"),  # patterns.indicator_count
    ("pattern_power_score", "double"),  # patterns.pattern_power_score
    ("instance_count", "bigint"),  # cast(count(*) as bigint)
    ("pattern_tier", "string"),  # _shared/pattern_tier
    ("median_lead_time_b", "smallint"),  # cast(... as smallint)
    ("min_lead_time_b", "smallint"),  # cast(... as smallint)
    ("max_lead_time_b", "smallint"),  # cast(... as smallint)
    ("median_lead_time_a", "smallint"),  # cast(... as smallint)
    ("pps", "double"),  # cast(... as double)
    ("contains_predicted", "boolean"),  # patterns.contains_predicted
)


def build_external_table_ddl(s3_bucket):
    """Build the CREATE EXTERNAL TABLE DDL for `qgi_data.recipes`.

    Run by the new SF state `5b.3a Create External Table` (between
    `5b.1 Drop Recipes Table` and `5b.3 List Formatter`'s downstream
    seed INSERT). Uses IF NOT EXISTS so re-runs after a partial-success
    are idempotent — the 5b.1 DROP cleared the table, the new DDL is the
    only writer in this scope. Pinned LOCATION at the stable prefix
    avoids the query_results/tables/<uuid>/ 1-day-expiry trap that
    caused #622.

    Parameters
    ----------
    s3_bucket : str
        The data-lake bucket (caller-supplied so this stays env-agnostic
        across staging / qa / prod accounts).
    """
    col_defs = ",\n      ".join(f"{name} {ctype}" for name, ctype in RECIPES_COLUMNS)
    return f"""
    CREATE EXTERNAL TABLE IF NOT EXISTS {ATHENA_DB}.recipes (
      {col_defs}
    )
    PARTITIONED BY (country_a_id smallint)
    STORED AS PARQUET
    LOCATION 's3://{s3_bucket}/{RECIPES_STABLE_PREFIX}'
    TBLPROPERTIES (
      'parquet.compress' = 'SNAPPY',
      'classification' = 'parquet',
      'EXTERNAL' = 'TRUE'
    )
    """.strip()


# Safety guard: a seed chunk that ends up > this row-count threshold means
# the smart-chunking math has degraded and we'd be exposing the INSERT to
# the 30-min Athena DML wall risk on a country at Tier-3+ size (India /
# China territory).
#
# Calibration: 2026-04-29 production observation captured a 263M reported-
# count chunk completing in ~76s wall-clock (linear extrapolation: 1M ≈
# 0.3s, 5M ≈ 1.5s, 10M ≈ 3s — all well below the 30-min DML wall).
# So 5M is comfortably below the actual scale ceiling but above the
# realistic seed size of a properly-chunked Tier-3 country (with 71×12 =
# 852 shards, even a 10M-row country averages 12k rows per shard; the
# smallest shard becomes the seed). Triggers only on a pathological
# smart-chunking regression where the seed picks up an unsplit big
# slice. Fails fast rather than silently OOM-ing 30 minutes later.
SEED_CHUNK_PATTERN_COUNT_GUARD = 5_000_000
