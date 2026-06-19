"""Bronze Partition Writer — persists raw ingested JSONL/NDJSON records to partitioned S3 prefixes."""

from __future__ import annotations

import gzip
import io
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import boto3

logger = logging.getLogger(__name__)


class BronzePartitionWriter:
    """Manages raw payload writes into the Bronze layer of the S3 data lake."""

    def __init__(self, bucket_name: Optional[str] = None, s3_client: Optional[Any] = None) -> None:
        account_id = os.environ.get("AWS_ACCOUNT_ID", "771606957899")
        self.bucket_name = bucket_name or os.environ.get("S3_BUCKET_BRONZE", f"qgi-data-lake-{account_id}")
        self.s3_client = s3_client or boto3.client("s3")

    def build_partition_key(
        self, source: str, event_timestamp: Optional[datetime] = None, filename: str = "data.jsonl.gz"
    ) -> str:
        ts = event_timestamp or datetime.now(timezone.utc)
        year_str = f"year={ts.year:04d}"
        month_str = f"month={ts.month:02d}"
        day_str = f"day={ts.day:02d}"
        return f"bronze/raw/{source}/{year_str}/{month_str}/{day_str}/{filename}"

    def write_records(
        self,
        source: str,
        records: List[Dict[str, Any]],
        event_timestamp: Optional[datetime] = None,
        compress: bool = True,
    ) -> str:
        """Serializes raw dict records and uploads to partitioned S3 Bronze prefix."""
        if not records:
            logger.info("No records to write for source %s", source)
            return ""

        ts = event_timestamp or datetime.now(timezone.utc)
        filename = f"batch_{int(ts.timestamp())}.jsonl.gz" if compress else f"batch_{int(ts.timestamp())}.jsonl"
        s3_key = self.build_partition_key(source, ts, filename)

        buffer = io.BytesIO()
        if compress:
            with gzip.GzipFile(fileobj=buffer, mode="wb") as gz:
                for rec in records:
                    line = (json.dumps(rec, default=str) + "\n").encode("utf-8")
                    gz.write(line)
        else:
            for rec in records:
                line = (json.dumps(rec, default=str) + "\n").encode("utf-8")
                buffer.write(line)

        buffer.seek(0)
        content_type = "application/gzip" if compress else "application/x-ndjson"
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=s3_key,
            Body=buffer.getvalue(),
            ContentType=content_type,
            Metadata={"source": source, "record_count": str(len(records))},
        )
        logger.info("Wrote %d records to s3://%s/%s", len(records), self.bucket_name, s3_key)
        return f"s3://{self.bucket_name}/{s3_key}"
