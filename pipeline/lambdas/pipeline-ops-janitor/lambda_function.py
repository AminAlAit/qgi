import boto3
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)
sqs = boto3.client("sqs")


def lambda_handler(event, context):
    queue_urls = os.environ.get("QUEUE_URLS", "").split(",")

    # Clean up whitespace
    queue_urls = [q.strip() for q in queue_urls if q.strip()]

    if not queue_urls:
        logger.warning("No queues configured to purge.")
        return {"status": "Skipped"}

    purged_count = 0
    for url in queue_urls:
        try:
            logger.info(f"Purging queue: {url}")
            sqs.purge_queue(QueueUrl=url)
            purged_count += 1
        except sqs.exceptions.QueueDoesNotExist:
            logger.error(f"Queue does not exist: {url}")
        except sqs.exceptions.PurgeQueueInProgress:
            logger.warning(f"Purge already in progress for: {url}")
        except Exception as e:
            logger.error(f"Failed to purge {url}: {str(e)}")

    return {"status": "Success", "queues_purged": purged_count}
