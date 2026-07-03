"""
Phase 5b step 6: Recipe Engine finalize (#162 Layer 2).

Runs AFTER the Step Function's 5b.5 Map state has populated every
partition of qgi_data.recipes via per-country INSERTs (and the seed
country via the 5b.4 CTAS).

Responsibilities (all post-write, bounded wall time):

1. Count recipes + category breakdown (observability)
2. Create `recipes_normalized` view — the #158 follow-up that recomputes
   `pps` using the GLOBAL max(instance_count) + max(indicator_count)
   across ALL country partitions. Without this, the per-partition pps
   written by the Map state's INSERTs would not be comparable across
   countries. See #158 follow-up commit c856b67 for the original analysis.
3. Create `recipe_convergence` view (#133) — reads from recipes_normalized
   so `predictor_best_pps` is a true global max, not per-partition.
4. Pre-compute dashboard JSONs (#146):
     - ranking.json        — top 1000 patterns by pattern_power_score
     - early-warning.json  — B-leads-A patterns with end year ≥ (now-2)
     - recipes-top50.json  — diversity-capped top 50 recipes via convergence

Skips convergence + dashboard JSON steps on backtesting runs
(`cutoff_year` set) — only the canonical run should publish dashboards.

All queries here are either:
  - Bounded aggregates on the finished recipes table (1-2 GB scans, sub-min)
  - View CREATE OR REPLACE (instant, metadata only)
  - Athena SELECT for small result sets feeding JSON generation

Total wall time budget: ~2-3 min. Well under 900s.
"""

import os
import json
import logging
import time
from datetime import datetime, timezone

import boto3

# #375 — country-risks.json auto-generation at pipeline end
from country_risks import write_country_risks_json

# #558: pattern_tier S/M/L/XL bucketing — single source of truth at
# lambdas/_shared/pattern_tier.py. The deploy workflow copies _shared/
# into each Lambda's bundle before zipping.
from _shared.pattern_tier import pattern_tier_case_sql

logger = logging.getLogger()
logger.setLevel(logging.INFO)

S3_BUCKET = os.environ.get("S3_BUCKET")
ATHENA_DB = os.environ.get("ATHENA_DATABASE", "qgi_data")
ATHENA_WG = os.environ.get("ATHENA_WORKGROUP", "QGI-Lambda-Workgroup")
DASHBOARD_PREFIX = "dashboard"
RANKING_LIMIT = 1000

RECIPES_DEDUPED_VIEW_NAME = "recipes_deduped"
RECIPES_NORMALIZED_VIEW_NAME = "recipes_normalized"
CONVERGENCE_VIEW_NAME = "recipe_convergence"
# #462 Fork B: Phase 5b.6.5 Recipe Aggregation Level-4 table.
RECIPES_AGGREGATED_TABLE_NAME = "recipes_aggregated"
RECIPES_AGGREGATED_S3_PREFIX = "pipeline-recipe-aggregator/output/data/"
RECIPES_AGGREGATED_SCHEMA_VERSION = 1
PIPELINE_VERSION = os.environ.get("PIPELINE_VERSION", "V2.0-dev")

# #495: pattern_indicator_lookup — thin projection (pattern_id, indicator_numeric_ids)
# ~50 MB vs 64 GB for the full patterns table. Used as the JOIN target in
# write_recipes_aggregated_table() instead of patterns directly.
PATTERN_INDICATOR_LOOKUP_TABLE_NAME = "pattern_indicator_lookup"
PATTERN_INDICATOR_LOOKUP_S3_PREFIX = "pattern-indicator-lookup/parquet/"

# #497: transient temp-table S3 prefix for CTAS-once-then-SELECT pattern.
# Each run gets its own isolated prefix; try/finally cleans up on success or error.
RECIPES_TEMP_TABLE_S3_PREFIX = "pipeline-recipe-aggregator/tmp/"

# #463 Fork B: Phase 5b.6.6 Country-vs-Recipe Scoring.
COUNTRY_RECIPE_SCORES_TABLE_NAME = "country_recipe_scores"
COUNTRY_RECIPE_SCORES_S3_PREFIX = "pipeline-recipe-scorer/output/data/"
INDICATOR_MAP_S3_KEY = "pipeline-A-indicator-extractor/input/indicator_map.csv"
# #591 Option D — Allow-list of catalog-curated indicator numeric_ids.
# Read on cold start; injected into write_recipes_aggregated_table()'s
# indicator_unnest CTE as a WHERE clause to keep the recipes_aggregated
# fingerprint restricted to curated indicators only.
INDICATOR_ALLOW_LIST_S3_KEY = "pipeline-A-indicator-extractor/input/indicator-allow-list.json"
# Coverage threshold below which we suppress the score per Sebastien's
# partial-coverage tolerance (Decision-1 caveat). Refine post-eval (#463 Part C).
SCORER_MIN_COVERAGE = 0.30


# ---------------------------------------------------------------------------
# A3 Cascade: M1 + M2 + M3 methodology fixes (Ihsa I1 vote 2026-05-02)
# ---------------------------------------------------------------------------
# - M1: corr-weighted MEDIAN canonical_length (was unweighted approx_percentile)
# - M2: ≥0.75 SCDI hard cut (founder picked, gentler than 0.90 alternative)
# - M3: corr-weighted FINGERPRINT (TF-IDF uses sum of |avg_correlation| for
#       term frequency; Wilson CI keeps unweighted recipe counts so the
#       binomial-CI semantic stays valid)
#
# Implementation reads `avg_correlation` from recipes_deduped (per-recipe).
# Trino approx_percentile(value, weight, percentage) supports the weighted form.
# The threshold is env-overridable for backtest sweeps; default matches the
# Ihsa I1 lock.
#
# IMPORTANT for future maintainers (per strict review 2026-05-03):
# Phase 0b stationarity audit (#582) found that 64-92% of random country
# pairs on I(1) indicators correlate at ≥0.75 SPURIOUSLY (Granger-Newbold
# construction). The M2 cut alone does NOT protect against unit-root
# contamination. Detrending of I(1) indicators is implemented in the
# auditioner (#585 Phase C, qgi-ml). Pipeline-side detrending of I(1) at
# SCDI scan time is gated on Ihsa I5 (out of scope for this PR).
#
# M3 is unconditionally weighted in v1 (per Ihsa I1 lock). No ablation flag.
# The parallel-run validation gate compares OLD corpus vs NEW corpus, not
# weighted vs unweighted within the new corpus. If a future ablation backtest
# is needed, introduce a SQL branch then — don't pre-bake a dead env flag.
def _load_scdi_m2_threshold() -> float:
    raw = os.environ.get("SCDI_M2_THRESHOLD", "0.75")
    try:
        return float(raw)
    except ValueError as e:
        raise RuntimeError(
            f"SCDI_M2_THRESHOLD env var must be a parseable float, got {raw!r}. "
            f"This is the M2 hard-cut threshold per Ihsa I1 (default 0.75)."
        ) from e


SCDI_M2_THRESHOLD = _load_scdi_m2_threshold()

# ---------------------------------------------------------------------------
# #170: Country → region map for the convergence score view.
#
# Canonical source of truth: qgi-data/registries/country_regions.yaml
# (synced to S3 at indicator-freshness/country_regions.yaml).
#
# This Lambda reads the YAML from S3 at init time and caches it.
# Falls back to an embedded copy if S3 read fails (cold start, missing
# file, permissions). The fallback is intentionally NOT maintained — it
# exists only as a safety net. If you update regions, update the YAML
# in qgi-data, sync to S3, and redeploy.
# ---------------------------------------------------------------------------
REGIONS_S3_KEY = os.environ.get("REGIONS_KEY", "indicator-freshness/country_regions.yaml")


def _load_country_regions():
    """Load country regions from S3 YAML, fall back to hardcoded."""
    try:
        obj = boto3.client("s3").get_object(Bucket=S3_BUCKET, Key=REGIONS_S3_KEY)
        raw = obj["Body"].read().decode("utf-8")
        # Parse simple YAML without pyyaml: each region is "REG:" followed by "  - XX" lines
        regions = {}
        current_region = None
        for line in raw.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("version") or not stripped:
                continue
            if not line.startswith(" ") and stripped.endswith(":"):
                current_region = stripped[:-1]
                regions[current_region] = set()
            elif current_region and stripped.startswith("- "):
                regions[current_region].add(stripped[2:].strip())
        if regions:
            logger.info(f"Loaded {sum(len(v) for v in regions.values())} country codes from S3")
            return regions
    except Exception:
        logger.warning("Failed to load country_regions from S3, using fallback", exc_info=True)

    # Hardcoded fallback (last synced 2026-04-10, 251 codes, 6 regions)
    return {
        "AFR": {
            "AO",
            "BF",
            "BI",
            "BJ",
            "BW",
            "CD",
            "CF",
            "CG",
            "CI",
            "CM",
            "CV",
            "DJ",
            "ER",
            "ET",
            "GA",
            "GH",
            "GM",
            "GN",
            "GQ",
            "GW",
            "KE",
            "KM",
            "LR",
            "LS",
            "MG",
            "ML",
            "MR",
            "MU",
            "MW",
            "MZ",
            "NA",
            "NE",
            "NG",
            "RE",
            "RW",
            "SC",
            "SH",
            "SL",
            "SN",
            "SO",
            "SS",
            "ST",
            "SZ",
            "TD",
            "TG",
            "TZ",
            "UG",
            "YT",
            "ZA",
            "ZM",
            "ZW",
        },
        "MEA": {
            "AE",
            "BH",
            "DZ",
            "EG",
            "EH",
            "IL",
            "IQ",
            "IR",
            "JO",
            "KW",
            "LB",
            "LY",
            "MA",
            "OM",
            "PS",
            "QA",
            "SA",
            "SD",
            "SY",
            "TN",
            "TR",
            "YE",
        },
        "EUR": {
            "AD",
            "AL",
            "AT",
            "AX",
            "BA",
            "BE",
            "BG",
            "BY",
            "CH",
            "CY",
            "CZ",
            "DE",
            "DK",
            "EE",
            "ES",
            "FI",
            "FO",
            "FR",
            "GB",
            "GG",
            "GI",
            "GL",
            "GR",
            "HR",
            "HU",
            "IE",
            "IM",
            "IS",
            "IT",
            "JE",
            "LI",
            "LT",
            "LU",
            "LV",
            "MC",
            "MD",
            "ME",
            "MK",
            "MT",
            "NL",
            "NO",
            "PL",
            "PT",
            "RO",
            "RS",
            "RU",
            "SE",
            "SI",
            "SJ",
            "SK",
            "SM",
            "UA",
            "VA",
            "XK",
        },
        "ASI": {
            "AF",
            "AM",
            "AZ",
            "BD",
            "BN",
            "BT",
            "CC",
            "CN",
            "CX",
            "GE",
            "HK",
            "ID",
            "IN",
            "IO",
            "JP",
            "KG",
            "KH",
            "KP",
            "KR",
            "KZ",
            "LA",
            "LK",
            "MM",
            "MN",
            "MO",
            "MV",
            "MY",
            "NP",
            "PH",
            "PK",
            "SG",
            "TH",
            "TJ",
            "TL",
            "TM",
            "TW",
            "UZ",
            "VN",
        },
        "AMR": {
            "AG",
            "AI",
            "AN",
            "AR",
            "AW",
            "BB",
            "BL",
            "BM",
            "BO",
            "BQ",
            "BR",
            "BS",
            "BZ",
            "CA",
            "CL",
            "CO",
            "CR",
            "CU",
            "CW",
            "DM",
            "DO",
            "EC",
            "FK",
            "GD",
            "GF",
            "GP",
            "GS",
            "GT",
            "GY",
            "HN",
            "HT",
            "JM",
            "KN",
            "KY",
            "LC",
            "MF",
            "MQ",
            "MS",
            "MX",
            "NI",
            "PA",
            "PE",
            "PM",
            "PR",
            "PY",
            "SR",
            "SV",
            "SX",
            "TC",
            "TT",
            "US",
            "UY",
            "VC",
            "VE",
            "VG",
            "VI",
        },
        "OCE": {
            "AQ",
            "AS",
            "AU",
            "BV",
            "CK",
            "FJ",
            "FM",
            "GU",
            "HM",
            "KI",
            "MH",
            "MP",
            "NC",
            "NF",
            "NR",
            "NU",
            "NZ",
            "PF",
            "PG",
            "PN",
            "PW",
            "SB",
            "TF",
            "TK",
            "TO",
            "TV",
            "UM",
            "VU",
            "WF",
            "WS",
        },
    }


COUNTRY_REGIONS = _load_country_regions()


athena = boto3.client("athena")
s3 = boto3.client("s3")
cloudwatch = boto3.client("cloudwatch")  # #381 drift + #409 caught-exception metrics


def _emit_caught_exception(context_key):
    """Emit CloudWatch metric for a log-and-continue exception (#409).

    Some catch blocks intentionally log-and-continue for non-fatal steps
    (e.g. view creation, dashboard sub-writes). Those exceptions still
    represent operational signal that deserves an alarm when they spike.
    This helper ensures the occurrence is counted in CloudWatch even
    when the handler chooses not to re-raise.

    Discovered after 2026-04-22 finalize-Lambda silent-failure incident:
    country-risks.json silently stopped regenerating for 2 days because
    a signature-mismatch exception was caught, logged, and the handler
    still returned 200. See #373 (audit) and #409 (observability).
    """
    try:
        cloudwatch.put_metric_data(
            Namespace="QGI/Pipeline",
            MetricData=[
                {
                    "MetricName": "CaughtExceptionCount",
                    "Value": 1.0,
                    "Unit": "Count",
                    "Dimensions": [
                        {"Name": "Lambda", "Value": os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "unknown")},
                        {"Name": "Location", "Value": context_key},
                    ],
                }
            ],
        )
    except Exception:  # noqa: BLE001 — last-resort; don't shadow original
        logger.warning(
            "emit_caught_exception: metric put failed (swallowed) context=%s",
            context_key,
        )


def lambda_handler(event, context):
    run_id = event.get("run_id", "manual")
    cutoff_year = event.get("cutoff_year")
    partitions_total = event.get("partitions_total", "unknown")

    logger.info(
        f"Recipe engine finalize starting. run_id={run_id}, "
        f"cutoff_year={cutoff_year}, partitions_total={partitions_total}"
    )

    # Step 1: total count + category breakdown (small scans)
    count_id = run_query(f"SELECT count(*) FROM {ATHENA_DB}.recipes")
    count_result = athena.get_query_results(QueryExecutionId=count_id)
    total_recipes = int(count_result["ResultSet"]["Rows"][1]["Data"][0]["VarCharValue"])
    logger.info(f"recipes row count: {total_recipes:,}")

    cat_id = run_query(
        f"SELECT event_category, count(*) AS cnt FROM {ATHENA_DB}.recipes "
        f"GROUP BY event_category ORDER BY cnt DESC LIMIT 20"
    )
    cat_result = athena.get_query_results(QueryExecutionId=cat_id)
    top_categories = [
        f"{r['Data'][0]['VarCharValue']}: {r['Data'][1]['VarCharValue']}" for r in cat_result["ResultSet"]["Rows"][1:6]
    ]
    logger.info(f"Top categories: {top_categories}")

    # Step 2a: recipes_deduped view (#458) — bullet-6 longest-pattern
    # collapse. Must precede recipes_normalized + recipes_aggregated since
    # both read from this view.
    create_recipes_deduped_view()

    # Step 2b: recipes_normalized view (#158 follow-up)
    create_recipes_normalized_view()

    # #496 idempotency: per-table force flags from event payload.
    # Default false → idempotency guard kicks in (skip if recently rebuilt).
    # Pass true to override (e.g. for explicit re-bake during debugging).
    force_aggregated = bool(event.get("force_rebake_aggregated", False))
    force_scores = bool(event.get("force_rebake_scores", False))
    force_lookup = bool(event.get("force_rebake_lookup", False))

    # Step 2c-pre: build pattern_indicator_lookup (#495) — must run before
    # write_recipes_aggregated_table which JOINs to this table instead of
    # the full patterns table (64 GB → ~50 MB scan reduction).
    lookup_status = "skipped"
    if cutoff_year is None:
        try:
            build_pattern_indicator_lookup_table(force=force_lookup)
            lookup_status = "ok"
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"Failed to build pattern_indicator_lookup: {exc}")
            lookup_status = f"error: {exc}"
            _emit_caught_exception("build_pattern_indicator_lookup_table")

    # Step 2c: recipes_aggregated table (#462 Fork B Phase 5b.6.5) — Level-4
    # Recipe object, one row per L3 event_category. Runs after the deduped
    # view and lookup table exist; independent of recipes_normalized + convergence.
    aggregated_status = "skipped"
    if cutoff_year is None:
        try:
            write_recipes_aggregated_table(force=force_aggregated)
            aggregated_status = "ok"
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"Failed to write recipes_aggregated: {exc}")
            aggregated_status = f"error: {exc}"
            _emit_caught_exception("write_recipes_aggregated_table")

    # Step 2d: country_recipe_scores table (#463 Fork B Phase 5b.6.6 v0.1) —
    # one row per (country, recipe). Depends on recipes_aggregated being
    # populated in Step 2c. Skipped on backtest cutoffs (frontend-only
    # consumer; backtest runs don't publish to the dashboard).
    scores_status = "skipped"
    if cutoff_year is None and aggregated_status == "ok":
        try:
            write_country_recipe_scores(force=force_scores)
            scores_status = "ok"
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"Failed to write country_recipe_scores: {exc}")
            scores_status = f"error: {exc}"
            _emit_caught_exception("write_country_recipe_scores")
    elif cutoff_year is None and aggregated_status != "ok":
        # Skip explicitly if upstream failed — the scorer reads from
        # recipes_aggregated, no point trying.
        scores_status = f"skipped: aggregated upstream {aggregated_status}"

    # Step 3: convergence view (#133) — reads from recipes_normalized
    convergence_status = "skipped"
    if cutoff_year is None:
        try:
            create_convergence_view()
            convergence_status = "ok"
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"Failed to create convergence view: {exc}")
            convergence_status = f"error: {exc}"
            _emit_caught_exception("create_convergence_view")

    # Step 4: dashboard JSONs (#146)
    dashboard_results = {}
    if cutoff_year is None:
        try:
            dashboard_results = write_dashboard_jsons()
            logger.info(f"Dashboard JSONs written: {dashboard_results}")
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"Failed to write dashboard JSONs: {exc}")
            dashboard_results = {"error": str(exc)}
            _emit_caught_exception("write_dashboard_jsons")

    return {
        "statusCode": 200,
        "recipes_count": total_recipes,
        "top_categories": top_categories,
        "pattern_indicator_lookup": lookup_status,
        "recipes_aggregated": aggregated_status,
        "country_recipe_scores": scores_status,
        "convergence_view": convergence_status,
        "dashboard": dashboard_results,
        "partitions_total": partitions_total,
    }


# ---------------------------------------------------------------------------
# recipes_deduped view — bullet-6 nested-length collapse (#458)
# ---------------------------------------------------------------------------


def create_recipes_deduped_view():
    """Collapse same-event nested-length Pattern instances to the longest.

    Today's `qgi_data.recipes` keys recipe_id by
    (country_a, country_b, start_year_a, length, event_category). When a
    pair-event has multiple patterns at different lengths that all end at
    the same event (Saudi-Egypt-2011-len5-civil_war + 2010-len6 + 2009-len7
    all terminating at the same Saudi 2015 event), each becomes a separate
    recipe row. The founder's bullet 6 (Majles audit 2026-04-25) says take
    the longest. The recipe-engine doesn't, so today's instance_count and
    recipe_count are inflated 3-5x per pair-event.

    This view collapses to the LONGEST per
    (country_a, country_b, event_year_a, event_year_b, event_category).
    Tiebreak by pps so the highest-quality row wins when lengths match.

    Downstream consumers (recipes_normalized + country_risks salience SQL +
    standalone bakers) read from this view instead of recipes directly.

    Superseded by V2.0 #462 (Recipe Aggregation Level-4 table) — when that
    lands, retire this view. Until then, this is the cheapest fix for the
    inflation bug that doesn't require a recipe-engine rewrite.

    Outer SELECT enumerates the 27 columns of qgi_data.recipes (26 regular
    + country_a_id partition key) instead of `SELECT * EXCEPT(rn)`. Athena's
    Trino dialect does not support `EXCEPT (col)` despite older comments
    claiming so — confirmed against engine v3 in QGI-Lambda-Workgroup on
    2026-04-26 with InvalidRequestException ('mismatched input rn').
    """
    sql = f"""
    CREATE OR REPLACE VIEW {ATHENA_DB}.{RECIPES_DEDUPED_VIEW_NAME} AS
    WITH ranked AS (
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY country_a_id, country_b_id,
                                event_year_a, event_year_b, event_category
                   ORDER BY length DESC, pattern_power_score DESC
               ) AS rn
        FROM {ATHENA_DB}.recipes
    )
    SELECT recipe_id, event_category, pattern_id, country_a_id, country_b_id,
           country_a_name, country_b_name, start_year_a, start_year_b, length,
           avg_correlation, end_year_a, end_year_b, event_window,
           event_year_a, event_year_b, event_title_a, event_title_b,
           indicator_count, pattern_power_score, instance_count, pattern_tier,
           median_lead_time_b, min_lead_time_b, max_lead_time_b,
           median_lead_time_a, pps,
           -- #461 D7 plumbing: legacy recipes (pre-#461 pipeline run) have no
           -- contains_predicted column; default false so downstream views and
           -- the recipes_aggregated CTAS can reference the column without
           -- erroring on schema-resolution. Once the recipe-engine writer is
           -- re-run with #461 plumbing, recipes will gain the column and this
           -- view should be updated to pass it through (tracked in #475).
           CAST(false AS boolean) AS contains_predicted
    FROM ranked
    WHERE rn = 1
    """
    logger.info("Creating recipes_deduped view (bullet-6 longest-pattern collapse)")
    run_query(sql)
    logger.info(f"View {ATHENA_DB}.{RECIPES_DEDUPED_VIEW_NAME} created")


# ---------------------------------------------------------------------------
# recipes_normalized view — global pps normalization (#158 follow-up)
# ---------------------------------------------------------------------------


def create_recipes_normalized_view():
    """Overlay view that recomputes pps using GLOBAL max across all partitions.

    The Map state's per-country INSERTs each compute their own local
    `max(instance_count)` and `max(indicator_count)` inside the per-country
    `global_stats` CTE — so the physically-stored `pps` column is per-
    partition wrong. This view re-reads the finished recipes table, takes
    the TRUE global max via CROSS JOIN, and rewrites `pps` on the fly.

    #458: now reads from `recipes_deduped` (bullet-6 collapse) instead of
    raw `recipes`, so global max is taken over the deduped row set rather
    than the inflated set. Downstream consumers (convergence view + top50
    dashboard query) inherit the dedup automatically through this view.

    Requires Athena engine v3 for `SELECT * EXCEPT`. Confirmed live in
    QGI-Lambda-Workgroup.
    """
    sql = f"""
    CREATE OR REPLACE VIEW {ATHENA_DB}.{RECIPES_NORMALIZED_VIEW_NAME} AS
    SELECT
        r.recipe_id, r.event_category, r.pattern_id, r.country_b_id,
        r.country_a_name, r.country_b_name, r.start_year_a, r.start_year_b,
        r.length, r.avg_correlation, r.end_year_a, r.end_year_b,
        r.event_window, r.event_year_a, r.event_year_b,
        r.event_title_a, r.event_title_b, r.indicator_count,
        r.pattern_power_score, r.instance_count, r.pattern_tier,
        r.median_lead_time_b, r.min_lead_time_b, r.max_lead_time_b,
        r.median_lead_time_a, r.country_a_id,
        -- #461: D7 plumbing carries through from recipes_deduped → here →
        -- convergence view (which reads from this view) → dashboard JSONs.
        r.contains_predicted,
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
        ) AS pps
    FROM {ATHENA_DB}.{RECIPES_DEDUPED_VIEW_NAME} r
    CROSS JOIN (
        SELECT
            cast(max(instance_count) as double)  AS max_inst,
            cast(max(indicator_count) as double) AS max_ind
        FROM {ATHENA_DB}.{RECIPES_DEDUPED_VIEW_NAME}
    ) g
    """
    logger.info("Creating recipes_normalized view (global pps over deduped set)")
    run_query(sql)
    logger.info(f"View {ATHENA_DB}.{RECIPES_NORMALIZED_VIEW_NAME} created")


# ---------------------------------------------------------------------------
# pattern_indicator_lookup table — #495 cost-reduction
# ---------------------------------------------------------------------------


def build_pattern_indicator_lookup_table(force: bool = False):
    """#495: materialise a thin (pattern_id, indicator_numeric_ids) lookup table.

    Purpose: replace the 64 GB full-patterns scan in write_recipes_aggregated_table
    with a ~50 MB read. The lookup contains only the two columns the CTAS
    actually needs from patterns, so Athena's projection pushdown reduces the
    scan by ~90%.

    Strategy (mirrors write_recipes_aggregated_table / write_country_recipe_scores):
      1. Idempotency guard — skip if rebuilt within 60 min (same window as
         recipes_aggregated; the patterns table only changes on pipeline re-bake).
      2. Clear the S3 prefix so re-runs are idempotent.
      3. INSERT INTO SELECT pattern_id, indicator_numeric_ids FROM patterns.

    The Glue table is Terraform-managed (qgi-infra/modules/storage/main.tf
    aws_glue_catalog_table.pattern_indicator_lookup). Call this BEFORE
    write_recipes_aggregated_table so the lookup is populated when the CTAS runs.

    Trigger: runs automatically as Step 2c-pre in lambda_handler on every
    non-backtest invocation. To rebuild independently (e.g. after patterns
    is re-baked), pass event.force_rebake_lookup=true.
    """
    # 0. #496-style idempotency guard. We reuse the same timestamp machinery
    # but patterns doesn't have a last_recomputed_at column. Instead we proxy
    # via a COUNT(*) check: if the table is non-empty AND force=False, skip.
    # Rationale: the lookup is rebuilt from patterns which only changes on a
    # full pipeline re-bake (rare). The 60-min window is a reasonable guard
    # against repeated finalize invocations within the same run.
    if _check_idempotency_skip_rowcount(PATTERN_INDICATOR_LOOKUP_TABLE_NAME, force=force):
        return

    # 1. Clear existing data so re-runs are idempotent.
    logger.info(f"[#495] Clearing s3://{S3_BUCKET}/{PATTERN_INDICATOR_LOOKUP_S3_PREFIX}")
    paginator = s3.get_paginator("list_objects_v2")
    keys_to_delete = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=PATTERN_INDICATOR_LOOKUP_S3_PREFIX):
        for obj in page.get("Contents", []):
            keys_to_delete.append({"Key": obj["Key"]})
            if len(keys_to_delete) >= 1000:
                s3.delete_objects(Bucket=S3_BUCKET, Delete={"Objects": keys_to_delete})
                keys_to_delete = []
    if keys_to_delete:
        s3.delete_objects(Bucket=S3_BUCKET, Delete={"Objects": keys_to_delete})

    # 2. INSERT INTO — project only the two columns we need. Athena's
    # projection pushdown ensures only those two columns are decoded from
    # the Parquet row groups in patterns, but the scan size is still driven
    # by the full column set unless we materialise the projection. Hence
    # this dedicated table.
    sql = f"""
    INSERT INTO {ATHENA_DB}.{PATTERN_INDICATOR_LOOKUP_TABLE_NAME}
    SELECT
        pattern_id,
        indicator_numeric_ids
    FROM {ATHENA_DB}.patterns
    WHERE indicator_numeric_ids IS NOT NULL
    """
    logger.info(
        f"[#495] Building {ATHENA_DB}.{PATTERN_INDICATOR_LOOKUP_TABLE_NAME} from patterns (projects 2 of ~12 columns)"
    )
    run_query(sql)
    logger.info(f"[#495] {ATHENA_DB}.{PATTERN_INDICATOR_LOOKUP_TABLE_NAME} populated")


def _check_idempotency_skip_rowcount(table_name: str, force: bool) -> bool:
    """Idempotency guard for tables without a timestamp column.

    Returns True (skip) when:
      - force=False AND the table has ≥ 1 row (non-empty → was built this run
        or a recent run).

    Rationale for pattern_indicator_lookup: it's rebuilt from patterns which
    is only regenerated on a full pipeline re-bake. An empty table always
    triggers a build; a non-empty table is assumed fresh unless force=True.

    Falls back to False (proceed) on any Athena error — same graceful
    degradation as _check_idempotency_skip.
    """
    if force:
        logger.info(f"[idempotency-rowcount] {table_name}: force=True, proceeding")
        return False
    try:
        sql = f"SELECT 1 FROM {ATHENA_DB}.{table_name} LIMIT 1"
        qid = run_query(sql)
        result = athena.get_query_results(QueryExecutionId=qid)
        rows = result["ResultSet"]["Rows"]
        if len(rows) > 1:
            logger.info(
                f"[idempotency-rowcount] {table_name}: non-empty (has data), SKIPPING. "
                f"Pass event.force_rebake_lookup=true to override."
            )
            return True
        logger.info(f"[idempotency-rowcount] {table_name}: empty, proceeding with build")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[idempotency-rowcount] {table_name} check failed: {exc}; proceeding without skip")
    return False


# ---------------------------------------------------------------------------
# recipes_aggregated table — Fork B Phase 5b.6.5 (#462)
# ---------------------------------------------------------------------------


def _check_idempotency_skip(
    table_name: str, force: bool, timestamp_col: str = "last_recomputed_at", window_minutes: int = 60
) -> bool:
    """#496 idempotency guard. Returns True if we should skip the heavy CTAS.

    Skips when the target table's max(timestamp_col) is younger than
    `window_minutes`, unless `force` is True. Prevents accidental re-runs
    during debug iteration from costing $0.95/scan apiece (#496 origin:
    April 26 2026 cost spike — 8 sequential invocations at $7.21 total).

    timestamp_col defaults to "last_recomputed_at" (recipes_aggregated);
    pass "last_computed_at" for country_recipe_scores.
    """
    if force:
        logger.info(f"[idempotency] {table_name}: force=True, proceeding")
        return False
    try:
        # Use start_query_execution + get_query_results directly (run_query
        # raises on FAILED, but here we want to gracefully handle the
        # "table empty" case).
        sql = f"SELECT cast(max({timestamp_col}) as varchar) AS recent FROM {ATHENA_DB}.{table_name}"
        check_id = run_query(sql)
        result = athena.get_query_results(QueryExecutionId=check_id)
        rows = result["ResultSet"]["Rows"]
        if len(rows) <= 1:
            return False
        recent_str = rows[1]["Data"][0].get("VarCharValue")
        if not recent_str:
            return False
        recent_ts = datetime.fromisoformat(recent_str.replace(" ", "T"))
        if recent_ts.tzinfo is None:
            recent_ts = recent_ts.replace(tzinfo=timezone.utc)
        age_min = (datetime.now(timezone.utc) - recent_ts).total_seconds() / 60.0
        if age_min < window_minutes:
            logger.info(
                f"[idempotency] {table_name}: last_recomputed_at is {age_min:.1f}min ago "
                f"(< {window_minutes}min window); SKIPPING. "
                f"Pass event.force_rebake_aggregated/scores=true to override."
            )
            return True
        logger.info(f"[idempotency] {table_name}: last write {age_min:.1f}min ago, proceeding")
    except Exception as exc:  # noqa: BLE001
        # Any failure (table missing, query error, etc.) → don't skip; let
        # the caller's normal CTAS path run and surface the real issue.
        logger.warning(f"[idempotency] {table_name} check failed: {exc}; proceeding without skip")
    return False


def write_recipes_aggregated_table(force: bool = False):
    """Phase 5b.6.5: produce qgi_data.recipes_aggregated (Level-4 Recipe object).

    One row per L3 event_category (~71 rows total). The
    Recipe-as-aggregated-fingerprint phase the audit found missing.

    Strategy: the Glue table is Terraform-owned (qgi-infra/modules/storage),
    so we can't use Athena CTAS (it would conflict on the table definition).
    Instead: clear the data prefix in S3, then INSERT INTO. Idempotent
    because the prefix wipe runs every cycle.

    Schema (per Majles consult Decision 3, extended from 3 to 11 properties):
      - event_category, canonical_length, length_distribution
      - indicator_fingerprint (top-15 by TF-IDF + Wilson 95% CI)
      - coverage_bias_diagnostic (n_pairs + OECD share + regional concentration)
      - total_instances, n_distinct_country_pairs
      - last_recomputed_at, pipeline_version, schema_version
      - contains_predicted (#461 D7 plumbing inherited)

    REFINEMENTS DEFERRED (TODO markers in the SQL):
      - avg_corr_magnitude per indicator: requires join back to scdis (~12B
        rows); emits 0.0 placeholder for now. Scorer falls back to
        tfidf_score as the Pearson weight (commit 656e143). Tracked under
        a follow-up to #519.
      - coverage_bias_diagnostic.regional_concentration: emits empty array.
        Requires a 200-row alpha_3 → UN-region inline VALUES. The frontend
        gates rendering on `length > 0` so this is hidden, not "0" — no
        user-visible regression. Tracked under a follow-up to #519.

    REFINEMENTS LIVE:
      - coverage_bias_diagnostic.oecd_share (#519): now computed from
        recipe pairs JOIN qgi_data.countries → 38-member OECD VALUES
        clause. Replaces the previous 0.0 placeholder which was rendered
        on /signals/{country}/{slug} as "0%".

    Cost optimisations (#495 + #497):
      #495 — JOIN target switched from qgi_data.patterns (~64 GB) to
             qgi_data.pattern_indicator_lookup (~50 MB). The lookup is built
             by build_pattern_indicator_lookup_table() earlier in the same
             Lambda invocation. Saves ~90% of the patterns scan per run.
      #497 — CTAS-once-then-SELECT: the heavy JOIN (recipes_deduped ×
             pattern_indicator_lookup) is materialised into a transient Glue
             table ONCE via CREATE TABLE AS SELECT. All downstream aggregation
             CTEs read from that small temp table (estimated ~5-10 MB) instead
             of re-running the join for each CTE reference. Athena does NOT
             memoize CTEs; without this, the original 6-CTE chain re-executed
             the join 5-6 times. try/finally ensures the temp table + S3
             prefix are deleted on success or error.

    Combined expected scan per invocation: ~190 GB → ~10-15 GB.
    """
    import uuid

    # 0. #496 idempotency guard — short-circuit if table was just rebuilt.
    if _check_idempotency_skip(RECIPES_AGGREGATED_TABLE_NAME, force=force):
        return

    # 1. Clear existing output data so re-runs are idempotent.
    logger.info(f"Clearing s3://{S3_BUCKET}/{RECIPES_AGGREGATED_S3_PREFIX}")
    _s3_delete_prefix(RECIPES_AGGREGATED_S3_PREFIX)

    # 2. #497 — materialise the heavy join ONCE into a temp table.
    # Use a short UUID suffix to isolate concurrent runs.
    run_uid = uuid.uuid4().hex[:12]
    temp_table = f"tmp_rwp_{run_uid}"
    temp_s3_prefix = f"{RECIPES_TEMP_TABLE_S3_PREFIX}{temp_table}/"
    temp_s3_location = f"s3://{S3_BUCKET}/{temp_s3_prefix}"

    logger.info(
        f"[#497] Materialising temp table {ATHENA_DB}.{temp_table} "
        f"(recipes_deduped × pattern_indicator_lookup). "
        f"Data lands in workgroup default (query_results/) per #545."
    )
    # #545: removed `external_location` from the CTAS. The QGI-Lambda-Workgroup
    # has EnforceWorkGroupConfiguration=true with a centralized OutputLocation —
    # any per-query override (including CTAS external_location) is rejected with
    # "InvalidRequestException: ... submitted with an 'external_location' property
    # to an Athena Workgroup that enforces a centralized output location".
    # Pre-#545 this killed the whole recipes_aggregated population step silently.
    # Trade-off: temp-table Parquet now lands in query_results/ (workgroup default).
    # The DROP TABLE in `finally:` still removes the Glue catalog entry; orphaned
    # Parquet in query_results/ is cleaned by the bucket's lifecycle policy.
    # The _s3_delete_prefix(temp_s3_prefix) call in `finally:` is now dead
    # code (data lands in query_results/, not at temp_s3_prefix); retained
    # to avoid churn this PR. Cleanable in a follow-up if desired.
    ctas_sql = f"""
    CREATE TABLE {ATHENA_DB}.{temp_table}
    WITH (
        format = 'PARQUET',
        parquet_compression = 'SNAPPY'
    ) AS
    SELECT
        rd.event_category,
        rd.recipe_id,
        rd.country_a_id,
        rd.country_b_id,
        rd.length,
        -- A3 cascade M1+M3: avg_correlation projected for use as the weight
        -- in canonical_length weighted-median (M1) AND TF-IDF weighted term
        -- frequency (M3). Source: recipes_deduped per-recipe correlation.
        rd.avg_correlation,
        COALESCE(rd.contains_predicted, FALSE) AS contains_predicted,
        p.indicator_numeric_ids
    FROM {ATHENA_DB}.{RECIPES_DEDUPED_VIEW_NAME} rd
    INNER JOIN {ATHENA_DB}.{PATTERN_INDICATOR_LOOKUP_TABLE_NAME} p
        ON p.pattern_id = rd.pattern_id
    -- A3 cascade M2: hard cut on |avg_correlation| ≥ {SCDI_M2_THRESHOLD}
    -- (Ihsa I1 vote 2026-05-02; founder picked 0.75 over 0.90 alternative).
    -- Filtering after dedup so we keep the longest pattern per (country, event)
    -- but drop those whose correlation magnitude is too weak to be a reliable
    -- pattern. Threshold env-overridable for backtest sweeps.
    WHERE abs(rd.avg_correlation) >= {SCDI_M2_THRESHOLD}
    """
    try:
        run_query(ctas_sql)
        logger.info(f"[#497] Temp table {temp_table} materialised")

        # 3. INSERT INTO from the temp table. All aggregation CTEs below read
        # from temp_table (small) — no repeated full-scan of recipes_deduped
        # or pattern_indicator_lookup. Column order MUST match the
        # Terraform-owned Glue schema (main.tf recipes_aggregated).
        #
        # #591 Option D: bind the catalog allow-list IN-clause for the
        # indicator_unnest CTE. Loaded lazily so test runs without S3 mocks
        # don't trigger a real GET. Tuple of trusted ints — comma-join is
        # safe for SQL embedding (no quoting, no escapes).
        allow_list = _get_indicator_allow_list()
        allow_list_in_clause = ", ".join(str(i) for i in allow_list)

        insert_sql = f"""
        INSERT INTO {ATHENA_DB}.{RECIPES_AGGREGATED_TABLE_NAME}
        WITH
        -- Per-category point estimates. Single pass over the temp table.
        -- A3 cascade M1: canonical_length is the CORRELATION-WEIGHTED median
        -- of pattern lengths within the category (Ihsa I1 vote 2026-05-02).
        --
        -- Trino approx_percentile(value, weight, percentage) requires
        -- weight >= 1 (the function treats weight as a per-item count and
        -- raises INVALID_FUNCTION_ARGUMENT at runtime if any weight < 1).
        -- After the M2 filter abs(avg_correlation) >= 0.75 in the temp
        -- table, every weight is in [0.75, 1.0] — every row would crash.
        -- We multiply by 100.0 to lift weights into [75, 100]. Because
        -- approx_percentile uses weights as RELATIVE counts, scaling
        -- every weight by the same constant is mathematically a no-op:
        -- the weighted median is unchanged. The *100.0 is purely a
        -- runtime-constraint workaround, not a methodology change.
        --
        -- Headroom: the minimum safe multiplier at threshold T is
        -- ceil(1.0 / T) (at T=0.75 the minimum is 2; at T=0.10 it is
        -- 10). With multiplier=100 the M2 threshold can safely drop as
        -- low as 0.01 (=> 0.01 * 100 = 1) without violating weight>=1.
        -- If the threshold is ever lowered below 0.01, this multiplier
        -- MUST be raised in lockstep — otherwise the SQL silently
        -- crashes the moment any |corr| in the data falls below 0.01.
        --
        -- Caught by smoke test 2026-05-03 (qid 0d1be98a). The unit tests
        -- in tests/unit/pipeline-recipe-engine-finalize/ inspect SQL
        -- source text and could not have caught this — it is a Trino
        -- runtime constraint not visible from the SQL alone.
        --
        -- Correctness coupling (still holds): M1 weighted-median is
        -- valid only when M2 has fired. NULL avg_correlation is excluded
        -- by M2 (NULL >= 0.75 is unknown → row dropped). Future
        -- maintainers: do NOT remove the M2 filter without also adding
        -- `WHERE avg_correlation IS NOT NULL AND avg_correlation != 0`
        -- here.
        category_basics AS (
            SELECT
                event_category,
                cast(approx_percentile(
                    cast(length as double),
                    abs(cast(avg_correlation as double)) * 100.0,
                    0.5
                ) as smallint) AS canonical_length,
                cast(count(distinct recipe_id) as bigint) AS total_instances,
                cast(count(distinct cast(country_a_id as varchar) || '-' || cast(country_b_id as varchar)) as bigint) AS n_distinct_country_pairs,
                bool_or(contains_predicted) AS contains_predicted
            FROM {ATHENA_DB}.{temp_table}
            GROUP BY event_category
        ),
        -- Length histogram per category. Second pass (small table).
        length_dist_rows AS (
            SELECT event_category, length, cast(count(distinct recipe_id) as bigint) AS cnt
            FROM {ATHENA_DB}.{temp_table}
            GROUP BY event_category, length
        ),
        length_distributions AS (
            SELECT
                event_category,
                array_agg(
                    cast(row(cast(length as smallint), cnt)
                         as row(length smallint, count bigint))
                    ORDER BY length
                ) AS length_distribution
            FROM length_dist_rows
            GROUP BY event_category
        ),
        -- Per-indicator unnest for fingerprint. Third pass (small table).
        -- A3 cascade M3: project avg_correlation through the unnest so each
        -- (recipe × indicator) row carries the recipe's correlation magnitude
        -- as a weight for downstream TF-IDF.
        --
        -- #591 Option D: filter unnested indicator_ids to the catalog allow-
        -- list (loaded from indicator-allow-list.json at S3
        -- INDICATOR_ALLOW_LIST_S3_KEY; bound at SQL-build time as a comma-
        -- joined IN-list of trusted ints — no SQL-injection vector since
        -- the generator emits ints and the loader raises on non-int).
        indicator_unnest AS (
            SELECT event_category, recipe_id, indicator_id,
                   abs(cast(avg_correlation as double)) AS w
            FROM {ATHENA_DB}.{temp_table}
            CROSS JOIN UNNEST(indicator_numeric_ids) AS t(indicator_id)
            WHERE t.indicator_id IN ({allow_list_in_clause})
        ),
        -- A3 cascade M3: dual aggregations.
        -- (a) UNWEIGHTED count is preserved for Wilson 95% CI — the binomial
        --     CI semantic only works on integer trial counts; keeping it
        --     unweighted is the right call for downstream confidence display.
        -- (b) WEIGHTED sum drives TF-IDF — the correlation-weighted version
        --     of "term frequency" rewards indicators that appear in
        --     high-correlation recipes within the category.
        indicator_counts AS (
            SELECT
                event_category,
                indicator_id,
                count(distinct recipe_id) AS recipes_with_indicator,
                sum(w) AS recipes_with_indicator_weighted
            FROM indicator_unnest
            GROUP BY event_category, indicator_id
        ),
        recipes_per_category AS (
            SELECT event_category,
                   count(distinct recipe_id) AS n_recipes,
                   sum(abs(cast(avg_correlation as double))) AS n_recipes_weighted
            FROM {ATHENA_DB}.{temp_table}
            GROUP BY event_category
        ),
        total_recipe_count AS (
            SELECT count(distinct recipe_id) AS n_total,
                   sum(abs(cast(avg_correlation as double))) AS n_total_weighted
            FROM {ATHENA_DB}.{temp_table}
        ),
        -- Indicator metrics: frequency + TF-IDF + Wilson 95% CI on the proportion.
        -- Wilson formula: z=1.96, z²=3.8416. center=(p+z²/2n)/(1+z²/n);
        -- margin=z*sqrt(p(1-p)/n + z²/(4n²))/(1+z²/n).
        --
        -- A3 cascade M3 (Ihsa I1 vote 2026-05-02): TF-IDF uses the WEIGHTED
        -- aggregations (n_d_weighted, k_d_weighted) so indicators co-occurring
        -- with high-correlation recipes get higher TF. The Wilson CI keeps
        -- the unweighted (k_d, n_d) so the binomial-CI math stays valid.
        indicator_with_n AS (
            SELECT
                ic.event_category,
                ic.indicator_id,
                cast(ic.recipes_with_indicator as double) AS k_d,
                cast(rpc.n_recipes as double) AS n_d,
                -- Unweighted proportion p — used by Wilson CI only.
                cast(ic.recipes_with_indicator as double) / cast(rpc.n_recipes as double) AS p,
                -- Weighted TF-IDF: TF = sum(|r|) / sum(category |r|);
                -- IDF = ln(total weight / indicator weight).
                (ic.recipes_with_indicator_weighted / rpc.n_recipes_weighted)
                    * ln(tr.n_total_weighted / ic.recipes_with_indicator_weighted) AS tfidf
            FROM indicator_counts ic
            JOIN recipes_per_category rpc ON rpc.event_category = ic.event_category
            CROSS JOIN total_recipe_count tr
        ),
        indicator_with_ci AS (
            SELECT
                event_category,
                indicator_id,
                p AS frequency,
                tfidf,
                -- Wilson denominators / numerators broken out for readability.
                greatest(0.0,
                    ((p + 1.9208 / n_d) / (1.0 + 3.8416 / n_d))
                    - (1.96 * sqrt(p * (1.0 - p) / n_d + 0.9604 / (n_d * n_d)) / (1.0 + 3.8416 / n_d))
                ) AS ci_lower,
                least(1.0,
                    ((p + 1.9208 / n_d) / (1.0 + 3.8416 / n_d))
                    + (1.96 * sqrt(p * (1.0 - p) / n_d + 0.9604 / (n_d * n_d)) / (1.0 + 3.8416 / n_d))
                ) AS ci_upper,
                -- TODO #462 follow-up: avg correlation magnitude per indicator
                -- requires joining back to scdis. 0.0 placeholder for now.
                0.0 AS avg_corr_magnitude
            FROM indicator_with_n
        ),
        indicator_ranked AS (
            SELECT *,
                row_number() OVER (PARTITION BY event_category ORDER BY tfidf DESC) AS rn
            FROM indicator_with_ci
        ),
        indicator_fingerprints AS (
            SELECT
                event_category,
                array_agg(
                    cast(row(
                        cast(indicator_id as smallint),
                        cast(frequency as real),
                        cast(ci_lower as real),
                        cast(ci_upper as real),
                        cast(avg_corr_magnitude as real),
                        cast(tfidf as real)
                    ) as row(
                        indicator_id smallint,
                        frequency real,
                        ci_lower real,
                        ci_upper real,
                        avg_corr_magnitude real,
                        tfidf_score real
                    ))
                    ORDER BY tfidf DESC
                ) AS indicator_fingerprint
            FROM indicator_ranked
            WHERE rn <= 15
            GROUP BY event_category
        ),
        -- #519: OECD share of recipe-pair countries per event_category.
        -- Each recipe instance has a (country_a_id, country_b_id) pair. We
        -- count BOTH countries (UNION ALL) so a recipe with one OECD member
        -- contributes 0.5 to the share, not 1.0. Sources: temp_table for the
        -- pairs, qgi_data.countries for alpha_3 lookup, inline VALUES for
        -- OECD membership (38 members as of 2026-04; Costa Rica joined 2021,
        -- Colombia 2020, Lithuania 2018).
        recipe_country_unnested AS (
            SELECT event_category, recipe_id, country_a_id AS country_id
                FROM {ATHENA_DB}.{temp_table}
            UNION ALL
            SELECT event_category, recipe_id, country_b_id AS country_id
                FROM {ATHENA_DB}.{temp_table}
        ),
        oecd_members(alpha_3) AS (VALUES
            ('AUS'), ('AUT'), ('BEL'), ('CAN'), ('CHL'), ('COL'), ('CRI'),
            ('CZE'), ('DNK'), ('EST'), ('FIN'), ('FRA'), ('DEU'), ('GRC'),
            ('HUN'), ('ISL'), ('IRL'), ('ISR'), ('ITA'), ('JPN'), ('KOR'),
            ('LVA'), ('LTU'), ('LUX'), ('MEX'), ('NLD'), ('NZL'), ('NOR'),
            ('POL'), ('PRT'), ('SVK'), ('SVN'), ('ESP'), ('SWE'), ('CHE'),
            ('TUR'), ('GBR'), ('USA')
        ),
        recipe_country_with_oecd AS (
            SELECT
                rcu.event_category,
                CASE WHEN o.alpha_3 IS NOT NULL THEN 1 ELSE 0 END AS is_oecd
            FROM recipe_country_unnested rcu
            -- qgi_data.countries is OpenCSVSerde-backed: all columns are
            -- string typed, so we explicit-cast `id` to integer here to
            -- match the predicate type. Same pattern used in
            -- pipeline-recipe-engine/lambda_function.py L939.
            LEFT JOIN qgi_data.countries c ON cast(c.id as integer) = rcu.country_id
            LEFT JOIN oecd_members o ON o.alpha_3 = c.alpha_3
        ),
        oecd_shares AS (
            SELECT
                event_category,
                cast(sum(is_oecd) as double) / nullif(cast(count(*) as double), 0)
                    AS oecd_share
            FROM recipe_country_with_oecd
            GROUP BY event_category
        )
        -- Final SELECT — column order matches the Terraform Glue schema.
        SELECT
            cb.event_category,
            cb.canonical_length,
            ld.length_distribution,
            ifp.indicator_fingerprint,
            -- #519: oecd_share now computed from recipe pairs × OECD VALUES.
            -- regional_concentration still emits empty array — frontend gates
            -- rendering on `length > 0` so this is hidden, not "wrong". Tracked
            -- as #519 follow-up.
            cast(row(
                cast(cb.n_distinct_country_pairs as int),
                cast(coalesce(os.oecd_share, 0.0) as real),
                cast(array[] as array<row(region varchar, share real)>)
            ) as row(
                n_pairs int,
                oecd_share real,
                regional_concentration array<row(region varchar, share real)>
            )) AS coverage_bias_diagnostic,
            cb.total_instances,
            cb.n_distinct_country_pairs,
            cast(current_timestamp as timestamp) AS last_recomputed_at,
            '{PIPELINE_VERSION}' AS pipeline_version,
            cast({RECIPES_AGGREGATED_SCHEMA_VERSION} as smallint) AS schema_version,
            cb.contains_predicted
        FROM category_basics cb
        LEFT JOIN length_distributions ld ON ld.event_category = cb.event_category
        LEFT JOIN indicator_fingerprints ifp ON ifp.event_category = cb.event_category
        LEFT JOIN oecd_shares os ON os.event_category = cb.event_category
        """
        logger.info("[#497] Inserting into recipes_aggregated from temp table (Phase 5b.6.5 Level-4 fingerprints)")
        run_query(insert_sql)
        logger.info(f"Wrote {ATHENA_DB}.{RECIPES_AGGREGATED_TABLE_NAME}")

    finally:
        # 4. #497 — always clean up the temp table and its S3 data, even on
        # error. Leaking temp tables accumulates Glue catalog clutter and S3
        # charges; the try/finally guarantees cleanup regardless of outcome.
        logger.info(f"[#497] Cleaning up temp table {ATHENA_DB}.{temp_table}")
        try:
            run_query(f"DROP TABLE IF EXISTS {ATHENA_DB}.{temp_table}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[#497] DROP TABLE {temp_table} failed: {exc} — cleaning S3 directly")
        _s3_delete_prefix(temp_s3_prefix)
        logger.info(f"[#497] Temp cleanup done for {temp_table}")


def _s3_delete_prefix(prefix: str) -> None:
    """Delete all S3 objects under prefix in the data lake bucket.

    Used for idempotent pre-clear of output prefixes and temp-table cleanup
    (#497). Batches deletes in groups of 1000 (S3 API max).
    """
    paginator = s3.get_paginator("list_objects_v2")
    keys_to_delete = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys_to_delete.append({"Key": obj["Key"]})
            if len(keys_to_delete) >= 1000:
                s3.delete_objects(Bucket=S3_BUCKET, Delete={"Objects": keys_to_delete})
                keys_to_delete = []
    if keys_to_delete:
        s3.delete_objects(Bucket=S3_BUCKET, Delete={"Objects": keys_to_delete})


# ---------------------------------------------------------------------------
# country_recipe_scores table — Fork B Phase 5b.6.6 (#463), v0.1
# ---------------------------------------------------------------------------


def _read_indicator_map_csv():
    """Load the indicator string-id ↔ numeric_id map from S3.

    Mirrors the loader in qgi-pipeline/batch/scdi-finder/src/scdi_finder.py
    (which reads the same file directly via boto3, not Glue). Returns a
    dict {numeric_id: id_string}.

    Used by write_country_recipe_scores to inline the mapping into the
    Athena SQL via a VALUES clause — avoids needing a Glue table for the
    map (which would have to live in a dedicated S3 prefix away from
    other CSVs in `pipeline-A-indicator-extractor/input/`).
    """
    import csv
    import io

    obj = s3.get_object(Bucket=S3_BUCKET, Key=INDICATOR_MAP_S3_KEY)
    raw = obj["Body"].read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(raw))
    out = {}
    for row in reader:
        try:
            num_id = int(row["numeric_id"])
            id_str = row["id_string"].strip()
            if id_str:
                out[num_id] = id_str
        except (ValueError, KeyError):
            continue
    return out


def _load_indicator_allow_list():
    """Load the catalog-derived numeric_id allow-list from S3 (#591 Option D).

    The JSON is generated by qgi-ml/scripts/generate_indicator_allow_list.py
    (catalog markdown × indicator_map.csv) and synced to S3 by
    qgi-data/scripts/sync_indicator_allow_list.py. See
    docs/specs/internal/ops/cascade-track/phase-5-v0.0.md "Step 5" for the
    full pipeline.

    Returns a tuple of ints (immutable; safe to embed directly into the
    Athena SQL via comma-join — boto3 has already returned trusted bytes
    from a known S3 key, no SQL-injection vector).

    Raises ValueError if the JSON is malformed or empty — refuse to silently
    no-op the filter, since an empty allow-list would emit zero indicators
    in every fingerprint and that's a worse failure mode than an exception.
    """
    obj = s3.get_object(Bucket=S3_BUCKET, Key=INDICATOR_ALLOW_LIST_S3_KEY)
    raw = obj["Body"].read().decode("utf-8")
    payload = json.loads(raw)
    ids = payload.get("allow_list_numeric_ids")
    if not isinstance(ids, list) or not all(isinstance(x, int) for x in ids):
        raise ValueError("indicator-allow-list.json malformed: 'allow_list_numeric_ids' must be a list of ints")
    if not ids:
        raise ValueError(
            "indicator-allow-list.json is empty — refusing to apply a no-op filter that would emit empty fingerprints"
        )
    return tuple(sorted(set(ids)))


# Lazy cache for the allow-list. First call to _get_indicator_allow_list()
# fetches from S3 and caches into the module global; subsequent calls reuse
# the tuple. We use a sentinel (None) rather than an empty tuple so callers
# can distinguish "not loaded yet" from "intentionally empty" (which would
# raise inside the loader anyway). Lazy load (vs. import-time load) keeps
# the test suite from needing a live S3 mock at module import.
#
# Test-time bypass: when QGI_TEST_ALLOW_LIST is set (comma-separated ints),
# the cache is pre-populated with those IDs and S3 is never called. Used by
# the existing pre-#591 unit tests in tests/unit/pipeline-recipe-engine-
# finalize/test_cost_optimizations.py which mock the s3 client with generic
# MagicMocks and don't return parseable JSON for our loader.
_INDICATOR_ALLOW_LIST_CACHE: tuple[int, ...] | None = None
_qgi_test_seed = os.environ.get("QGI_TEST_ALLOW_LIST")
if _qgi_test_seed:
    try:
        _INDICATOR_ALLOW_LIST_CACHE = tuple(sorted(set(int(x) for x in _qgi_test_seed.split(",") if x.strip())))
    except ValueError:
        pass  # ignore malformed env value; fall back to lazy load


def _get_indicator_allow_list():
    """Return the cached allow-list tuple, fetching from S3 on first call."""
    global _INDICATOR_ALLOW_LIST_CACHE
    if _INDICATOR_ALLOW_LIST_CACHE is None:
        _INDICATOR_ALLOW_LIST_CACHE = _load_indicator_allow_list()
    return _INDICATOR_ALLOW_LIST_CACHE


def write_country_recipe_scores(force: bool = False):
    """Phase 5b.6.6 v0.2: Country-vs-Recipe Pearson trajectory similarity.

    For each (country, recipe) pair: compute a similarity score in [0,1]
    via per-indicator Pearson correlation between the country's recent
    trajectory and the Recipe's reference Pattern instance trajectory.

    Replaces v0.1 (weighted indicator coverage) per the design doc at
    docs/specs/internal/design/recipe-scoring-architecture.md.

    v0.2 algorithm:
        For each recipe R:
            Reference = the highest-PPS pattern instance for R in
                        recipes_deduped (its country_a_id, start_year_a,
                        length).
            For each fingerprint indicator i in R (top-K by TF-IDF):
                ref_traj  = ref_country's values for indicator i over
                            [ref_start, ref_start + canonical_length]
                subj_traj = country C's values for indicator i over
                            [now - canonical_length, now]
                r_i      = Pearson correlation between ref_traj and
                           subj_traj, aligned by relative year offset
                           0…canonical_length-1
            similarity_raw = sum(|r_i| * weight_i) / sum(weight_i)
                             where weight_i = fp[i].avg_corr_magnitude
            coverage_ratio = indicators_with_≥3_aligned_years / fingerprint_size
            suppressed     = coverage_ratio < SCORER_MIN_COVERAGE

    Properties:
    - Real trajectory comparison, not coverage proxy
    - Per-indicator Pearson, weighted aggregate
    - Min 3 paired years for a meaningful r
    - Falls back to suppressed when too few indicators alignable

    Calibration (Part B) — similarity_calibrated still equals
    similarity_raw here. The Platt training script
    qgi-ml/scripts/calibrate_recipe_similarity.py produces
    per-tier (a, b) → published to S3. Wiring the runtime sigmoid
    application into this Lambda is a follow-up commit (would JOIN
    recipes_aggregated for canonical_length, derive tier, look up
    (a, b), apply sigmoid in the SELECT).

    Performance:
    - Subject × fingerprint × paired years can be ~270 × 1065 × 18 ≈ 5M
      rows in the `paired` CTE. Athena handles this but the wall time
      is the long pole; Lambda 15-min timeout is the budget ceiling.
    - If the CTAS exceeds budget, promote to Batch (per design doc rec).

    Strategy: clear S3 prefix, INSERT INTO. Mirrors
    write_recipes_aggregated_table.
    """
    # 0. #496 idempotency guard — short-circuit if table was just rebuilt.
    if _check_idempotency_skip(
        COUNTRY_RECIPE_SCORES_TABLE_NAME,
        force=force,
        timestamp_col="last_computed_at",
    ):
        return

    # 1. Read indicator_map from S3 — small file (~270 rows).
    indicator_map = _read_indicator_map_csv()
    if not indicator_map:
        raise RuntimeError(
            f"indicator_map.csv at s3://{S3_BUCKET}/{INDICATOR_MAP_S3_KEY} "
            f"is empty or unreadable; cannot score without numeric → string id mapping"
        )
    logger.info(f"Loaded {len(indicator_map)} indicator IDs from CSV")

    # 2. Clear existing parquet data so re-runs are idempotent.
    logger.info(f"Clearing s3://{S3_BUCKET}/{COUNTRY_RECIPE_SCORES_S3_PREFIX}")
    _s3_delete_prefix(COUNTRY_RECIPE_SCORES_S3_PREFIX)

    # 3. Build inline VALUES clause for the indicator_map. Athena accepts
    # up to 1024 rows in a single VALUES; ~270 fits comfortably. Escape
    # single-quotes defensively even though indicator IDs shouldn't have any.
    map_rows = ", ".join(
        f"({nid}, '{sid.replace(chr(39), chr(39) + chr(39))}')" for nid, sid in sorted(indicator_map.items())
    )

    # 4. INSERT INTO. Column order MUST match the Terraform-owned Glue
    # schema (qgi-infra/modules/storage/main.tf
    # aws_glue_catalog_table.country_recipe_scores). Failure to match is
    # an Athena type error — fails loud, not silent.
    sql = f"""
    INSERT INTO {ATHENA_DB}.{COUNTRY_RECIPE_SCORES_TABLE_NAME}
    WITH indicator_map AS (
        SELECT numeric_id, id_string
        FROM (VALUES {map_rows}) AS t(numeric_id, id_string)
    ),
    -- One row per (recipe, fingerprint indicator) — typically 71 × 15 ≈ 1065.
    -- weight = tfidf_score (per-category indicator importance). The original
    -- v0.2 design used avg_corr_magnitude, but that field is currently a
    -- 0.0 placeholder in recipes_aggregated (CTAS TODO requires a 12B-row
    -- scdis JOIN). tfidf_score is computed in the same CTAS and approximates
    -- indicator distinctiveness — non-zero, monotone with frequency, and
    -- avoids the all-NULL similarity_raw outcome of weighted-by-zero.
    fp_unnested AS (
        SELECT
            ra.event_category,
            cast(ra.canonical_length as integer) AS L,
            cast(fp.indicator_id as integer) AS num_id,
            cast(fp.tfidf_score as double) AS weight,
            cardinality(ra.indicator_fingerprint) AS n_in_fp,
            COALESCE(ra.contains_predicted, FALSE) AS recipe_contains_predicted
        FROM {ATHENA_DB}.{RECIPES_AGGREGATED_TABLE_NAME} ra
        CROSS JOIN UNNEST(ra.indicator_fingerprint) AS u(fp)
    ),
    fp_with_string AS (
        SELECT fp.*, im.id_string
        FROM fp_unnested fp
        JOIN indicator_map im ON im.numeric_id = fp.num_id
    ),
    -- v0.2: reference pattern instance per recipe — the highest-PPS
    -- pattern from recipes_deduped. Its country_a + window define the
    -- "expected trajectory" the subject's recent trajectory is compared
    -- against per-indicator below.
    ref_pattern_ranked AS (
        SELECT
            rd.event_category,
            cast(rd.country_a_id as integer) AS ref_country_id,
            cast(rd.start_year_a as integer) AS ref_start,
            cast(rd.length as integer) AS ref_length,
            ROW_NUMBER() OVER (
                PARTITION BY rd.event_category
                ORDER BY rd.pattern_power_score DESC
            ) AS rn
        FROM {ATHENA_DB}.{RECIPES_DEDUPED_VIEW_NAME} rd
    ),
    ref_pattern_top AS (
        SELECT event_category, ref_country_id, ref_start, ref_length
        FROM ref_pattern_ranked
        WHERE rn = 1
    ),
    -- Country id ↔ name lookup. indicators_completed is keyed by name
    -- (string), recipes/patterns/scores are keyed by id (smallint) — the
    -- countries reference table is the bridge.
    countries_indexed AS (
        SELECT cast(cd.id as integer) AS country_id, cd.name_1 AS name
        FROM {ATHENA_DB}.countries cd
        WHERE cd.name_1 IS NOT NULL AND cd.name_1 != ''
          AND cd.id IS NOT NULL AND cd.id != ''
    ),
    -- v0.2: reference trajectory per (recipe, fingerprint indicator).
    -- Pulls the ref country's values for the fp indicator over the ref
    -- pattern instance's window. Year offset 0…(L-1) becomes the alignment
    -- key for the Pearson pairing.
    ref_values AS (
        SELECT
            fws.event_category,
            fws.num_id,
            fws.weight,
            fws.n_in_fp,
            fws.recipe_contains_predicted,
            fws.L,
            ic.year - rpt.ref_start AS year_offset,
            cast(ic.value as double) AS ref_value
        FROM fp_with_string fws
        JOIN ref_pattern_top rpt ON rpt.event_category = fws.event_category
        JOIN countries_indexed rcn ON rcn.country_id = rpt.ref_country_id
        JOIN {ATHENA_DB}.indicators_completed ic
            ON ic.indicator_id = fws.id_string
           AND ic.country = rcn.name
           AND ic.year >= rpt.ref_start
           AND ic.year < rpt.ref_start + fws.L
           AND ic.value IS NOT NULL
    ),
    -- v0.2: subject trajectory per (subject, recipe, fingerprint indicator).
    -- Pulls each scoreable country's last L years of values for the
    -- fp indicator. Year offset 0…(L-1) is the relative position in the
    -- last-L-years window — same scale as ref_values so Pearson pairing
    -- aligns by position, not absolute year.
    NOW_YEAR AS (SELECT year(current_timestamp) AS y),
    subject_values AS (
        SELECT
            cast(ci.country_id as smallint) AS subject_id,
            fws.event_category,
            fws.num_id,
            ic.year - (n.y - fws.L) AS year_offset,
            cast(ic.value as double) AS subj_value
        FROM countries_indexed ci
        CROSS JOIN fp_with_string fws
        CROSS JOIN NOW_YEAR n
        JOIN {ATHENA_DB}.indicators_completed ic
            ON ic.indicator_id = fws.id_string
           AND ic.country = ci.name
           AND ic.year >= n.y - fws.L
           AND ic.year < n.y
           AND ic.value IS NOT NULL
    ),
    -- v0.2: pair subject + ref by (event_category, num_id, year_offset).
    -- Inner join — only year offsets present in BOTH series contribute to
    -- the Pearson sum. This handles missing-year gracefully without
    -- introducing imputation bias.
    paired AS (
        SELECT
            sv.subject_id,
            sv.event_category,
            sv.num_id,
            sv.subj_value AS x,
            rv.ref_value AS y,
            rv.weight,
            rv.n_in_fp,
            rv.recipe_contains_predicted
        FROM subject_values sv
        JOIN ref_values rv
            ON rv.event_category = sv.event_category
           AND rv.num_id = sv.num_id
           AND rv.year_offset = sv.year_offset
    ),
    -- v0.2: Pearson aggregations per (subject, recipe, indicator).
    -- HAVING n >= 3: need at least 3 aligned years for a meaningful r.
    -- Below 3, the indicator drops out of the aggregation entirely.
    pearson_sums AS (
        SELECT
            subject_id, event_category, num_id, weight, n_in_fp,
            recipe_contains_predicted,
            COUNT(*) AS n,
            SUM(x) AS sx, SUM(y) AS sy,
            SUM(x*y) AS sxy, SUM(x*x) AS sxx, SUM(y*y) AS syy
        FROM paired
        GROUP BY subject_id, event_category, num_id, weight, n_in_fp,
                 recipe_contains_predicted
        HAVING COUNT(*) >= 3
    ),
    r_per_indicator AS (
        SELECT
            subject_id, event_category, num_id, weight, n_in_fp,
            recipe_contains_predicted,
            -- Pearson r = (n*sxy - sx*sy) / sqrt((n*sxx - sx²)(n*syy - sy²))
            -- Defensive: when either denominator term is ≤ 0 (constant series),
            -- emit r=0 instead of NaN — Athena propagates NaN through
            -- aggregations and we don't want the recipe-level score to NaN
            -- because of one degenerate indicator series.
            CASE
                WHEN (n*sxx - sx*sx) > 0 AND (n*syy - sy*sy) > 0
                THEN (n*sxy - sx*sy)
                     / sqrt((n*sxx - sx*sx) * (n*syy - sy*sy))
                ELSE 0.0
            END AS r
        FROM pearson_sums
    ),
    -- v0.2: aggregate per (subject, recipe). Weighted mean of |r| with
    -- weight = avg_corr_magnitude (the recipe's per-indicator importance).
    -- Indicators with insufficient paired years (<3) silently drop out;
    -- the coverage_ratio reflects that.
    aggregated AS (
        SELECT
            subject_id AS country_id,
            event_category,
            sum(ABS(r) * weight) / nullif(sum(weight), 0.0) AS similarity_raw,
            cast(count(*) as integer) AS indicators_matched,
            cast(max(n_in_fp) as integer) AS indicators_in_fingerprint,
            cast(count(*) as double) / nullif(cast(max(n_in_fp) as double), 0.0)
                AS coverage_ratio,
            bool_or(recipe_contains_predicted) AS contains_predicted
        FROM r_per_indicator
        GROUP BY subject_id, event_category
    )
    SELECT
        cast(country_id as smallint) AS country_id,
        event_category,
        cast(similarity_raw as real) AS similarity_raw,
        -- v0.2: similarity_calibrated == similarity_raw still — Part B
        -- (Platt) trains (a,b) per tier in qgi-ml/scripts/calibrate_recipe_similarity.py
        -- and publishes to s3://(bucket)/calibration/recipe_similarity_vN/.
        -- Lambda runtime read + sigmoid application is a follow-up commit.
        cast(similarity_raw as real) AS similarity_calibrated,
        cast(indicators_matched as smallint) AS indicators_matched,
        cast(indicators_in_fingerprint as smallint) AS indicators_in_fingerprint,
        cast(coverage_ratio as real) AS coverage_ratio,
        coverage_ratio < {SCORER_MIN_COVERAGE} AS suppressed,
        CASE WHEN coverage_ratio < {SCORER_MIN_COVERAGE}
            THEN 'insufficient indicator coverage ('
                 || cast(indicators_matched as varchar) || '/'
                 || cast(indicators_in_fingerprint as varchar)
                 || ' — minimum {int(SCORER_MIN_COVERAGE * 100)}%)'
            ELSE cast(NULL as varchar)
        END AS suppression_reason,
        contains_predicted,
        cast(current_timestamp as timestamp) AS last_computed_at,
        '{PIPELINE_VERSION}' AS pipeline_version,
        cast(NULL as varchar) AS calibration_mapping_version
    FROM aggregated
    """
    logger.info("Inserting into country_recipe_scores (Phase 5b.6.6 v0.2 Pearson)")
    run_query(sql)
    logger.info(f"Wrote {ATHENA_DB}.{COUNTRY_RECIPE_SCORES_TABLE_NAME}")


# ---------------------------------------------------------------------------
# Convergence view (#133)
# ---------------------------------------------------------------------------


def _country_region_pairs():
    for region, codes in COUNTRY_REGIONS.items():
        for code in sorted(codes):
            yield code, region


def _country_regions_values_sql():
    rows = ",\n            ".join(f"('{code}', '{region}')" for code, region in _country_region_pairs())
    return f"(VALUES\n            {rows}\n        ) AS t(alpha_2, region)"


def create_convergence_view():
    """#133 convergence view — reads from recipes_normalized."""
    region_values = _country_regions_values_sql()
    sql = f"""
    CREATE OR REPLACE VIEW {ATHENA_DB}.{CONVERGENCE_VIEW_NAME} AS
    WITH country_regions AS (
        SELECT alpha_2, region FROM {region_values}
    ),
    countries_dedup AS (
        SELECT id, MAX(alpha_2) AS alpha_2
        FROM {ATHENA_DB}.countries
        WHERE alpha_2 IS NOT NULL AND alpha_2 != ''
        GROUP BY id
    ),
    predictor_counts AS (
        SELECT
            r.country_a_id           AS following_country_id,
            r.event_category,
            r.end_year_a,
            r.country_b_id           AS predictor_country_id,
            COUNT(*)                 AS recipe_count,
            MAX(r.pps)               AS predictor_best_pps,
            ARBITRARY(r.pattern_tier) AS predictor_best_tier
        -- #158 follow-up: read from normalized view so pps is globally comparable
        FROM {ATHENA_DB}.{RECIPES_NORMALIZED_VIEW_NAME} r
        GROUP BY r.country_a_id, r.event_category, r.end_year_a, r.country_b_id
    ),
    predictor_contributions AS (
        SELECT
            pc.following_country_id,
            pc.event_category,
            pc.end_year_a,
            pc.predictor_country_id,
            pc.recipe_count,
            pc.predictor_best_pps,
            pc.predictor_best_tier,
            pr.region                                  AS predictor_region,
            CASE
                WHEN fr.region IS NOT NULL
                 AND pr.region IS NOT NULL
                 AND fr.region = pr.region THEN 0.7
                ELSE 1.0
            END                                        AS region_factor,
            LN(1.0 + CAST(pc.recipe_count AS double)) *
                CASE
                    WHEN fr.region IS NOT NULL
                     AND pr.region IS NOT NULL
                     AND fr.region = pr.region THEN 0.7
                    ELSE 1.0
                END                                    AS contribution
        FROM predictor_counts pc
        LEFT JOIN countries_dedup cf ON cf.id = CAST(pc.following_country_id AS varchar)
        LEFT JOIN countries_dedup cp ON cp.id = CAST(pc.predictor_country_id AS varchar)
        LEFT JOIN country_regions fr ON fr.alpha_2 = cf.alpha_2
        LEFT JOIN country_regions pr ON pr.alpha_2 = cp.alpha_2
    ),
    forecast_aggregated AS (
        SELECT
            following_country_id,
            event_category,
            end_year_a,
            SUM(contribution)                                       AS convergence_score,
            COUNT(DISTINCT predictor_country_id)                    AS n_predictors,
            COUNT(DISTINCT predictor_region)                        AS n_regions,
            MAX(predictor_best_pps)                                 AS best_pps,
            ARBITRARY(predictor_best_tier)                          AS best_tier,
            ARRAY_AGG(predictor_country_id ORDER BY predictor_best_pps DESC) AS predictor_country_ids
        FROM predictor_contributions
        GROUP BY following_country_id, event_category, end_year_a
    )
    SELECT
        following_country_id,
        event_category,
        end_year_a,
        convergence_score,
        n_predictors,
        n_regions,
        best_pps,
        best_tier,
        predictor_country_ids,
        CASE
            WHEN n_predictors < 2          THEN 'single'
            WHEN convergence_score < 4.0   THEN 'emerging'
            WHEN convergence_score < 7.0   THEN 'multilateral'
            ELSE 'high'
        END                                                                AS convergence_tier,
        best_pps * LN(1.0 + convergence_score)                             AS composite_sort_key
    FROM forecast_aggregated
    """
    logger.info(f"Creating convergence view ({len(sql)} chars)")
    run_query(sql)
    logger.info(f"Convergence view {ATHENA_DB}.{CONVERGENCE_VIEW_NAME} created")


# ---------------------------------------------------------------------------
# Dashboard JSONs (#146)
# ---------------------------------------------------------------------------


def write_dashboard_jsons():
    current_year = datetime.now(timezone.utc).year
    results = {
        "ranking": _write_ranking_json(),
        "early_warning": _write_early_warning_json(current_year),
        "recipes_top50": _write_recipes_top50_json(current_year),
    }
    # #375 — country-risks.json (V1.8.1 scoring) auto-generated at pipeline end
    try:
        country_risks_summary = write_country_risks_json(
            run_query_fn=run_query,
            rows_fn=_rows_from_query_id,
            s3_client=s3,
            bucket=S3_BUCKET,
            athena_db=ATHENA_DB,
            cloudwatch_client=cloudwatch,  # #381 drift metric emission
        )
        results["country_risks"] = country_risks_summary
        logger.info(f"country-risks.json: {country_risks_summary}")
    except Exception as exc:  # noqa: BLE001
        # Non-fatal: the 3 core dashboard JSONs already landed; country-risks
        # was added in #375 and shouldn't block the pipeline on regression.
        # #409: emit CloudWatch metric so the 2026-04-22 silent-failure class
        # (2 days of missing regeneration before anyone noticed) cannot recur
        # without an alarm firing.
        logger.exception(f"country-risks.json generation failed: {exc}")
        results["country_risks"] = {"error": str(exc)}
        _emit_caught_exception("write_country_risks_json")
    return results


def _write_ranking_json():
    sql = f"""
    WITH c AS (
        SELECT id, MAX(name_1) AS name FROM {ATHENA_DB}.countries WHERE name_1 != '' GROUP BY id
    )
    SELECT * FROM (
        SELECT ca.name AS country_a, cb.name AS country_b,
               p.start_year_a, p.start_year_b, p.length AS pattern_length,
               p.indicator_count AS num_indexes, p.avg_correlation, p.pattern_power_score,
               CAST(p.country_a_id AS VARCHAR) AS country_a_id,
               CAST(p.country_b_id AS VARCHAR) AS country_b_id,
               -- #558: pattern_tier SQL centralized in _shared/pattern_tier.py
               COALESCE(p.pattern_tier, {pattern_tier_case_sql("p.length")}) AS pattern_tier,
               ROW_NUMBER() OVER (ORDER BY p.pattern_power_score DESC) AS rn
        FROM {ATHENA_DB}.patterns p
        LEFT JOIN c ca ON ca.id = CAST(p.country_a_id AS VARCHAR)
        LEFT JOIN c cb ON cb.id = CAST(p.country_b_id AS VARCHAR)
    ) t
    WHERE rn <= {RANKING_LIMIT}
    ORDER BY rn
    """
    rows = _run_query_to_rows(sql)
    results = [
        {
            "country_a": r.get("country_a") or r.get("country_a_id"),
            "country_b": r.get("country_b") or r.get("country_b_id"),
            "country_a_id": r.get("country_a_id"),
            "country_b_id": r.get("country_b_id"),
            "start_year_a": _to_int(r.get("start_year_a")),
            "start_year_b": _to_int(r.get("start_year_b")),
            "pattern_length": _to_int(r.get("pattern_length")),
            "avg_correlation": _to_float(r.get("avg_correlation")),
            "pattern_power_score": _to_float(r.get("pattern_power_score")),
            "num_indexes": _to_int(r.get("num_indexes")),
            "pattern_tier": r.get("pattern_tier"),
            "predicted": False,
        }
        for r in rows
    ]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "limit": RANKING_LIMIT,
        "results": results,
    }
    _put_dashboard_json("ranking.json", payload)
    return len(results)


def _write_early_warning_json(current_year):
    sql = f"""
    WITH c AS (
        SELECT id, MAX(name_1) AS name FROM {ATHENA_DB}.countries WHERE name_1 != '' GROUP BY id
    )
    SELECT ca.name AS country_a, cb.name AS country_b,
           p.start_year_a, p.start_year_b, p.length AS pattern_length,
           p.avg_correlation, p.pattern_power_score,
           p.indicator_count AS num_indexes,
           -- #558: pattern_tier SQL centralized in _shared/pattern_tier.py
           COALESCE(p.pattern_tier, {pattern_tier_case_sql("p.length")}) AS pattern_tier
    FROM {ATHENA_DB}.patterns p
    LEFT JOIN c ca ON ca.id = CAST(p.country_a_id AS VARCHAR)
    LEFT JOIN c cb ON cb.id = CAST(p.country_b_id AS VARCHAR)
    WHERE p.start_year_b < p.start_year_a
      AND (p.start_year_a + p.length) >= {current_year - 2}
    ORDER BY p.pattern_power_score DESC
    LIMIT 500
    """
    rows = _run_query_to_rows(sql)
    results = [
        {
            **r,
            "avg_correlation": _to_float(r.get("avg_correlation")),
            "pattern_power_score": _to_float(r.get("pattern_power_score")),
            "num_indexes": _to_int(r.get("num_indexes")),
        }
        for r in rows
    ]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of_year": current_year,
        "results": results,
    }
    _put_dashboard_json("early-warning.json", payload)
    return len(results)


def _write_recipes_top50_json(current_year):
    """Top 50 recipes via convergence view, reading through recipes_normalized
    for globally-comparable pps.
    """
    sql = f"""
    WITH joined AS (
        SELECT
            r.*,
            cv.convergence_score,
            cv.n_predictors,
            cv.n_regions,
            cv.convergence_tier,
            cv.predictor_country_ids,
            cv.composite_sort_key
        -- #158 follow-up: recipes_normalized for globally-comparable pps
        FROM {ATHENA_DB}.{RECIPES_NORMALIZED_VIEW_NAME} r
        INNER JOIN {ATHENA_DB}.{CONVERGENCE_VIEW_NAME} cv
            ON cv.following_country_id = r.country_a_id
           AND cv.event_category       = r.event_category
           AND cv.end_year_a           = r.end_year_a
        WHERE r.start_year_b < r.start_year_a
          AND (r.start_year_a + r.length) >= {current_year - 2}
          AND (r.start_year_a + r.length) <= {current_year + 3}
          AND cv.n_predictors >= 2
    ),
    ranked AS (
        SELECT j.*,
            ROW_NUMBER() OVER (PARTITION BY j.country_a_id   ORDER BY j.composite_sort_key DESC) AS country_rank,
            ROW_NUMBER() OVER (PARTITION BY j.event_category ORDER BY j.composite_sort_key DESC) AS cat_rank
        FROM joined j
    )
    SELECT * FROM ranked
    WHERE country_rank <= 3 AND cat_rank <= 10
    ORDER BY composite_sort_key DESC
    LIMIT 50
    """
    rows = _run_query_to_rows(sql)
    results = [
        {
            "recipe_id": r.get("recipe_id"),
            "event_category": r.get("event_category"),
            "country_a_id": _to_int(r.get("country_a_id")),
            "country_b_id": _to_int(r.get("country_b_id")),
            "country_a_name": r.get("country_a_name") or f"Country {r.get('country_a_id')}",
            "country_b_name": r.get("country_b_name") or f"Country {r.get('country_b_id')}",
            "start_year_a": _to_int(r.get("start_year_a")),
            "start_year_b": _to_int(r.get("start_year_b")),
            "length": _to_int(r.get("length")),
            "avg_correlation": _to_float(r.get("avg_correlation")),
            "end_year_a": _to_int(r.get("end_year_a")),
            "end_year_b": _to_int(r.get("end_year_b")),
            "event_window": _to_int(r.get("event_window")),
            "event_year_a": _to_int(r.get("event_year_a")),
            "event_year_b": _to_int(r.get("event_year_b")),
            "event_title_a": r.get("event_title_a"),
            "event_title_b": r.get("event_title_b"),
            "indicator_count": _to_int(r.get("indicator_count")),
            "instance_count": _to_int(r.get("instance_count")),
            "pattern_power_score": _to_float(r.get("pattern_power_score")),
            "pps": _to_float(r.get("pps")),
            "pattern_tier": r.get("pattern_tier"),
            "median_lead_time": _to_int(r.get("median_lead_time_b")),
            "min_lead_time": _to_int(r.get("min_lead_time_b")),
            "max_lead_time": _to_int(r.get("max_lead_time_b")),
            "convergence_score": _to_float(r.get("convergence_score")),
            "convergence_tier": r.get("convergence_tier"),
            "n_predictors": _to_int(r.get("n_predictors")),
            "n_regions": _to_int(r.get("n_regions")),
            "predictor_country_ids": _parse_id_array(r.get("predictor_country_ids")),
            "composite_sort_key": _to_float(r.get("composite_sort_key")),
        }
        for r in rows
    ]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of_year": current_year,
        "results": results,
    }
    _put_dashboard_json("recipes-top50.json", payload)
    return len(results)


def _put_dashboard_json(filename, payload):
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=f"{DASHBOARD_PREFIX}/{filename}",
        Body=body,
        ContentType="application/json",
        CacheControl="public, max-age=300, s-maxage=86400",
    )
    logger.info(f"Wrote s3://{S3_BUCKET}/{DASHBOARD_PREFIX}/{filename} ({len(body)} bytes)")


def _rows_from_query_id(query_id):
    """Fetch result rows for an already-executed Athena query.

    Used by write_country_risks_json which follows the protocol
    `rows_fn(run_query_fn(sql))` — run_query_fn returns a query_id, rows_fn
    expects a query_id (NOT raw SQL). See country_risks.py callsites.
    """
    rows = []
    headers = None
    next_token = None
    while True:
        kwargs = {"QueryExecutionId": query_id}
        if next_token:
            kwargs["NextToken"] = next_token
        result = athena.get_query_results(**kwargs)
        result_rows = result["ResultSet"]["Rows"]
        if headers is None:
            headers = [col.get("VarCharValue", "") for col in result_rows[0]["Data"]]
            data_rows = result_rows[1:]
        else:
            data_rows = result_rows
        for row in data_rows:
            cells = row.get("Data", [])
            rows.append(
                {headers[i]: cells[i].get("VarCharValue", "") if i < len(cells) else "" for i in range(len(headers))}
            )
        next_token = result.get("NextToken")
        if not next_token:
            break
    return rows


def _run_query_to_rows(sql):
    """Convenience: execute sql + return rows. Used by dashboard-JSON builders
    that construct a query inline and want rows in one call."""
    return _rows_from_query_id(run_query(sql))


def _to_int(value):
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_id_array(value):
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [int(x) for x in value if x is not None]
    s = str(value).strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    out = []
    for piece in s.split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            out.append(int(piece))
        except ValueError:
            continue
    return out


def run_query(sql):
    """Sync Athena query with 1s poll loop. Raises on FAILED/CANCELLED."""
    response = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": ATHENA_DB},
        WorkGroup=ATHENA_WG,
    )
    query_id = response["QueryExecutionId"]
    logger.info(f"Query {query_id}: started")
    while True:
        status = athena.get_query_execution(QueryExecutionId=query_id)
        state = status["QueryExecution"]["Status"]["State"]
        if state == "SUCCEEDED":
            logger.info(f"Query {query_id}: SUCCEEDED")
            return query_id
        if state in ("FAILED", "CANCELLED"):
            reason = status["QueryExecution"]["Status"].get("StateChangeReason", "unknown")
            logger.error(f"Query {query_id}: {state} - {reason}")
            raise RuntimeError(f"Athena query {state}: {reason}")
        time.sleep(1)
