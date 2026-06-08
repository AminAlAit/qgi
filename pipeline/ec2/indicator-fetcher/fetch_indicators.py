#!/usr/bin/env python3
"""
EC2 Indicator Fetcher — Phase 1 replacement for Lambda workers.

Fetches all 'process' indicators from the World Bank API sequentially,
writes Parquet to S3, and updates DynamoDB counters. No timeout limit.

Usage (called via SSM Run Command from Step Functions):
    python3 /opt/qgi/fetch_indicators.py --run-id <execution_name> --bucket <bucket> --table <dynamo_table>
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import time

import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import wbgapi as wb
from io import StringIO, BytesIO

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

S3_INPUT_PREFIX = "pipeline-A-indicator-extractor/input"
S3_OUTPUT_PREFIX = "pipeline-A-indicator-extractor/output"
COUNTRIES_CSV_KEY = f"{S3_INPUT_PREFIX}/countries.csv"


REGION = "eu-central-1"


class IndicatorFetcher:
    def __init__(self, bucket, dynamo_table, run_id):
        self.bucket = bucket
        self.run_id = run_id
        self.s3 = boto3.client("s3", region_name=REGION)
        self.dynamodb = boto3.resource("dynamodb", region_name=REGION)
        self.table = self.dynamodb.Table(dynamo_table)
        self.country_mapping = None

    def get_country_mapping(self):
        if self.country_mapping is None:
            logger.info(f"Loading country mapping from s3://{self.bucket}/{COUNTRIES_CSV_KEY}")
            obj = self.s3.get_object(Bucket=self.bucket, Key=COUNTRIES_CSV_KEY)
            df = pd.read_csv(StringIO(obj["Body"].read().decode("utf-8")))
            df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
            if "name_1" in df.columns:
                mapping = {}
                for col in df.columns:
                    if col != "name_1":
                        temp_map = df.dropna(subset=[col]).set_index(col)["name_1"].to_dict()
                        mapping.update(temp_map)
                self.country_mapping = mapping
            else:
                raise ValueError("countries.csv missing 'name_1' column")
        return self.country_mapping

    def get_remote_hash(self, key):
        try:
            response = self.s3.head_object(Bucket=self.bucket, Key=key)
            return response["Metadata"].get("content_hash")
        except Exception:
            return None

    def update_state(self, indicator_id, status):
        try:
            expire_at = int(time.time()) + (30 * 24 * 60 * 60)
            self.table.put_item(
                Item={
                    "run_id": self.run_id,
                    "indicator_id": indicator_id,
                    "status": status,
                    "timestamp": int(time.time()),
                    "expire_at": expire_at,
                }
            )
        except Exception as e:
            logger.error(f"Failed to update DynamoDB for {indicator_id}: {e}")
            raise

    def fetch_with_retry(self, indicator_id, max_attempts=5):
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"Fetching {indicator_id} (Attempt {attempt}/{max_attempts})")
                return wb.data.DataFrame(indicator_id)
            except Exception as e:
                if attempt == max_attempts:
                    logger.error(f"Final attempt failed for {indicator_id}: {e}")
                    raise
                sleep_time = (10 * (2 ** (attempt - 1))) + 2
                logger.warning(f"Error fetching {indicator_id}, retrying in {sleep_time}s: {e}")
                time.sleep(sleep_time)

    def process_one(self, indicator_id):
        logger.info(f"--- Processing {indicator_id} ---")
        try:
            # Fetch
            raw_df = self.fetch_with_retry(indicator_id)
            if raw_df.empty:
                logger.info(f"{indicator_id}: empty response, skipping")
                self.update_state(indicator_id, "SKIPPED")
                return "SKIPPED"

            # Transform
            mapping = self.get_country_mapping()
            df = raw_df.dropna(axis="columns", how="all").copy()
            df["economy"] = df.index
            df_long = pd.melt(df, id_vars=["economy"], var_name="year", value_name="value")
            df_long["year"] = df_long["year"].str.extract(r"(\d+)").astype(int)
            df_long = df_long.rename(columns={"economy": "country"})
            df_long["country"] = df_long["country"].map(mapping).fillna(df_long["country"])
            canonical_names = set(mapping.values())
            df_long = df_long[df_long["country"].isin(canonical_names)]
            final_df = df_long.dropna(subset=["value"]).sort_values(by=["country", "year"])

            # Hash check
            csv_str = final_df.to_csv(index=False)
            new_hash = hashlib.md5(csv_str.encode("utf-8")).hexdigest()
            output_key = f"{S3_OUTPUT_PREFIX}/parquet/{indicator_id}/{indicator_id}.parquet"
            existing_hash = self.get_remote_hash(output_key)

            if existing_hash == new_hash:
                logger.info(f"{indicator_id}: data unchanged (hash match), skipping upload")
                self.update_state(indicator_id, "UNCHANGED")
                return "UNCHANGED"

            # Upload
            logger.info(f"{indicator_id}: data changed, uploading to S3")
            parquet_buffer = BytesIO()
            final_df.to_parquet(parquet_buffer, index=False, engine="pyarrow", compression="snappy")
            self.s3.put_object(
                Bucket=self.bucket, Key=output_key, Body=parquet_buffer.getvalue(), Metadata={"content_hash": new_hash}
            )
            self.update_state(indicator_id, "UPDATED")
            logger.info(f"{indicator_id}: SUCCESS")
            return "UPDATED"

        except Exception as e:
            logger.error(f"{indicator_id}: FAILED — {e}")
            self.update_state(indicator_id, "FAILED")
            return "FAILED"

    def run(self):
        # Load indicator config from S3
        config_key = "indicators/indicators.json"
        logger.info(f"Loading config from s3://{self.bucket}/{config_key}")
        obj = self.s3.get_object(Bucket=self.bucket, Key=config_key)
        config = json.loads(obj["Body"].read().decode("utf-8"))

        indicators = [i for i in config["indicators"] if i["status"] == "process"]
        total = len(indicators)
        logger.info(f"Processing {total} indicators sequentially")

        results = {"UPDATED": 0, "UNCHANGED": 0, "SKIPPED": 0, "FAILED": 0}

        for i, ind in enumerate(indicators, 1):
            ind_id = ind["id_string"]
            logger.info(f"[{i}/{total}] Starting {ind_id}")
            status = self.process_one(ind_id)
            results[status] = results.get(status, 0) + 1
            logger.info(f"[{i}/{total}] {ind_id} → {status}  |  Running totals: {results}")

            # Pause between indicators to be gentle on WB API
            if i < total:
                time.sleep(60)

        logger.info(f"=== COMPLETE === {total} indicators processed: {results}")
        return results


def main():
    parser = argparse.ArgumentParser(description="QGI EC2 Indicator Fetcher")
    parser.add_argument("--run-id", required=True, help="Step Function execution name")
    parser.add_argument("--bucket", required=True, help="S3 data lake bucket name")
    parser.add_argument("--table", default="qgi-indicator-updates", help="DynamoDB tracking table")
    args = parser.parse_args()

    fetcher = IndicatorFetcher(args.bucket, args.table, args.run_id)
    fetcher.run()


if __name__ == "__main__":
    main()
