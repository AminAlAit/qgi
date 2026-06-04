"""Silver Harmonizer — cleanses, standardizes country codes, and emits Parquet."""

from __future__ import annotations

import io
import logging
import os
from typing import Any, Dict, List, Optional
import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)


class SilverHarmonizer:
    """Transforms Bronze raw records into Silver partitioned Parquet datasets."""

    def __init__(self, bucket_name: Optional[str] = None, s3_client: Optional[Any] = None) -> None:
        account_id = os.environ.get("AWS_ACCOUNT_ID", "771606957899")
        self.bucket_name = bucket_name or os.environ.get("S3_BUCKET_SILVER", f"qgi-data-lake-{account_id}")
        self.s3_client = s3_client or boto3.client("s3")

    @staticmethod
    def clean_iso3(iso: str) -> str:
        code = str(iso).strip().upper()
        if len(code) == 3 and code.isalpha():
            return code
        return "UNK"

    def harmonize_dataframe(self, df: pd.DataFrame, dedupe_cols: Optional[List[str]] = None) -> pd.DataFrame:
        """Cleans columns, normalizes ISO3, and removes duplicate observations."""
        cleaned = df.copy()
        if "iso3" in cleaned.columns:
            cleaned["iso3"] = cleaned["iso3"].apply(self.clean_iso3)
        elif "country_iso" in cleaned.columns:
            cleaned["iso3"] = cleaned["country_iso"].apply(self.clean_iso3)

        if dedupe_cols:
            existing = [c for c in dedupe_cols if c in cleaned.columns]
            if existing:
                cleaned = cleaned.drop_duplicates(subset=existing, keep="last")

        return cleaned

    def write_parquet(
        self,
        df: pd.DataFrame,
        s3_key: str,
        schema: Optional[pa.Schema] = None,
        compression: str = "snappy",
    ) -> str:
        """Writes a harmonized DataFrame to S3 as an optimized Parquet table."""
        table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)
        buffer = io.BytesIO()
        pq.write_table(table, buffer, compression=compression)
        buffer.seek(0)

        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=s3_key,
            Body=buffer.getvalue(),
            ContentType="application/x-parquet",
        )
        logger.info("Wrote Silver Parquet table to s3://%s/%s (%d rows)", self.bucket_name, s3_key, len(df))
        return f"s3://{self.bucket_name}/{s3_key}"
