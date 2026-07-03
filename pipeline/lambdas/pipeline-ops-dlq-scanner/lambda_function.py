import boto3
import logging
import os
import json

# T11 #304 MEDIUM fix (2026-04-19): was using bare print(). Replaced with
# standard logger so output is ingested by CloudWatch Logs + searchable by
# log level.
logger = logging.getLogger()
logger.setLevel(logging.INFO)

sqs = boto3.client("sqs")
sns = boto3.client("sns")

# Environment Variables:
# DLQ_URLS: Comma-separated list of DLQ URLs
# SNS_TOPIC_ARN: ARN of your email topic


def lambda_handler(event, context):
    dlq_urls = os.environ.get("DLQ_URLS", "").split(",")
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN")

    dlq_urls = [q.strip() for q in dlq_urls if q.strip()]
    failed_queues = {}

    for url in dlq_urls:
        try:
            # Get approximate count
            response = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages"])
            count = int(response["Attributes"]["ApproximateNumberOfMessages"])
            if count > 0:
                failed_queues[url] = count
        except Exception as e:
            logger.exception(f"Error checking DLQ {url}")

    if failed_queues:
        message = "ALERT: QGI Pipeline Failure Detected.\n\nMessages found in Dead Letter Queues:\n"
        for url, count in failed_queues.items():
            message += f"- {url.split('/')[-1]}: {count} messages\n"

        sns.publish(TopicArn=sns_topic_arn, Subject="[QGI ALERT] DLQ Messages Detected", Message=message)
        return {"status": "Failed", "details": failed_queues}

    else:
        # Optional: Send "Success" email if it's the end of the month
        sns.publish(
            TopicArn=sns_topic_arn,
            Subject="[QGI SUCCESS] Monthly Run Complete",
            Message="All pipelines finished. Zero messages in DLQs.",
        )
        return {"status": "Success", "message": "No DLQ messages."}
