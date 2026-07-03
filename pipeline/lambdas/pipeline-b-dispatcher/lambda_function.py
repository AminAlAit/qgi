import boto3
import os
import pandas as pd
from io import BytesIO
import logging
import json
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)
s3_client = boto3.client("s3")
sqs_client = boto3.client("sqs")


def get_country_map(bucket: str) -> dict:
    """
    Loads the countries.csv file from S3 once and returns a name-to-id dictionary.
    """
    try:
        countries_key = "pipeline-A-indicator-extractor/input/countries.csv"
        logger.info(f"Loading countries mapping from s3://{bucket}/{countries_key}")
        countries_obj = s3_client.get_object(Bucket=bucket, Key=countries_key)
        countries_df = pd.read_csv(countries_obj["Body"])
        return {row["name_1"]: row["id"] for _, row in countries_df.iterrows()}
    except Exception as e:
        logger.error(f"FATAL: Failed to load and parse countries mapping file: {e}", exc_info=True)
        raise


def lambda_handler(event, context):
    bucket = os.environ.get("S3_BUCKET")
    input_prefix = os.environ.get("S3_INPUT_PREFIX")
    sqs_queue_url = os.environ.get("SQS_QUEUE_URL")

    if not all([bucket, input_prefix, sqs_queue_url]):
        logger.error("FATAL: Missing one or more environment variables.")
        return {"statusCode": 500, "body": "Internal configuration error."}

    mode = event.get("mode", "test")
    logger.info(f"Running in '{mode}' mode.")

    # --- Purge the queue first for a clean run ---
    if "invoke" in mode:
        try:
            logger.info(f"Purging SQS queue: {sqs_queue_url}")
            sqs_client.purge_queue(QueueUrl=sqs_queue_url)
            logger.info("Purge request sent. Waiting 60s for SQS to clear...")
            time.sleep(60)  # Purging can take up to 60s
        except Exception as e:
            logger.error(f"Failed to purge queue. Continuing, but may have duplicate jobs. Error: {e}")

    country_name_to_id_map = get_country_map(bucket)
    logger.info(f"Successfully loaded mapping for {len(country_name_to_id_map)} countries.")

    jobs_to_submit = []
    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket, Prefix=input_prefix, Delimiter="/")

        for page in pages:
            for prefix in page.get("CommonPrefixes", []):
                indicator_id = prefix.get("Prefix").strip("/").split("/")[-1]
                indicator_key = f"{input_prefix}{indicator_id}/{indicator_id}.parquet"

                try:
                    obj = s3_client.get_object(Bucket=bucket, Key=indicator_key)
                    df = pd.read_parquet(BytesIO(obj["Body"].read()))
                    countries = df["country"].unique()

                    for country_a_name in countries:
                        if country_a_name not in country_name_to_id_map:
                            logger.warning(
                                f"Skipping job for '{country_a_name}' as it was not found in the country mapping file."
                            )
                            continue

                        # Add the job payload to our list
                        jobs_to_submit.append({"indicator_id": indicator_id, "country_a_name": country_a_name})
                except Exception as e:
                    logger.error(f"Could not process indicator {indicator_id}: {e}", exc_info=True)
                    continue
    except Exception as e:
        logger.error(f"Error during S3 scanning: {e}", exc_info=True)
        return {"statusCode": 500, "body": "Failed during S3 scan."}

    logger.info(f"Phase 1 Complete. Collected {len(jobs_to_submit)} total jobs.")

    if "invoke" in mode:
        logger.info("Phase 2: Submitting all jobs to SQS...")
        submitted_count = 0
        batch_entries = []

        for i, job_payload in enumerate(jobs_to_submit):
            entry = {"Id": str(i), "MessageBody": json.dumps(job_payload)}
            batch_entries.append(entry)

            # SQS send_message_batch has a limit of 10 entries
            if len(batch_entries) == 10:
                sqs_client.send_message_batch(QueueUrl=sqs_queue_url, Entries=batch_entries)
                submitted_count += len(batch_entries)
                batch_entries = []

            if mode == "invoke_5" and submitted_count >= 5:
                logger.info("Invoke_5 mode: Reached 5 submissions. Stopping.")
                break

        # Send any remaining entries
        if batch_entries:
            sqs_client.send_message_batch(QueueUrl=sqs_queue_url, Entries=batch_entries)
            submitted_count += len(batch_entries)

        logger.info(f"Phase 2 Complete. Successfully submitted {submitted_count} of {len(jobs_to_submit)} jobs.")
        return {"statusCode": 200, "body": f"Successfully submitted {submitted_count} of {len(jobs_to_submit)} jobs."}

    else:  # This will catch 'test' mode
        logger.info("Phase 2 Skipped. Running in 'test' mode (dry run).")
        return {"statusCode": 200, "body": f"Dry run complete. Collected {len(jobs_to_submit)} jobs."}
