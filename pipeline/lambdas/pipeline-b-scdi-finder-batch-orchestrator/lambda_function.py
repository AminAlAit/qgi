import boto3
import os
import pandas as pd
from io import BytesIO
import logging
import re
import json
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")
batch_client = boto3.client("batch")
lambda_client = boto3.client("lambda")

# 10 threads per worker (50 workers × 10 = 500 concurrent, within Batch API limits)
MAX_WORKERS = 10
MAX_RETRIES = 5
FUNCTION_NAME = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "qgi-pipeline-b-scdi-finder-batch-orchestrator")


def sanitize_for_batch(name: str) -> str:
    name = name.replace(" ", "_").replace(".", "_")
    return re.sub(r"[^a-zA-Z0-9_-]", "", name)


def get_country_map(bucket: str) -> dict:
    countries_key = "pipeline-A-indicator-extractor/input/countries.csv"
    logger.info(f"Loading countries mapping from s3://{bucket}/{countries_key}")
    countries_obj = s3_client.get_object(Bucket=bucket, Key=countries_key)
    countries_df = pd.read_csv(countries_obj["Body"])
    return {row["name_1"]: row["id"] for _, row in countries_df.iterrows()}


def collect_indicators(event, bucket, input_prefix):
    multiple = event.get("indicator_ids")
    single = event.get("indicator_id")

    if multiple:
        logger.info(f"Multi-indicator mode: {len(multiple)} indicators")
        return multiple
    elif single:
        logger.info(f"Single-indicator mode: {single}")
        return [single]
    else:
        logger.info("Full-scan mode: scanning S3 for all indicators...")
        indicators = []
        paginator = s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=input_prefix, Delimiter="/"):
            for prefix in page.get("CommonPrefixes", []):
                ind = prefix.get("Prefix").strip("/").split("/")[-1]
                indicators.append(ind)
        logger.info(f"Found {len(indicators)} indicators via S3 scan")
        return indicators


def build_jobs_for_indicator(indicator_id, bucket, input_prefix, country_map, job_queue, job_definition):
    indicator_key = f"{input_prefix}{indicator_id}/{indicator_id}.parquet"
    try:
        obj = s3_client.get_object(Bucket=bucket, Key=indicator_key)
        df = pd.read_parquet(BytesIO(obj["Body"].read()))
        countries = df["country"].unique()
    except Exception as e:
        logger.error(f"Could not read indicator {indicator_id}: {e}")
        return []

    jobs = []
    for country_a_name in countries:
        country_a_id = country_map.get(country_a_name)
        if not country_a_id:
            continue

        sane_ind = sanitize_for_batch(indicator_id)
        sane_country = sanitize_for_batch(country_a_name)
        jobs.append(
            {
                "jobName": f"scdi-{sane_ind}-{sane_country}"[:128],
                "jobQueue": job_queue,
                "jobDefinition": job_definition,
                "containerOverrides": {
                    "environment": [
                        {"name": "INDICATOR_ID", "value": indicator_id},
                        {"name": "COUNTRY_A_NAME", "value": country_a_name},
                    ]
                },
            }
        )
    return jobs


def submit_one_with_retry(job_params):
    """Submit a single Batch job with exponential backoff on throttling."""
    for attempt in range(MAX_RETRIES):
        try:
            batch_client.submit_job(**job_params)
            return True
        except batch_client.exceptions.ClientException:
            # Non-retryable error
            return False
        except Exception as e:
            err_str = str(e)
            if "TooManyRequestsException" in err_str or "ThrottlingException" in err_str:
                wait = (2**attempt) + random.uniform(0, 1)
                time.sleep(wait)
                continue
            else:
                return False
    return False


def submit_jobs_parallel(jobs):
    """Submit jobs with limited concurrency + per-job exponential backoff."""
    success = 0
    fail = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(submit_one_with_retry, j) for j in jobs]
        for f in as_completed(futures):
            if f.result():
                success += 1
            else:
                fail += 1
    return success, fail


def lambda_handler(event, context):
    bucket = os.environ.get("S3_BUCKET")
    input_prefix = os.environ.get("S3_INPUT_PREFIX")
    job_queue = os.environ.get("BATCH_JOB_QUEUE")
    job_definition = os.environ.get("BATCH_JOB_DEFINITION")

    if not all([bucket, input_prefix, job_queue, job_definition]):
        logger.error("FATAL: Missing environment variables.")
        return {"statusCode": 500, "body": "Internal configuration error."}

    mode = event.get("mode", "test")
    logger.info(f"Running in '{mode}' mode.")

    # ---------------------------------------------------------------
    # Worker mode: receive a single indicator, build + submit its jobs
    # ---------------------------------------------------------------
    if mode == "worker":
        indicator_id = event["indicator_id"]
        # Stagger worker start to avoid thundering herd
        jitter = random.uniform(0, 5)
        time.sleep(jitter)

        country_map = get_country_map(bucket)
        jobs = build_jobs_for_indicator(indicator_id, bucket, input_prefix, country_map, job_queue, job_definition)
        logger.info(f"Worker [{indicator_id}]: submitting {len(jobs)} jobs")
        success, fail = submit_jobs_parallel(jobs)
        msg = f"Worker [{indicator_id}]: {success} submitted, {fail} failed"
        logger.info(msg)
        return {"statusCode": 200, "body": msg}

    # ---------------------------------------------------------------
    # Coordinator path
    # ---------------------------------------------------------------
    indicators = collect_indicators(event, bucket, input_prefix)
    logger.info(f"Found {len(indicators)} indicator(s) to process.")

    # --- test mode: dry run ---
    if mode == "test":
        country_map = get_country_map(bucket)
        total_jobs = 0
        for ind in indicators:
            jobs = build_jobs_for_indicator(ind, bucket, input_prefix, country_map, job_queue, job_definition)
            total_jobs += len(jobs)
        return {"statusCode": 200, "body": f"Dry run complete. Collected {total_jobs} jobs."}

    # --- debug mode: submit limited count ---
    if mode == "debug":
        country_map = get_country_map(bucket)
        num = event.get("number_of_countries_to_process", 1)
        all_jobs = []
        for ind in indicators:
            all_jobs.extend(build_jobs_for_indicator(ind, bucket, input_prefix, country_map, job_queue, job_definition))
        submitted = 0
        failed = 0
        for j in all_jobs[:num]:
            j["jobName"] = "debug-" + j["jobName"]
            try:
                batch_client.submit_job(**j)
                submitted += 1
            except Exception:
                # T11 #304 MEDIUM fix (2026-04-19): was `pass`. Log so ops
                # can see when debug submissions are silently failing.
                logger.exception(f"debug batch.submit_job failed for {j.get('jobName')}")
                failed += 1
        return {"statusCode": 200, "body": f"Successfully submitted {submitted} debug jobs ({failed} failed)."}

    # --- invoke_5 mode: submit exactly 5 ---
    if mode == "invoke_5":
        country_map = get_country_map(bucket)
        all_jobs = []
        for ind in indicators:
            all_jobs.extend(build_jobs_for_indicator(ind, bucket, input_prefix, country_map, job_queue, job_definition))
        submitted = 0
        failed = 0
        for j in all_jobs[:5]:
            try:
                batch_client.submit_job(**j)
                submitted += 1
            except Exception:
                # T11 #304 MEDIUM fix: log so ops see silent failures.
                logger.exception(f"invoke_5 batch.submit_job failed for {j.get('jobName')}")
                failed += 1
        return {
            "statusCode": 200,
            "body": f"Successfully submitted {submitted} of {len(all_jobs)} jobs ({failed} failed).",
        }

    # --- invoke mode: FAN-OUT — one worker Lambda per indicator ---
    if "invoke" in mode:
        workers_launched = 0
        for indicator_id in indicators:
            payload = {"mode": "worker", "indicator_id": indicator_id}
            try:
                lambda_client.invoke(
                    FunctionName=FUNCTION_NAME, InvocationType="Event", Payload=json.dumps(payload).encode()
                )
                workers_launched += 1
            except Exception as e:
                logger.error(f"Failed to invoke worker for {indicator_id}: {e}")

        msg = f"Successfully submitted {workers_launched} of {len(indicators)} indicator workers."
        logger.info(msg)
        return {"statusCode": 200, "body": msg}

    return {"statusCode": 400, "body": f"Unknown mode: {mode}"}
