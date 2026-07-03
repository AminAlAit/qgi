import os
import json
import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple
from io import BytesIO
from concurrent.futures import ProcessPoolExecutor, as_completed

# --- Libraries from Lambda Layers ---
import boto3
import pandas as pd
import numpy as np
from scipy import signal
import psutil

# --- Global Configuration ---

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# These are set by the Lambda Environment Variables
S3_BUCKET = os.environ.get("S3_BUCKET")
S3_INPUT_PREFIX = os.environ.get("S3_INPUT_PREFIX")
S3_OUTPUT_PREFIX = os.environ.get("S3_OUTPUT_PREFIX")
MIN_LENGTH = int(os.environ.get("MIN_LENGTH", 3))
CORRELATION_THRESHOLD = float(os.environ.get("CORRELATION_THRESHOLD", 0.5))

s3_client = boto3.client("s3")

# These will be set dynamically by the handler
INDICATOR_ID = ""
COUNTRY_A_NAME = ""

# ===================================================================
# LAMBDA HANDLER (Entrypoint)
# ===================================================================


def lambda_handler(event, context):
    """
    SQS-triggered Lambda handler.
    Parses the SQS message, sets environment variables, and calls the main pipeline.
    """
    logger.info(f"Received {len(event.get('Records', []))} record(s).")

    for record in event.get("Records", []):
        try:
            body = json.loads(record["body"])
            indicator_id = body.get("indicator_id")
            country_a_name = body.get("country_a_name")

            if not indicator_id or not country_a_name:
                logger.error("Skipping message: 'indicator_id' or 'country_a_name' missing from body.")
                continue

            # --- This is the key ---
            # Set global variables for this script to use
            global INDICATOR_ID, COUNTRY_A_NAME
            INDICATOR_ID = indicator_id
            COUNTRY_A_NAME = country_a_name

            logger.info(f"Starting job for Indicator: {indicator_id}, Country: {country_a_name}")

            # Call the main function (defined below)
            run_pipeline()

            logger.info(f"Successfully completed job for Indicator: {indicator_id}, Country: {country_a_name}")

        except Exception as e:
            logger.error(f"Job FAILED for message body: {record.get('body')}. Error: {e}", exc_info=True)
            # This tells SQS the message failed, so it will be retried or sent to the DLQ
            raise e

    return {"statusCode": 200, "body": "Jobs processed."}


# ===================================================================
# ALL SCRIPT LOGIC FROM scdi_finder.py
# ===================================================================


@dataclass
class SDCI:
    """Represents a Single Dyadic Correlating Index."""

    country_a_id: int
    country_b_id: int
    length: int
    start_year_a: int
    start_year_b: int
    correlation: float


def load_indicator_map(bucket: str) -> Dict[str, int]:
    """Loads the indicator string-to-numeric-ID map from S3."""
    map_key = "pipeline-A-indicator-extractor/input/indicator_map.csv"
    logger.info(f"Loading indicator mapping from s3://{bucket}/{map_key}")
    try:
        map_obj = s3_client.get_object(Bucket=bucket, Key=map_key)
        map_df = pd.read_csv(map_obj["Body"])
        if not {"indicator_id_string", "indicator_numeric_id"}.issubset(map_df.columns):
            raise ValueError("Indicator map CSV is missing required columns.")
        return map_df.set_index("indicator_id_string")["indicator_numeric_id"].to_dict()
    except Exception as e:
        logger.error(f"Failed to load indicator map from S3: {e}", exc_info=True)
        raise


def run_pipeline():
    """Main execution function for the job."""

    if not all([S3_BUCKET, S3_INPUT_PREFIX, S3_OUTPUT_PREFIX, INDICATOR_ID, COUNTRY_A_NAME]):
        logger.error("Missing critical environment variables.")
        raise ValueError(
            "Missing critical environment variables: S3_BUCKET, S3_INPUT_PREFIX, S3_OUTPUT_PREFIX, INDICATOR_ID, COUNTRY_A_NAME"
        )

    logger.info(f"--- Starting OPTIMIZED SDCI Finder Job for Indicator: {INDICATOR_ID}, Country: {COUNTRY_A_NAME} ---")

    # 1. Load data from S3
    indicator_df, countries_df = load_data()
    country_name_to_id = {row["name_1"]: row["id"] for _, row in countries_df.iterrows()}

    # 2. Load Indicator Map
    indicator_map = load_indicator_map(S3_BUCKET)
    indicator_numeric_id = indicator_map.get(INDICATOR_ID)
    if indicator_numeric_id is None:
        logger.error(f"Numeric ID for indicator '{INDICATOR_ID}' not found in map. Exiting.")
        raise ValueError(f"Numeric ID for indicator '{INDICATOR_ID}' not found in map.")

    # 3. Preprocess data
    countries = indicator_df["country"].unique()
    preprocessed_data = preprocess_data(indicator_df, countries, MIN_LENGTH)
    logger.info(f"Successfully preprocessed data for {len(preprocessed_data)} countries.")

    # 4. Find and save SDCIs using the new parallel, checkpointing method
    find_and_save_sdcis_parallel(preprocessed_data, country_name_to_id, indicator_numeric_id)

    logger.info(f"--- Job for Indicator {INDICATOR_ID}, Country {COUNTRY_A_NAME} completed successfully. ---")


def find_sdcis_with_fft(
    country_a_data: Dict[str, Any], country_b_data: Dict[str, Any], country_name_to_id: Dict[str, int], segment_len: int
) -> List[SDCI]:
    """Uses FFT-based cross-correlation to find SDCIs for a single segment length."""

    values_a = country_a_data["values"]
    values_b = country_b_data["values"]
    sdcis = []

    if len(values_b) < segment_len:
        return sdcis

    # Pre-calculate rolling statistics for country B for efficiency
    b_series = pd.Series(values_b)
    rolling_mean_b = b_series.rolling(window=segment_len).mean().to_numpy()[segment_len - 1 :]
    rolling_std_b = b_series.rolling(window=segment_len).std(ddof=0).to_numpy()[segment_len - 1 :]

    for start_a in range(len(values_a) - segment_len + 1):
        segment_a = values_a[start_a : start_a + segment_len]
        mean_a = np.mean(segment_a)
        std_a = np.std(segment_a)

        if std_a == 0:
            continue

        # Normalize segment_a for Pearson correlation
        norm_segment_a = (segment_a - mean_a) / std_a

        # --- START BUGFIX ---
        # This is the full cross-correlation, but it's not yet Pearson
        correlations = signal.correlate(values_b, norm_segment_a, mode="valid")

        # We must apply the full, robust formula to correct for
        # floating point errors and non-zero means.
        sum_z_a = np.sum(norm_segment_a)

        for start_b in range(len(correlations)):
            std_b = rolling_std_b[start_b]
            if std_b == 0:
                continue

            mean_b = rolling_mean_b[start_b]

            # This is Sum(B * Z(A))
            raw_corr_sum = correlations[start_b]

            # This is the correct, numerically stable Pearson formula:
            # (1 / (N * std_b)) * [ Sum(B*Z(A)) - mean_b * Sum(Z(A)) ]
            pearson_corr = (1 / (segment_len * std_b)) * (raw_corr_sum - (mean_b * sum_z_a))
            # --- END BUGFIX ---

            # Clamp outlier values just in case of float instability
            if pearson_corr > 1.0:
                pearson_corr = 1.0
            elif pearson_corr < -1.0:
                pearson_corr = -1.0

            if pearson_corr >= CORRELATION_THRESHOLD:
                sdcis.append(
                    SDCI(
                        country_a_id=country_name_to_id.get(country_a_data["country"], 0),
                        country_b_id=country_name_to_id.get(country_b_data["country"], 0),
                        length=segment_len,
                        correlation=pearson_corr,
                        start_year_a=country_a_data["data"].iloc[start_a]["year"],
                        start_year_b=country_b_data["data"].iloc[start_b]["year"],
                    )
                )
    return sdcis


def process_one_country_pair(
    country_a_data: Dict[str, Any], country_b_data: Dict[str, Any], country_name_to_id: Dict[str, int]
) -> Tuple[str, List[SDCI]]:
    """
    Worker function for the process pool. Processes one (Country A vs Country B) pair.
    """
    sdcis_for_pair = []
    values_a = country_a_data["values"]

    for segment_len in range(MIN_LENGTH, len(values_a) + 1):
        found_sdcis = find_sdcis_with_fft(country_a_data, country_b_data, country_name_to_id, segment_len)
        if found_sdcis:
            sdcis_for_pair.extend(found_sdcis)

    return country_b_data["country"], sdcis_for_pair


def delete_s3_prefix(bucket: str, prefix: str):
    """
    Deletes all objects under a given prefix in S3, handling pagination and batching.
    """
    paginator = s3_client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

    keys_to_delete = []
    for page in pages:
        for obj in page.get("Contents", []):
            keys_to_delete.append({"Key": obj["Key"]})
            if len(keys_to_delete) == 1000:
                s3_client.delete_objects(Bucket=bucket, Delete={"Objects": keys_to_delete})
                logger.info(f"Deleted a batch of {len(keys_to_delete)} temporary files.")
                keys_to_delete = []

    if keys_to_delete:
        s3_client.delete_objects(Bucket=bucket, Delete={"Objects": keys_to_delete})
        logger.info(f"Deleted the final batch of {len(keys_to_delete)} temporary files.")


def find_and_save_sdcis_parallel(preprocessed_data: list, country_name_to_id: dict, indicator_numeric_id: int):
    """
    Orchestrates the parallel processing of country pairs with checkpointing and robust cleanup.
    """
    country_a_data = next((c for c in preprocessed_data if c["country"] == COUNTRY_A_NAME), None)
    if not country_a_data:
        logger.warning(f"Country '{COUNTRY_A_NAME}' not found. Exiting job.")
        return

    country_a_id = country_name_to_id.get(COUNTRY_A_NAME)
    if not country_a_id:
        logger.error(
            f"Could not find numeric ID for country '{COUNTRY_A_NAME}'. Cannot determine partition path. Exiting."
        )
        return

    tmp_output_prefix = f"pipeline-B-scdi-finder/tmp/{INDICATOR_ID}/{COUNTRY_A_NAME}/"
    # NOTE: The S3_OUTPUT_PREFIX is now 'pipeline-B-scdi-finder/scdis/'
    final_output_key = f"{S3_OUTPUT_PREFIX.rstrip('/')}/country_a_id={country_a_id}/{INDICATOR_ID}.parquet"

    logger.info(f"This job will write its final output to: s3://{S3_BUCKET}/{final_output_key}")

    completed_country_b = set()
    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=S3_BUCKET, Prefix=tmp_output_prefix)
        for page in pages:
            for obj in page.get("Contents", []):
                done_country = os.path.splitext(os.path.basename(obj["Key"]))[0]
                completed_country_b.add(done_country)
        if completed_country_b:
            logger.info(f"Resuming job, found {len(completed_country_b)} completed checkpoints.")
    except Exception:
        logger.warning("Could not list checkpoints, starting from scratch.")

    country_a_index = preprocessed_data.index(country_a_data)
    tasks = [
        (country_a_data, country_b_data, country_name_to_id)
        for country_b_data in preprocessed_data[country_a_index + 1 :]
        if country_b_data["country"] not in completed_country_b
    ]
    if not tasks:
        logger.info("All country pair comparisons are already complete.")
    else:
        # psutil.cpu_count() will correctly report the vCPUs available to the Lambda
        num_workers = psutil.cpu_count()
        logger.info(f"Starting ProcessPoolExecutor with {num_workers} workers for {len(tasks)} tasks.")

        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = {executor.submit(process_one_country_pair, *task): task for task in tasks}
            for future in as_completed(futures):
                try:
                    country_b_name, sdcis = future.result()
                    if sdcis:
                        df = convert_sdcis_to_df(sdcis)
                        buffer = BytesIO()
                        df.to_parquet(buffer, index=False, compression="snappy")
                        key = f"{tmp_output_prefix}{country_b_name}.parquet"
                        s3_client.put_object(Bucket=S3_BUCKET, Key=key, Body=buffer.getvalue())
                        logger.info(f"Checkpointed {len(sdcis)} SDCIs for pair ({COUNTRY_A_NAME}, {country_b_name})")
                except Exception as e:
                    failed_country_b = futures[future][1]["country"]
                    logger.error(f"Comparison with {failed_country_b} failed: {e}", exc_info=True)

    logger.info("Consolidating all partial results...")
    all_dfs = []
    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=S3_BUCKET, Prefix=tmp_output_prefix)
        for page in pages:
            for obj in page.get("Contents", []):
                s3_obj = s3_client.get_object(Bucket=S3_BUCKET, Key=obj["Key"])
                df = pd.read_parquet(BytesIO(s3_obj["Body"].read()))
                all_dfs.append(df)
    except Exception as e:
        logger.error(f"Failed during consolidation: {e}", exc_info=True)

    if all_dfs:
        final_df = pd.concat(all_dfs, ignore_index=True)

        if "country_a_id" in final_df.columns:
            final_df = final_df.drop(columns=["country_a_id"])

        final_df["indicator_numeric_id"] = indicator_numeric_id
        final_df["indicator_numeric_id"] = final_df["indicator_numeric_id"].astype("uint16")

        buffer = BytesIO()
        final_df.to_parquet(buffer, index=False, compression="snappy")
        s3_client.put_object(Bucket=S3_BUCKET, Key=final_output_key, Body=buffer.getvalue())
        logger.info(f"Saved final output with {len(final_df)} SDCIs to s3://{S3_BUCKET}/{final_output_key}")
    else:
        logger.info("No partial results found. Nothing to consolidate.")

    logger.info(f"Cleaning up temporary prefix: {tmp_output_prefix}")
    try:
        delete_s3_prefix(S3_BUCKET, tmp_output_prefix)
        logger.info("Cleanup of temporary prefix complete.")
    except Exception as e:
        logger.error(f"An error occurred during cleanup: {e}", exc_info=True)


def load_data() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Loads the main indicator file and the countries mapping file from S3."""
    try:
        indicator_key = f"{S3_INPUT_PREFIX.rstrip('/')}/{INDICATOR_ID}/{INDICATOR_ID}.parquet"
        logger.info(f"Loading indicator data from s3://{S3_BUCKET}/{indicator_key}")
        indicator_obj = s3_client.get_object(Bucket=S3_BUCKET, Key=indicator_key)
        indicator_df = pd.read_parquet(BytesIO(indicator_obj["Body"].read()))

        countries_key = "pipeline-A-indicator-extractor/input/countries.csv"
        logger.info(f"Loading countries mapping from s3://{S3_BUCKET}/{countries_key}")
        countries_obj = s3_client.get_object(Bucket=S3_BUCKET, Key=countries_key)
        countries_df = pd.read_csv(countries_obj["Body"])
        return indicator_df, countries_df
    except Exception as e:
        logger.error(f"Failed to load data from S3: {e}", exc_info=True)
        raise


def preprocess_data(df: pd.DataFrame, countries: list, min_len: int) -> list:
    """
    Prepares data for each country by finding the longest possible continuous
    streak of data, filling at most one NaN if it connects two longer streaks.
    """
    preprocessed_data = []
    for country in countries:
        country_data = df[df["country"] == country].sort_values("year").reset_index(drop=True)
        if country_data.empty or len(country_data) < min_len:
            continue

        values = country_data["value"].values.copy()
        not_nan = ~np.isnan(values)

        if not np.any(not_nan):
            continue

        change_points = np.diff(not_nan.astype(int))
        starts = np.where(change_points == 1)[0] + 1
        ends = np.where(change_points == -1)[0] + 1
        if not_nan[0]:
            starts = np.insert(starts, 0, 0)
        if not_nan[-1]:
            ends = np.append(ends, len(values))

        blocks = list(zip(starts, ends))
        if not blocks:
            continue

        best_streak_start, best_streak_end, longest_len = -1, -1, 0

        for start, end in blocks:
            if (end - start) > longest_len:
                longest_len = end - start
                best_streak_start, best_streak_end = start, end

        for i in range(len(blocks) - 1):
            gap_start, gap_end = blocks[i][1], blocks[i + 1][0]
            if gap_end - gap_start == 1:
                merged_len = blocks[i + 1][1] - blocks[i][0]
                if merged_len > longest_len:
                    longest_len = merged_len
                    best_streak_start, best_streak_end = blocks[i][0], blocks[i + 1][1]

        if longest_len >= min_len:
            final_data_slice = country_data.iloc[best_streak_start:best_streak_end].copy()
            final_values_slice = values[best_streak_start:best_streak_end].copy()

            nan_indices = np.isnan(final_values_slice)
            if np.sum(nan_indices) == 1:
                nan_pos = np.where(nan_indices)[0][0]
                if 0 < nan_pos < len(final_values_slice) - 1:
                    final_values_slice[nan_pos] = (
                        final_values_slice[nan_pos - 1] + final_values_slice[nan_pos + 1]
                    ) / 2
                else:
                    continue

            if np.any(np.isnan(final_values_slice)):
                continue

            preprocessed_data.append(
                {"country": country, "data": final_data_slice.reset_index(drop=True), "values": final_values_slice}
            )

    return preprocessed_data


def convert_sdcis_to_df(sdcis: List[SDCI]) -> pd.DataFrame:
    """Converts a list of SDCI objects to a memory-optimized DataFrame."""
    if not sdcis:
        return pd.DataFrame()
    return pd.DataFrame([sdc.__dict__ for sdc in sdcis]).astype(
        {
            "country_a_id": "uint16",
            "country_b_id": "uint16",
            "length": "uint16",
            "start_year_a": "uint16",
            "start_year_b": "uint16",
            "correlation": "float32",
        }
    )
