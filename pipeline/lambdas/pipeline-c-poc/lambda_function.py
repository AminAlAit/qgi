import time
import boto3
import logging
import os
import csv
import json
from io import StringIO
import uuid

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Boto3 clients
athena_client = boto3.client("athena")
s3_client = boto3.client("s3")
sqs_client = boto3.client("sqs")
lambda_client = boto3.client("lambda")


def run_athena_query(query_string, workgroup, db_name, output_location, expects_result_path=False):
    """Executes a query, waits for it to succeed, and optionally returns the result path."""
    logger.info(f"Executing query: \n{query_string}")

    # Each query needs a unique output location for its metadata
    result_output_location = f"{output_location.rstrip('/')}/query_results/{uuid.uuid4()}"

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
                    # Return the path to the actual result file
                    return f"{result_output_location}/{query_execution_id}.csv"
                return None  # For DDL/DML queries
            else:
                error_message = stats["QueryExecution"]["Status"].get("StateChangeReason", "Unknown error")
                raise Exception(f"Query {query_execution_id} failed: {error_message}")
        time.sleep(5)


def clean_s3_prefix(bucket, prefix):
    """Deletes all objects under a given S3 prefix."""
    if not prefix.endswith("/"):
        prefix += "/"
    logger.info(f"Cleaning S3 prefix: s3://{bucket}/{prefix}")
    paginator = s3_client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

    keys_to_delete = [{"Key": obj["Key"]} for page in pages for obj in page.get("Contents", [])]
    if keys_to_delete:
        # S3 delete_objects has a limit of 1000 keys per request
        for i in range(0, len(keys_to_delete), 1000):
            s3_client.delete_objects(Bucket=bucket, Delete={"Objects": keys_to_delete[i : i + 1000]})
            logger.info(f"Deleted {len(keys_to_delete[i : i + 1000])} objects from S3.")


def lambda_handler(event, context):
    # --- Environment Variable Setup ---
    S3_BUCKET = os.environ["S3_BUCKET"]
    DB_NAME = os.environ["ATHENA_DATABASE"]
    SCDIS_TABLE = os.environ["SCDIS_TABLE"]
    COUNTRIES_TABLE = os.environ["COUNTRIES_TABLE"]
    ATHENA_WORKGROUP = os.environ["ATHENA_WORKGROUP"]
    S3_OUTPUT_LOCATION = os.environ["S3_OUTPUT_LOCATION"]
    SQS_QUEUE_URL = os.environ["SQS_QUEUE_URL"]

    PATTERNS_TABLE_NAME = "patterns"
    PATTERNS_S3_LOCATION = f"s3://{S3_BUCKET}/pipeline-C-pattern-synthesizer/output/data/"  # [cite: 407]

    # --- ROUTER: Determine if running as Dispatcher or Worker ---

    # MODE 1: DISPATCHER (triggered manually with {"action": "start"})
    if event.get("action") == "start":
        logger.info("--- DISPATCHER MODE: Starting Pipeline C ---")

        try:
            # 1. Get the full list of countries to process
            countries_query = f"SELECT DISTINCT country_name FROM {DB_NAME}.{COUNTRIES_TABLE}"
            result_path = run_athena_query(
                countries_query, ATHENA_WORKGROUP, DB_NAME, S3_OUTPUT_LOCATION, expects_result_path=True
            )

            result_key = result_path.replace(f"s3://{S3_BUCKET}/", "")
            obj = s3_client.get_object(Bucket=S3_BUCKET, Key=result_key)
            body = obj["Body"].read().decode("utf-8")
            # Skip header row with [1:]
            # The 'if row' ensures the row isn't empty, and 'if row[0]' ensures the country name itself isn't an empty string.
            countries_to_process = [row[0] for row in csv.reader(StringIO(body)) if row and row[0]][1:]
            logger.info(f"Found {len(countries_to_process)} countries to dispatch.")

            # 2. Clean up old S3 data and drop the Glue table
            clean_s3_prefix(S3_BUCKET, PATTERNS_S3_LOCATION.replace(f"s3://{S3_BUCKET}/", ""))
            run_athena_query(
                f"DROP TABLE IF EXISTS `{DB_NAME}`.`{PATTERNS_TABLE_NAME}`;",
                ATHENA_WORKGROUP,
                DB_NAME,
                S3_OUTPUT_LOCATION,
            )

            # 3. Create the empty, partitioned shell table for the results
            create_shell_query = f"""
            CREATE EXTERNAL TABLE `{DB_NAME}`.`{PATTERNS_TABLE_NAME}` (
              `country_b_name` string, `length` smallint, `start_year_a` smallint, `start_year_b` smallint,
              `indicator_count` bigint, `avg_correlation` double, `pattern_power_score` double, `country_a_name` string
            )
            PARTITIONED BY (`country_a_id` smallint)
            STORED AS PARQUET LOCATION '{PATTERNS_S3_LOCATION}'
            """
            run_athena_query(create_shell_query, ATHENA_WORKGROUP, DB_NAME, S3_OUTPUT_LOCATION)

            # 4. Send each country name as a separate message to the SQS queue
            for country in countries_to_process:
                sqs_client.send_message(QueueUrl=SQS_QUEUE_URL, MessageBody=country)

            logger.info(f"Successfully dispatched all {len(countries_to_process)} countries to the SQS queue.")
            return {"statusCode": 200, "body": f"Dispatched {len(countries_to_process)} countries."}

        except Exception as e:
            logger.error(f"DISPATCHER FAILED: {e}", exc_info=True)
            raise e

    # MODE 2: WORKER (triggered by SQS)
    elif "Records" in event:
        for record in event["Records"]:
            country = record["body"]
            logger.info(f"--- WORKER MODE: Processing country: {country} ---")

            try:
                insert_query = f"""
                INSERT INTO {DB_NAME}.{PATTERNS_TABLE_NAME}
                SELECT
                    c_b.country_name AS country_b_name, s.length, s.start_year_a, s.start_year_b,
                    COUNT(*) AS indicator_count, AVG(s.correlation) AS avg_correlation,
                    AVG(s.correlation) * CAST(s.length AS double) * COUNT(*) AS pattern_power_score,
                    c_a.country_name, c_a.id AS country_a_id
                FROM {DB_NAME}.{SCDIS_TABLE} AS s
                JOIN {DB_NAME}.{COUNTRIES_TABLE} AS c_a ON s.country_a_id = c_a.id
                JOIN {DB_NAME}.{COUNTRIES_TABLE} AS c_b ON s.country_b_id = c_b.id
                WHERE c_a.country_name = '{country.replace("'", "''")}'
                GROUP BY 
                    c_a.country_name, c_b.country_name, s.length, s.start_year_a, s.start_year_b, c_a.id
                HAVING COUNT(*) > 1
                """
                run_athena_query(insert_query, ATHENA_WORKGROUP, DB_NAME, S3_OUTPUT_LOCATION)

            except Exception as e:
                logger.error(f"WORKER FAILED for country '{country}': {e}", exc_info=True)
                # Re-raise the exception to make the message visible again in SQS for a retry
                raise e

        return {"statusCode": 200, "body": "Processed SQS messages successfully."}

    else:
        logger.warning(
            "Lambda invoked without a valid event trigger ('action: start' or SQS Records). No action taken."
        )
        return {"statusCode": 400, "body": "Invalid invocation event."}
