"""Phase 2 batch checker — polls AWS Batch for in-flight scdi-finder jobs.

Returns {"jobs_running": N} for the Step Function 'Batch Done?' choice state.
"""

import boto3
import os

batch = boto3.client("batch")


def lambda_handler(event, context):
    job_queue = os.environ.get("JOB_QUEUE")

    # Statuses that imply the pipeline is still "working"
    active_statuses = ["SUBMITTED", "PENDING", "RUNNABLE", "STARTING", "RUNNING"]

    total_jobs = 0

    for status in active_statuses:
        # list_jobs returns a summary, maxResults default is 100 which is fine
        # because if we have >0 we just need to know we aren't done.
        response = batch.list_jobs(
            jobQueue=job_queue,
            jobStatus=status,
            maxResults=10,  # We only need to know if count > 0
        )
        count = len(response.get("jobSummaryList", []))
        total_jobs += count

    return {"jobs_running": total_jobs}
