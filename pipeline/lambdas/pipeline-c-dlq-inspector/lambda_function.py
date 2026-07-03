import boto3
import logging
import os
import csv
from io import StringIO
import uuid
import time
import json
import re

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Boto3 clients
athena_client = boto3.client("athena")
s3_client = boto3.client("s3")
sqs_client = boto3.client("sqs")


def get_processed_country_ids_from_s3(bucket, prefix):
    """Scans an S3 prefix for Hive-style partitions and returns the partition values."""
    if not prefix.endswith("/"):
        prefix += "/"
    logger.info(f"Scanning S3 for processed country IDs in: s3://{bucket}/{prefix}")

    processed_ids = set()
    paginator = s3_client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/")

    for page in pages:
        for common_prefix in page.get("CommonPrefixes", []):
            folder_name = common_prefix.get("Prefix").replace(prefix, "")
            match = re.search(r"country_a_id=(\d+)", folder_name)
            if match:
                processed_ids.add(match.group(1))

    logger.info(f"Found {len(processed_ids)} successfully processed country IDs in S3.")
    return processed_ids


def run_athena_query(query_string, workgroup, db_name, output_location):
    """Executes a SELECT query and returns the S3 path to the results."""
    logger.info(f"Executing Athena query: \n{query_string}")
    result_output_location = f"{output_location.rstrip('/')}/dlq_inspector_results/{uuid.uuid4()}"

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
                return f"{result_output_location}/{query_execution_id}.csv"
            else:
                error_message = stats["QueryExecution"]["Status"].get("StateChangeReason", "Unknown error")
                raise Exception(f"Query {query_execution_id} failed: {error_message}")
        time.sleep(2)


def lambda_handler(event, context):
    DLQ_URL = os.environ["DLQ_URL"]
    S3_BUCKET = os.environ["S3_BUCKET"]
    DB_NAME = os.environ["ATHENA_DATABASE"]
    COUNTRIES_NAMES_TABLE = os.environ["COUNTRIES_NAMES_TABLE"]
    ATHENA_WORKGROUP = os.environ["ATHENA_WORKGROUP"]
    S3_OUTPUT_LOCATION = os.environ["S3_OUTPUT_LOCATION"]

    PATTERNS_S3_PREFIX = "pipeline-C-pattern-synthesizer/output/data/"

    # 1. Get all country IDs from the DLQ
    failed_country_ids = set()
    logger.info(f"Polling for messages in DLQ: {DLQ_URL}")
    while True:
        response = sqs_client.receive_message(
            QueueUrl=DLQ_URL, MaxNumberOfMessages=10, WaitTimeSeconds=2, VisibilityTimeout=30
        )
        messages = response.get("Messages", [])
        if not messages:
            break
        for msg in messages:
            if msg["Body"].isdigit():
                failed_country_ids.add(msg["Body"])

    if not failed_country_ids:
        logger.info("DLQ is empty.")
    else:
        logger.info(f"Found {len(failed_country_ids)} unique country IDs in DLQ.")

    # 2. Get all country IDs that have successfully created folders in S3
    processed_country_ids = get_processed_country_ids_from_s3(S3_BUCKET, PATTERNS_S3_PREFIX)

    # 3. Find the difference: IDs in DLQ but NOT in S3
    truly_failed_ids = list(failed_country_ids - processed_country_ids)

    # --- LOGIC BRANCH: Report on failures OR provide a progress update ---
    if truly_failed_ids:
        # --- FAILURE MODE ---
        logger.info(
            f"Identified {len(truly_failed_ids)} countries that are in the DLQ and are missing S3 data: {truly_failed_ids}"
        )
        # T11 #304 HIGH fix (2026-04-19): SQS DLQ messages are
        # attacker-controlled. Validate each country_id is pure-digit
        # before interpolating into Athena SQL to close the injection path.
        safe_ids = [i for i in truly_failed_ids if str(i).isdigit()]
        if len(safe_ids) != len(truly_failed_ids):
            logger.warning(
                f"Rejected {len(truly_failed_ids) - len(safe_ids)} non-digit country_ids from DLQ: "
                f"{[i for i in truly_failed_ids if not str(i).isdigit()]}"
            )
        if not safe_ids:
            logger.info("No valid country_ids to look up after sanitization.")
            return {"statusCode": 200, "body": json.dumps({})}
        ids_string = ", ".join(safe_ids)
        lookup_query = f"SELECT id, name_1 FROM {DB_NAME}.{COUNTRIES_NAMES_TABLE} WHERE id IN ({ids_string})"
        result_path = run_athena_query(lookup_query, ATHENA_WORKGROUP, DB_NAME, S3_OUTPUT_LOCATION)
        result_key = result_path.replace(f"s3://{S3_BUCKET}/", "")
        obj = s3_client.get_object(Bucket=S3_BUCKET, Key=result_key)
        body = obj["Body"].read().decode("utf-8")
        csv_reader = csv.reader(StringIO(body))
        next(csv_reader)
        failed_countries_map = {row[0]: row[1] for row in csv_reader if row}

        logger.info("--- TRULY FAILED COUNTRIES REPORT (in DLQ and missing S3 data) ---")
        logger.info(json.dumps(failed_countries_map, indent=2))
        logger.info("----------------------------------------------------------------")
        return {"statusCode": 200, "body": json.dumps(failed_countries_map)}

    else:
        # --- PROGRESS REPORT MODE ---
        logger.info("No truly failed countries found. Checking overall pipeline progress...")

        # 4. Get the complete list of all countries from the master table
        # This uses the robust Parquet-formatted country mapping table as the source of truth.
        all_countries_query = f"SELECT id FROM {DB_NAME}.{COUNTRIES_NAMES_TABLE}"
        result_path = run_athena_query(all_countries_query, ATHENA_WORKGROUP, DB_NAME, S3_OUTPUT_LOCATION)
        result_key = result_path.replace(f"s3://{S3_BUCKET}/", "")
        obj = s3_client.get_object(Bucket=S3_BUCKET, Key=result_key)
        body = obj["Body"].read().decode("utf-8")
        csv_reader = csv.reader(StringIO(body))
        next(csv_reader)
        all_country_ids = {row[0] for row in csv_reader if row and row[0]}

        # 5. Find the unprocessed countries
        unprocessed_ids = list(all_country_ids - processed_country_ids)

        if not unprocessed_ids:
            logger.info("--- PIPELINE COMPLETE ---")
            logger.info(f"All {len(all_country_ids)} countries have been successfully processed.")
            logger.info("-------------------------")
            return {"statusCode": 200, "body": "Pipeline run is complete."}

        # 6. Look up names for the unprocessed countries and report
        logger.info(f"Found {len(unprocessed_ids)} countries remaining to be processed.")
        # T11 #304 HIGH fix: same digit-only allowlist for the unprocessed
        # branch. `unprocessed_ids` derives from set difference with the
        # DLQ-derived failed set, so attacker input can still reach here.
        safe_ids = [i for i in unprocessed_ids if str(i).isdigit()]
        if len(safe_ids) != len(unprocessed_ids):
            logger.warning(
                f"Rejected {len(unprocessed_ids) - len(safe_ids)} non-digit country_ids: "
                f"{[i for i in unprocessed_ids if not str(i).isdigit()]}"
            )
        if not safe_ids:
            logger.info("No valid country_ids to look up after sanitization.")
            return {"statusCode": 200, "body": "All unprocessed ids were non-digit; nothing to report."}
        ids_string = ", ".join(safe_ids)
        lookup_query = f"SELECT id, name_1 FROM {DB_NAME}.{COUNTRIES_NAMES_TABLE} WHERE id IN ({ids_string})"
        result_path = run_athena_query(lookup_query, ATHENA_WORKGROUP, DB_NAME, S3_OUTPUT_LOCATION)
        result_key = result_path.replace(f"s3://{S3_BUCKET}/", "")
        obj = s3_client.get_object(Bucket=S3_BUCKET, Key=result_key)
        body = obj["Body"].read().decode("utf-8")
        csv_reader = csv.reader(StringIO(body))
        next(csv_reader)
        unprocessed_countries_map = {row[0]: row[1] for row in csv_reader if row}

        logger.info(f"--- UNPROCESSED COUNTRIES REPORT ({len(unprocessed_ids)} remaining) ---")
        logger.info(json.dumps(unprocessed_countries_map, indent=2))
        logger.info("---------------------------------------------------------")
        return {"statusCode": 200, "body": json.dumps(unprocessed_countries_map)}
