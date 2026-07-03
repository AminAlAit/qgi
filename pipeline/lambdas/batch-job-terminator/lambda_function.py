import boto3
import os
import logging
import json
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger()
logger.setLevel(logging.INFO)

batch_client = boto3.client("batch")
s3_client = boto3.client("s3")

MAX_WORKERS = 50
CHUNK_SIZE = 500

CANCEL_STATUSES = ["SUBMITTED", "PENDING", "RUNNABLE"]
TERMINATE_STATUSES = ["STARTING", "RUNNING"]


def lambda_handler(event, context):
    """
    Three modes, orchestrated by Step Functions:

    1. mode=list   — Collect all active job IDs, write chunks to S3, return metadata
    2. mode=kill   — Read a chunk from S3 by index, kill jobs in parallel
    3. mode=report — Summarize results
    """
    mode = event.get("mode", "list")
    job_queue = os.environ.get("BATCH_JOB_QUEUE")
    reason = event.get("reason", "Terminated by batch-job-terminator.")
    bucket = event.get("bucket", "")
    run_id = event.get("run_id", "default")

    if not job_queue:
        raise ValueError("BATCH_JOB_QUEUE environment variable not set.")

    if mode == "list":
        return handle_list(job_queue, bucket, run_id)
    elif mode == "kill":
        chunk_index = event.get("chunk_index", 0)
        return handle_kill(bucket, run_id, chunk_index, reason)
    elif mode == "report":
        return handle_report(job_queue)
    else:
        raise ValueError(f"Unknown mode: {mode}")


def handle_list(job_queue, bucket, run_id):
    """List all active jobs, write chunks to S3, return chunk count."""
    all_jobs = []

    for status in CANCEL_STATUSES:
        try:
            paginator = batch_client.get_paginator("list_jobs")
            for page in paginator.paginate(jobQueue=job_queue, jobStatus=status):
                for job in page.get("jobSummaryList", []):
                    all_jobs.append({"id": job["jobId"], "cancel": True})
        except Exception as e:
            logger.error(f"Failed to list {status} jobs: {e}")

    for status in TERMINATE_STATUSES:
        try:
            paginator = batch_client.get_paginator("list_jobs")
            for page in paginator.paginate(jobQueue=job_queue, jobStatus=status):
                for job in page.get("jobSummaryList", []):
                    all_jobs.append({"id": job["jobId"], "cancel": False})
        except Exception as e:
            logger.error(f"Failed to list {status} jobs: {e}")

    total = len(all_jobs)
    logger.info(f"Found {total} active jobs.")

    if total == 0:
        return {"total_jobs": 0, "total_chunks": 0, "chunk_indices": []}

    # Write chunks to S3
    chunk_indices = []
    for i in range(0, total, CHUNK_SIZE):
        chunk_idx = i // CHUNK_SIZE
        chunk = all_jobs[i : i + CHUNK_SIZE]
        key = f"_terminator/{run_id}/chunk_{chunk_idx}.json"
        s3_client.put_object(Bucket=bucket, Key=key, Body=json.dumps(chunk).encode())
        chunk_indices.append({"chunk_index": chunk_idx})

    logger.info(f"Wrote {len(chunk_indices)} chunks to S3.")

    return {"total_jobs": total, "total_chunks": len(chunk_indices), "chunk_indices": chunk_indices}


def handle_kill(bucket, run_id, chunk_index, reason):
    """Read a chunk from S3 and kill all jobs in parallel."""
    key = f"_terminator/{run_id}/chunk_{chunk_index}.json"
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    jobs = json.loads(obj["Body"].read())

    logger.info(f"Chunk {chunk_index}: killing {len(jobs)} jobs")

    success = 0
    fail = 0

    def kill_one(job):
        try:
            if job["cancel"]:
                batch_client.cancel_job(jobId=job["id"], reason=reason)
            else:
                batch_client.terminate_job(jobId=job["id"], reason=reason)
            return True
        except Exception as exc:  # noqa: BLE001 — log-and-continue per #373
            logger.warning(f"Failed to {'cancel' if job.get('cancel') else 'terminate'} job {job.get('id')!r}: {exc}")
            return False

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(kill_one, j) for j in jobs]
        for f in as_completed(futures):
            if f.result():
                success += 1
            else:
                fail += 1

    logger.info(f"Chunk {chunk_index}: {success} killed, {fail} failed")
    return {"chunk_index": chunk_index, "killed": success, "failed": fail}


def handle_report(job_queue):
    """Check remaining active jobs."""
    remaining = 0
    for status in CANCEL_STATUSES + TERMINATE_STATUSES:
        try:
            paginator = batch_client.get_paginator("list_jobs")
            for page in paginator.paginate(jobQueue=job_queue, jobStatus=status):
                remaining += len(page.get("jobSummaryList", []))
        except Exception as exc:  # noqa: BLE001 — log-and-continue per #373
            logger.warning(f"Failed to list jobs in status {status!r} during report: {exc}")
    return {"remaining_jobs": remaining}
