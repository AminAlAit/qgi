"""
Phase 1 Batch Dispatcher (#FAR-1)

Replaces the legacy EC2 + SSM single-instance fetcher with a fan-out to
AWS Batch on Fargate Spot — one job per indicator. Each job sleeps a
random 1-5 min before its WB API call to enforce rate limiting via
natural distribution rather than centralized coordination.

## What this Lambda does

1. Reads `indicators/indicators.json` from S3 (written by sheet-fetcher).
2. Filters to status='process'.
3. Resets the qgi-pipeline-a-counter for this run_id (PutItem with
   pending = N). Always overwrites — re-running a stuck Step Function
   does not require manual cleanup.
4. Submits N AWS Batch jobs to the Fargate Spot job queue, one per
   indicator. Each job receives the indicator id + run_id + table
   names via container env var overrides.
5. Returns the count for the Step Function's logs.

The checker Lambda then polls the counter (every 2 min) until it
reaches 0; the Reporter Lambda sends the email; Phase 1.5 advances.

## Why we seed the counter to N upfront
Fargate Spot doesn't provision all N tasks instantly — they trickle in
over 30-90 seconds. If the counter started at 0 and tasks did +1 on
start, -1 on success, the counter could momentarily hit 0 between the
fast tasks finishing and the slow tasks starting. The next-phase Lambda
would advance prematurely. Seeding to N upfront eliminates the race:
the counter can only ever DECREASE from N to 0, and can only hit 0
once when every task has reported.
"""

import json
import logging
import os
import time
from decimal import Decimal

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")
batch = boto3.client("batch")
dynamodb = boto3.resource("dynamodb")

S3_BUCKET = os.environ["S3_BUCKET"]
INDICATORS_KEY = "indicators/indicators.json"

BATCH_JOB_QUEUE = os.environ["BATCH_JOB_QUEUE"]
# Legacy: one JobDef for every indicator. Still the default when an
# indicator's provider isn't in BATCH_JOB_DEFINITION_MAP (below).
BATCH_JOB_DEFINITION = os.environ["BATCH_JOB_DEFINITION"]
# #240 Phase A: per-provider JobDef routing. JSON map of provider
# name -> Batch JobDef ARN. When an indicator's `provider` field
# matches a key here, the dispatcher submits to that JobDef instead
# of the default. Lets WB indicators flow to the WB fetcher and
# FAOSTAT indicators flow to the FAOSTAT bulk-download fetcher.
# Empty/missing env var = legacy single-JobDef behaviour.
try:
    BATCH_JOB_DEFINITION_MAP = json.loads(os.environ.get("BATCH_JOB_DEFINITION_MAP", "{}"))
    if not isinstance(BATCH_JOB_DEFINITION_MAP, dict):
        raise ValueError("BATCH_JOB_DEFINITION_MAP must decode to a dict")
except (ValueError, json.JSONDecodeError) as exc:
    logger.warning(
        "BATCH_JOB_DEFINITION_MAP env var is not valid JSON map; falling back to legacy single-JobDef mode. error=%s",
        exc,
    )
    BATCH_JOB_DEFINITION_MAP = {}

COUNTER_TABLE = os.environ["COUNTER_TABLE"]  # qgi-pipeline-a-counter
TRACKER_TABLE = os.environ.get("TRACKER_TABLE", "qgi-indicator-updates")
INDICATOR_VALUES_TABLE = os.environ.get("INDICATOR_VALUES_TABLE", "qgi-indicator-values")
ATHENA_DATABASE = os.environ.get("ATHENA_DATABASE", "qgi_data")
ATHENA_WORKGROUP = os.environ.get("ATHENA_WORKGROUP", "QGI-Lambda-Workgroup")
# #416 — ATHENA_OUTPUT_LOCATION removed; workgroup enforces its own location.
# No longer forwarded to the indicator-fetcher Fargate container (which also
# dropped ResultConfiguration per #416).

JITTER_MIN_S = os.environ.get("JITTER_MIN_S", "60")
JITTER_MAX_S = os.environ.get("JITTER_MAX_S", "300")

# DISPATCH_LIMIT: cap the number of indicators dispatched per run.
# 0 = unlimited (production). Useful for E2E tests with 2-5 indicators.
DISPATCH_LIMIT = int(os.environ.get("DISPATCH_LIMIT", "0"))

counter_table = dynamodb.Table(COUNTER_TABLE)


# --------------------------------------------------------------------- #
# #241 Phase B: task-unit grouping per provider                         #
# --------------------------------------------------------------------- #
# Different providers have different "fetch units":
#
#   WB        — one indicator per task (per-indicator API call).
#               Task unit = 1 indicator.
#
#   FAOSTAT   — one bulk-download ZIP per DOMAIN, each domain contains
#               multiple indicators. Downloading the same 100MB ZIP 6
#               times (once per indicator in that domain) would waste
#               ~500MB of egress per pipeline run. Group by
#               `fao_domain_code` so one task fetches all indicators
#               in its domain.
#
# Adding a new provider with a bulk pattern is a one-line addition to
# _PROVIDER_TASK_GROUPING.

# For providers not listed here, the default is "one task per indicator"
# (same as WB). This is safe for API-per-indicator providers.
_PROVIDER_TASK_GROUPING: dict[str, str] = {
    # Provider -> name of the indicator field to group by.
    # (None/absent field = one task per indicator.)
    "FAOSTAT": "fao_domain_code",
}


def _group_indicators_into_task_units(
    indicators: list[dict],
) -> list[dict]:
    """Turn a flat list of indicators into a list of "task units" that
    the dispatcher will each submit as ONE Batch job.

    Each returned unit is a dict: ``{provider, group_key, indicators}``
    where ``indicators`` is the list of indicators that share this
    task. For single-indicator units (the WB case), the list has
    length 1.
    """
    units: list[dict] = []
    # Walk the indicators in order, grouping contiguous-same-provider
    # runs into task units. We key by (provider, group_value) so a
    # FAOSTAT domain's indicators always land in the same unit even
    # if they were interleaved in the XLSX.
    bucketed: dict[tuple[str, str | None], list[dict]] = {}
    bucket_order: list[tuple[str, str | None]] = []
    for ind in indicators:
        provider = ind.get("provider") or "WB"
        group_field = _PROVIDER_TASK_GROUPING.get(provider)
        if group_field:
            group_value = ind.get(group_field)
            if group_value is None:
                # Defensive: provider needs a group field but indicator
                # doesn't have it set. Fall back to per-indicator unit
                # (key each by id_string so they get their own tasks).
                key = (provider, f"__ungrouped__{ind['id_string']}")
            else:
                key = (provider, str(group_value))
        else:
            # One task per indicator for this provider.
            key = (provider, f"__single__{ind['id_string']}")

        if key not in bucketed:
            bucketed[key] = []
            bucket_order.append(key)
        bucketed[key].append(ind)

    for key in bucket_order:
        provider, group_value = key
        units.append(
            {
                "provider": provider,
                "group_key": group_value,
                "indicators": bucketed[key],
            }
        )
    return units


def _build_task_env(
    unit: dict,
    run_id: str,
) -> list[dict]:
    """Build the container env-var list for one task unit's Batch job.

    Single-indicator units get INDICATOR_ID (existing WB shape). Multi-
    indicator units (FAOSTAT domains) get DOMAIN_CODE + INDICATORS_JSON
    instead. Common env (PROVIDER, RUN_ID, S3, DDB, Athena) is always
    included — the FAOSTAT fetcher reads the same set as the WB one.
    """
    provider = unit["provider"]
    indicators = unit["indicators"]

    base_env = [
        {"name": "PROVIDER", "value": provider},
        {"name": "RUN_ID", "value": run_id},
        {"name": "S3_BUCKET", "value": S3_BUCKET},
        {"name": "COUNTER_TABLE", "value": COUNTER_TABLE},
        {"name": "TRACKER_TABLE", "value": TRACKER_TABLE},
        {"name": "INDICATOR_VALUES_TABLE", "value": INDICATOR_VALUES_TABLE},
        {"name": "ATHENA_DATABASE", "value": ATHENA_DATABASE},
        {"name": "ATHENA_WORKGROUP", "value": ATHENA_WORKGROUP},
        # #416 — ATHENA_OUTPUT_LOCATION no longer forwarded; workgroup enforces.
        {"name": "JITTER_MIN_S", "value": str(JITTER_MIN_S)},
        {"name": "JITTER_MAX_S", "value": str(JITTER_MAX_S)},
    ]

    if len(indicators) == 1 and not _PROVIDER_TASK_GROUPING.get(provider):
        # Legacy per-indicator shape (WB and anything without a group
        # field). Pass INDICATOR_ID as the fetcher expects today.
        base_env.append({"name": "INDICATOR_ID", "value": indicators[0]["id_string"]})
    else:
        # Multi-indicator unit (e.g., FAOSTAT domain). The fetcher
        # reads DOMAIN_CODE + INDICATORS_JSON and loops over them.
        base_env.append({"name": "DOMAIN_CODE", "value": str(unit["group_key"])})
        base_env.append(
            {
                "name": "INDICATORS_JSON",
                "value": json.dumps(
                    [
                        {
                            "id_string": i["id_string"],
                            "numeric_id": i["numeric_id"],
                            # Pass through provider-specific fields the fetcher
                            # needs. For FAOSTAT: item_code + element_code.
                            **{
                                k: v
                                for k, v in i.items()
                                if k
                                not in (
                                    "id_string",
                                    "numeric_id",
                                    "name",
                                    "status",
                                    "category",
                                    "description",
                                    "license",
                                    "hidden_source",
                                    "provider",
                                )
                            },
                        }
                        for i in indicators
                    ]
                ),
            }
        )
    return base_env


def lambda_handler(event, context):
    run_id = event.get("run_id", "unknown")
    logger.info(f"Phase 1 Batch dispatcher starting for run_id={run_id}")

    # 1. Load indicators config from S3
    obj = s3.get_object(Bucket=S3_BUCKET, Key=INDICATORS_KEY)
    config = json.loads(obj["Body"].read().decode("utf-8"))
    process_list = [i for i in config["indicators"] if i["status"] == "process"]

    if DISPATCH_LIMIT > 0:
        process_list = process_list[:DISPATCH_LIMIT]
        logger.info(f"DISPATCH_LIMIT={DISPATCH_LIMIT} applied")

    n = len(process_list)
    logger.info(f"Will dispatch {n} Batch jobs")

    if n == 0:
        # Edge case: nothing to do. Set counter to 0 so the checker
        # immediately advances.
        counter_table.put_item(Item={"run_id": run_id, "pending": Decimal(0)})
        return {"dispatched": 0, "run_id": run_id}

    # 2. Seed the counter — overwrite any prior value for this run_id
    counter_table.put_item(
        Item={
            "run_id": run_id,
            "pending": Decimal(n),
            "total": Decimal(n),  # immutable, for the reporter to compare against
        }
    )
    logger.info(f"Counter seeded: {COUNTER_TABLE}[{run_id}].pending = {n}")

    # 3. Group indicators into task units (one Batch job per unit).
    #    Per #241 Phase B: FAOSTAT indicators are grouped by domain so
    #    the 6 indicators in FS domain share ONE task that downloads the
    #    FS ZIP once, instead of 6 tasks each downloading the same ZIP.
    task_units = _group_indicators_into_task_units(process_list)
    logger.info(f"Grouped {len(process_list)} indicators into {len(task_units)} task units")

    # 4. Submit Batch jobs (one per task unit).
    submitted_indicators = 0
    submitted_units = 0
    submit_failures: list[str] = []  # indicator IDs that failed to submit
    # Track per-provider submission counts (in INDICATOR units, not task
    # units — the reporter wants "259 WB + 15 FAOSTAT", not "259 WB
    # tasks + 8 FAOSTAT tasks").
    per_provider_counts: dict[str, int] = {}
    for unit in task_units:
        provider = unit["provider"]
        indicators = unit["indicators"]
        unit_size = len(indicators)
        job_definition = BATCH_JOB_DEFINITION_MAP.get(provider, BATCH_JOB_DEFINITION)
        # Build a task-unit job name. For single-indicator units, name
        # by the indicator id (legacy shape). For multi-indicator
        # (FAOSTAT domain) units, name by provider + group_key.
        if unit_size == 1 and not _PROVIDER_TASK_GROUPING.get(provider):
            safe_id = indicators[0]["id_string"].replace(".", "-").replace("_", "-")
            job_name = f"qgi-fetch-{safe_id}-{run_id[-12:]}"[:128]
        else:
            safe_group = str(unit["group_key"]).replace(".", "-").replace("_", "-")
            job_name = f"qgi-fetch-{provider.lower()}-{safe_group}-{run_id[-12:]}"[:128]

        container_env = _build_task_env(unit, run_id)
        try:
            response = batch.submit_job(
                jobName=job_name,
                jobQueue=BATCH_JOB_QUEUE,
                jobDefinition=job_definition,
                containerOverrides={"environment": container_env},
            )
            submitted_indicators += unit_size
            submitted_units += 1
            per_provider_counts[provider] = per_provider_counts.get(provider, 0) + unit_size
            logger.debug(
                f"Submitted {provider} unit ({unit_size} indicators, "
                f"group={unit['group_key']}, jobDef={job_definition}): "
                f"{response['jobId']}"
            )
        except Exception as e:  # noqa: BLE001
            logger.error(
                f"Failed to submit Batch job for {provider} unit "
                f"(group={unit['group_key']}, {unit_size} indicators): {e}"
            )
            # Mark every indicator in this failed unit as failed so the
            # counter can be decremented correctly below.
            submit_failures.extend(i["id_string"] for i in indicators)

    logger.info(
        f"Submitted {submitted_indicators}/{n} indicators across "
        f"{submitted_units}/{len(task_units)} task units for run_id={run_id}. "
        f"Indicator-failures: {len(submit_failures)}"
    )

    # If some submissions failed, decrement the counter by that count so
    # it can still reach 0. Otherwise the run hangs forever waiting on
    # jobs that were never submitted. We count INDICATOR failures, not
    # TASK-UNIT failures — a failed FAOSTAT task-unit means N indicators
    # failed to submit.
    if submit_failures:
        counter_table.update_item(
            Key={"run_id": run_id},
            UpdateExpression="ADD pending :neg",
            ExpressionAttributeValues={":neg": Decimal(-len(submit_failures))},
        )
        logger.warning(f"Decremented counter by {len(submit_failures)} for failed submissions")

    return {
        # Dispatched count is in INDICATORS (not task units) — the
        # Step Function checker compares against counter.pending which
        # is seeded in indicators. Keeping the name for backward compat.
        "dispatched": submitted_indicators,
        "total": submitted_indicators,
        # #241 Phase B: task-unit count surfaced separately so the
        # reporter can distinguish "15 indicators in 8 Fargate tasks"
        # from "15 indicators in 15 Fargate tasks".
        "dispatched_task_units": submitted_units,
        # #240 Phase A: per-provider breakdown (indicator counts).
        "per_provider_counts": per_provider_counts,
        # Epoch seconds — checker uses this against DEADMAN_SECONDS to
        # decide whether the run has busted its hard deadline.
        "phase1_started_at": int(time.time()),
        "submit_failures": submit_failures,
        "run_id": run_id,
    }
