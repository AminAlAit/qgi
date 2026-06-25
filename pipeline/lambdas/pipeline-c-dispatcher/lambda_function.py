import boto3
import logging
import os
import csv
from io import StringIO
import uuid
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

athena_client = boto3.client("athena")
s3_client = boto3.client("s3")
sqs_client = boto3.client("sqs")


def run_athena_query(query_string, workgroup, db_name, output_location, expects_result_path=False, context=None):
    """Executes a query, waits for it to succeed, and optionally returns the result path.

    #919: when a Lambda `context` is passed, the poll loop aborts (TimeoutError) once
    <30s of budget remains rather than being killed mid-poll (which would leave the
    query running + the dispatcher in a broken intermediate state)."""
    logger.info(f"Executing query: \n{query_string}")
    result_output_location = f"{output_location.rstrip('/')}/dispatcher_query_results/{uuid.uuid4()}"

    query_execution = athena_client.start_query_execution(
        QueryString=query_string,
        QueryExecutionContext={"Database": db_name},
        ResultConfiguration={"OutputLocation": result_output_location},
        WorkGroup=workgroup,
    )
    query_execution_id = query_execution["QueryExecutionId"]

    while True:
        stats = athena_client.get_query_execution(QueryExecutionId=query_execution_id)
        status = stats["QueryExecution"]["Status"]["State"]
        if status in ("SUCCEEDED", "FAILED", "CANCELLED"):
            if status == "SUCCEEDED":
                logger.info(f"Query {query_execution_id} succeeded.")
                if expects_result_path:
                    # workgroup has enforce_workgroup_configuration=true, so results always land at
                    # {output_location}/{query_execution_id}.csv regardless of what we requested
                    return f"{output_location.rstrip('/')}/{query_execution_id}.csv"
                return None
            else:
                error_message = stats["QueryExecution"]["Status"].get("StateChangeReason", "Unknown error")
                raise Exception(f"Query {query_execution_id} failed: {error_message}")
        if context is not None and context.get_remaining_time_in_millis() < 30_000:
            try:
                athena_client.stop_query_execution(QueryExecutionId=query_execution_id)
            except Exception:  # noqa: BLE001 — best-effort cancel; never mask the timeout
                logger.warning("Could not stop runaway query %s on budget abort", query_execution_id)
            raise TimeoutError(f"Aborting Athena poll for {query_execution_id}: <30s Lambda budget left.")
        time.sleep(5)


def clean_s3_prefix(bucket, prefix):
    if not prefix.endswith("/"):
        prefix += "/"
    logger.info(f"Cleaning S3 prefix: s3://{bucket}/{prefix}")
    paginator = s3_client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

    keys_to_delete = [{"Key": obj["Key"]} for page in pages for obj in page.get("Contents", [])]
    if keys_to_delete:
        for i in range(0, len(keys_to_delete), 1000):
            s3_client.delete_objects(Bucket=bucket, Delete={"Objects": keys_to_delete[i : i + 1000]})


def lambda_handler(event, context):
    S3_BUCKET = os.environ["S3_BUCKET"]
    DB_NAME = os.environ["ATHENA_DATABASE"]
    COUNTRIES_NAMES_TABLE = os.environ["COUNTRIES_NAMES_TABLE"]
    ATHENA_WORKGROUP = os.environ["ATHENA_WORKGROUP"]
    S3_OUTPUT_LOCATION = os.environ["S3_OUTPUT_LOCATION"]
    SQS_QUEUE_URL = os.environ["SQS_QUEUE_URL"]
    COMPLETION_TABLE = os.environ.get("COMPLETION_TABLE")
    SCDIS_TABLE = os.environ.get("SCDIS_TABLE", "scdis")
    RUN_ID = event.get("run_id", "unknown")

    PATTERNS_TABLE_NAME = "patterns"
    PATTERNS_S3_LOCATION = f"s3://{S3_BUCKET}/pipeline-C-pattern-synthesizer/output/data/"

    if event.get("action") == "start" or event.get("action") == "start_sample":
        logger.info("--- DISPATCHER MODE: Starting Pipeline C ---")

        # 1. Get list of country IDs that actually have SCDIs (not all 261 countries).
        #    Dispatching all countries caused 200+ empty INSERTs and the DynamoDB write
        #    burst that triggered the counter bug fixed in #108.
        countries_query = f"SELECT DISTINCT country_a_id FROM {DB_NAME}.{SCDIS_TABLE}"
        result_path = run_athena_query(
            countries_query, ATHENA_WORKGROUP, DB_NAME, S3_OUTPUT_LOCATION, expects_result_path=True, context=context
        )
        result_key = result_path.replace(f"s3://{S3_BUCKET}/", "")
        obj = s3_client.get_object(Bucket=S3_BUCKET, Key=result_key)
        body = obj["Body"].read().decode("utf-8")
        csv_reader = csv.reader(StringIO(body))
        header = next(csv_reader)
        # T11 #304 HIGH fix (2026-04-19): previously `sorted(..., key=int)`
        # could crash Phase 4 dispatch silently if any row had non-digit
        # content (blank line, header duplicate, unexpected string). Guard
        # with try/except ValueError + log-and-drop rows that don't parse.
        raw_ids = [row[0] for row in csv_reader if row and row[0]]
        country_ids = []
        dropped = []
        for rid in raw_ids:
            try:
                _ = int(rid)
                country_ids.append(rid)
            except ValueError:
                dropped.append(rid)
        if dropped:
            logger.warning(f"Dropped {len(dropped)} non-numeric country_ids from Athena result: {dropped[:10]}...")
        country_ids = sorted(country_ids, key=int)
        logger.info(f"Found {len(country_ids)} country IDs to dispatch.")

        logger.info("Cleaning output locations and dropping old tables...")
        clean_s3_prefix(S3_BUCKET, PATTERNS_S3_LOCATION.replace(f"s3://{S3_BUCKET}/", ""))
        run_athena_query(
            f"DROP TABLE IF EXISTS `{DB_NAME}`.`{PATTERNS_TABLE_NAME}`;",
            ATHENA_WORKGROUP,
            DB_NAME,
            S3_OUTPUT_LOCATION,
            context=context,
        )

        # Create the main patterns table (WITH pattern_id, WITHOUT indicator_ids)
        logger.info(f"Creating shell table: {PATTERNS_TABLE_NAME}")
        # NOTE: this column list MUST match the SELECT column order emitted
        # by pipeline-c-worker, including the partition column at the end.
        # History of regressions:
        #   #108 — pipeline-c-worker added pattern_tier (#128) but this
        #          dispatcher's CREATE TABLE wasn't updated → Phase C stall,
        #          every INSERT failed with TYPE_MISMATCH, no counter
        #          increments, infinite retries.
        #   #512 — pipeline-c-worker added contains_predicted (#461) and
        #          qgi-infra/modules/storage was updated, but this
        #          dispatcher was missed again → identical symptom.
        # The schema-parity test in
        # tests/unit/pipeline-c-dispatcher/test_dispatcher_worker_schema_parity.py
        # now fails CI if these two column lists ever drift again.
        create_patterns_query = f"""
        CREATE EXTERNAL TABLE `{DB_NAME}`.`{PATTERNS_TABLE_NAME}` (
          `pattern_id` string,
          `country_b_id` smallint,
          `length` smallint,
          `start_year_a` smallint,
          `start_year_b` smallint,
          `indicator_count` bigint,
          `avg_correlation` double,
          `pattern_power_score` double,
          `indicator_numeric_ids` array<smallint>,
          `pattern_tier` string,
          `contains_predicted` boolean
        )
        PARTITIONED BY (`country_a_id` smallint)
        STORED AS PARQUET
        LOCATION '{PATTERNS_S3_LOCATION}'
        """
        run_athena_query(create_patterns_query, ATHENA_WORKGROUP, DB_NAME, S3_OUTPUT_LOCATION, context=context)

        logger.info("Waiting for 10 seconds for Glue Catalog propagation...")
        time.sleep(10)

        # Purge queue (remains unchanged)
        logger.info(f"Purging main SQS queue: {SQS_QUEUE_URL}")
        sqs_client.purge_queue(QueueUrl=SQS_QUEUE_URL)
        time.sleep(5)

        # 3. Dispatch messages to SQS
        # T11 #304 HIGH fix (2026-04-19): use an explicit counter that's
        # initialized to 0 so `dispatched_count` is always bound even when
        # `country_ids` is empty — previously relied on `enumerate` binding
        # `count` and would NameError out on an empty list.
        import json as _json

        dispatched = 0
        for count, country_id in enumerate(country_ids):
            sqs_client.send_message(
                QueueUrl=SQS_QUEUE_URL,
                MessageBody=_json.dumps({"country_id": country_id, "run_id": RUN_ID}),
            )
            dispatched = count + 1
            logger.info(f"Dispatching country ID {country_id} to the SQS queue.")
            if dispatched % 10 == 0:
                logger.info(f"Dispatched {dispatched} countries to the SQS queue.")
            if event.get("action") == "start_sample":
                if count > 3:
                    break

        dispatched_count = dispatched if event.get("action") == "start_sample" else len(country_ids)
        logger.info(f"Successfully dispatched {dispatched_count} countries to the SQS queue.")

        # Write completion counter so c-checker can poll without a hard wait
        if COMPLETION_TABLE:
            boto3.resource("dynamodb").Table(COMPLETION_TABLE).update_item(
                Key={"run_id": RUN_ID},
                UpdateExpression="SET total_c = :t, processed_c = if_not_exists(processed_c, :z), expires_at = :e",
                ExpressionAttributeValues={
                    ":t": dispatched_count,
                    ":z": 0,
                    ":e": int(time.time()) + 7 * 24 * 3600,
                },
            )

        return {
            "statusCode": 200,
            "dispatched_count": dispatched_count,
            "body": f"Dispatched {dispatched_count} countries.",
        }
    else:
        logger.warning("Dispatcher invoked without 'action: start'. No action taken.")
        return {"statusCode": 400, "body": "Invalid invocation event."}
