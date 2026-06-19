"""
SDCI Finder for AWS Batch (Optimized Version)

This script represents a highly optimized version of the SDCI finder, designed
for massively parallel execution on AWS Batch.

Key Optimizations Implemented:
1.  **Fine-Grained Jobs:** Each job processes exactly one main country ('Country A'),
    specified by the COUNTRY_A_NAME environment variable.
2.  **Intra-Job Parallelism:** Uses a ProcessPoolExecutor to parallelize the
    comparison of 'Country A' against all other countries ('Country B') across
    all available vCPUs on the instance.
3.  **FFT-Based Algorithm:** Replaces the O(n^4) brute-force correlation search
    with a vastly more performant algorithm based on scipy's FFT cross-correlation.
4.  **Resilient Checkpointing:** Each parallel task checkpoints its individual result
    (e.g., the result of A vs. B) to a temporary S3 location. If the spot instance
    is terminated, a resumed job will skip already completed pairs, saving hours
    of computation.
5.  **Final Consolidation:** After all parallel tasks are complete, the job
    consolidates all temporary partial results into a single final output file
    and cleans up the temporary directory.
"""

import os
import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple
from io import BytesIO
from concurrent.futures import ProcessPoolExecutor, as_completed

import boto3
import pandas as pd
import numpy as np
from scipy import signal
import psutil  # For getting CPU count


S3_BUCKET = os.environ.get("S3_BUCKET")
S3_INPUT_PREFIX = os.environ.get("S3_INPUT_PREFIX")
S3_OUTPUT_PREFIX = os.environ.get("S3_OUTPUT_PREFIX")
INDICATOR_ID = os.environ.get("INDICATOR_ID")
COUNTRY_A_NAME = os.environ.get("COUNTRY_A_NAME")
MIN_LENGTH = int(os.environ.get("MIN_LENGTH", 3))
# Legacy single-threshold env var, retained as a hard floor across all tiers.
# Set to a value below the lowest tier threshold (0.82) so it never overrides them.
CORRELATION_THRESHOLD = float(os.environ.get("CORRELATION_THRESHOLD", 0.5))

# #509 (2026-04-28): hard year cutoff for SCDI search. V-Dem v16 brought
# 1789-2025 coverage to qgi_data.indicators (#494 close-out). Without a
# cutoff, the SCDI finder would burn ~10x more compute on pre-1960
# V-Dem segments that are analytically uninformative for QGI's
# "find modern precedent for modern event" use case (V-Dem's pre-1960
# coverage is sparse and methodologically discontinuous — coders
# backfill from historical records, confidence drops at depth).
#
# Filter is applied at the COMPUTE layer in load_data() BEFORE
# preprocess_data finds the longest continuous streak per country.
# The data lake preserves all rows back to 1789; they just don't
# participate in SCDI search.
#
# WB / FAO indicators (already 1960+) see no row drops — this filter
# is effectively a V-Dem-specific cost guard. Ablation researchers
# can dial the cutoff back via the MIN_YEAR_CUTOFF env var without
# a code change.
MIN_YEAR_CUTOFF = int(os.environ.get("MIN_YEAR_CUTOFF", 1960))

# #502 (2026-04-27): Benjamini-Hochberg / FDR multiple-testing correction
# is removed per founder hard veto (`feedback_no_fdr_correction.md`). QGI
# is screening candidates for downstream investigation, not making point
# claims that need bounded false-discovery rates. Spurious correlations
# are filtered downstream via Phase C/D pattern aggregation requiring
# COUNT >= 2 indicators per country pair, plus recipe binding to events.
# Do NOT re-add BH/FDR / Bonferroni / any multiple-testing correction
# here without explicit founder direction; closes #356.

# #128: Tier-aware Pearson thresholds. Pattern length stratification (D-decision
# 2026-04-06): short patterns capture specific causal mechanisms and demand a
# stricter |r| threshold; longer patterns reflect institutional similarity and
# can tolerate slightly looser correlation.
#
#   S  ( 3-8 yr)  : single policy/commodity cycle               -> |r| >= 0.88
#   M  ( 9-20 yr) : leadership era / generational shift          -> |r| >= 0.85
#   L  (21-40 yr) : Cold War era / development model             -> |r| >= 0.82
#   XL (41+  yr)  : institutional similarity                     -> |r| >= 0.82
#
# Each threshold can be overridden via env var for backtesting / sweeps.
TIER_THRESHOLD_S = float(os.environ.get("TIER_THRESHOLD_S", 0.88))
TIER_THRESHOLD_M = float(os.environ.get("TIER_THRESHOLD_M", 0.85))
TIER_THRESHOLD_L = float(os.environ.get("TIER_THRESHOLD_L", 0.82))
TIER_THRESHOLD_XL = float(os.environ.get("TIER_THRESHOLD_XL", 0.82))


def apply_year_cutoff(df: pd.DataFrame, min_year: int) -> pd.DataFrame:
    """Drop rows with year < min_year (#509).

    Returns a new DataFrame (`.copy()`); the caller's reference is
    unchanged. If `year` column is missing, returns the input unchanged
    with a warning (defensive against a future schema drift in
    indicators_completed).

    ## Side-effect: streak-bridging

    Because this filter runs BEFORE preprocess_data's longest-streak
    finder, dropping pre-cutoff rows can BRIDGE pre-existing gaps in
    the post-cutoff data. Example: a country with values 1900-2020
    but a NaN gap at 1955-1965 had two streaks under the old logic
    (1900-1954 and 1966-2020). Post-cutoff: only the 1965+ portion
    of the 2nd block survives, leaving a single contiguous 1966-2020
    block — gap removed by the cutoff truncation, not by imputation.
    This extends the analyzable streak length and is desirable for
    SCDI search.

    For V-Dem indicators specifically (which have sparse pre-1960
    coverage AND post-1960 continuous coverage), this is essentially
    free streak length.

    Future researchers tweaking MIN_YEAR_CUTOFF should be aware that
    a less aggressive cutoff (e.g., 1900) would surface gaps that
    are currently hidden by the 1960 truncation.

    ## Cost impact

    Up to ~10x reduction in SCDI compute for V-Dem indicators
    (236-year span → 65-year span). For WB / FAO indicators that are
    already 1960+, this is a strict no-op (zero rows dropped, same
    compute as before). The ~10x figure is V-Dem-specific.
    """
    if "year" not in df.columns:
        logging.warning(f"[year_cutoff] 'year' column missing — skipping cutoff. Available columns: {list(df.columns)}")
        return df
    before = len(df)
    out = df[df["year"] >= min_year].copy()
    after = len(out)
    dropped = before - after
    if dropped == 0:
        logging.info(
            f"[year_cutoff] {before:,} rows all >= {min_year} (no-op). "
            f"Indicator {INDICATOR_ID} has no pre-{min_year} coverage."
        )
    else:
        logging.info(
            f"[year_cutoff] {before:,} -> {after:,} rows after applying "
            f"year >= {min_year} cutoff (dropped {dropped:,} rows = "
            f"{100 * dropped / before:.1f}% pre-{min_year})"
        )
    return out


def tier_threshold(segment_len: int) -> float:
    """Return the minimum |Pearson r| required for a given pattern length."""
    if segment_len <= 8:
        t = TIER_THRESHOLD_S
    elif segment_len <= 20:
        t = TIER_THRESHOLD_M
    elif segment_len <= 40:
        t = TIER_THRESHOLD_L
    else:
        t = TIER_THRESHOLD_XL
    # Honour the legacy global floor in case it is set higher than the tier value
    return max(t, CORRELATION_THRESHOLD)


s3_client = boto3.client("s3")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

S3_DEBUG_OUTPUT_PREFIX = os.environ.get("S3_DEBUG_OUTPUT_PREFIX")
if S3_DEBUG_OUTPUT_PREFIX:
    logging.warning(f"DEBUG MODE: Overriding output path to s3://{S3_BUCKET}/{S3_DEBUG_OUTPUT_PREFIX}")
    S3_OUTPUT_PREFIX = S3_DEBUG_OUTPUT_PREFIX


@dataclass
class SDCI:
    """Represents a Single Dyadic Correlating Index."""

    country_a_id: int
    country_b_id: int
    length: int
    start_year_a: int
    start_year_b: int
    correlation: float
    # #461 (D7 plumbing): true when ANY year in either segment_a or
    # segment_b had `is_predicted=true` in indicators_completed. Read
    # by the pattern synthesizer (Phase C) which OR-aggregates across
    # contributing SCDIs, then by the recipe engine (Phase 5b) which
    # inherits from the source pattern, then surfaced on the frontend
    # as a "contains predicted values" badge so users can interpret
    # the analogue accordingly.
    contains_predicted: bool = False


def load_indicator_map(bucket: str) -> Dict[str, int]:
    """Loads the indicator string-to-numeric-ID map from S3.

    Schema: the CSV at s3://{bucket}/pipeline-A-indicator-extractor/input/
    indicator_map.csv has two columns produced by the upstream WB sheet
    fetcher: ``id_string`` (e.g. NY.GDP.MKTP.KD.ZG) and ``numeric_id``
    (sequential int). This matches the WB indicators XLSX schema (#155).
    """
    map_key = "pipeline-A-indicator-extractor/input/indicator_map.csv"
    logging.info(f"Loading indicator mapping from s3://{bucket}/{map_key}")
    try:
        map_obj = s3_client.get_object(Bucket=bucket, Key=map_key)
        map_df = pd.read_csv(map_obj["Body"])
        required = {"id_string", "numeric_id"}
        if not required.issubset(map_df.columns):
            raise ValueError(
                f"Indicator map CSV is missing required columns. "
                f"Expected {sorted(required)}, found {sorted(map_df.columns)}."
            )
        return map_df.set_index("id_string")["numeric_id"].to_dict()
    except Exception as e:
        logging.error(f"Failed to load indicator map from S3: {e}", exc_info=True)
        raise


def run_pipeline():
    """Main execution function for the job."""
    if not all([S3_BUCKET, S3_INPUT_PREFIX, S3_OUTPUT_PREFIX, INDICATOR_ID, COUNTRY_A_NAME]):
        logging.error("Missing critical environment variables.")
        raise ValueError(
            "Missing critical environment variables: S3_BUCKET, S3_INPUT_PREFIX, S3_OUTPUT_PREFIX, INDICATOR_ID, COUNTRY_A_NAME"
        )

    logging.info(f"--- Starting OPTIMIZED SDCI Finder Job for Indicator: {INDICATOR_ID}, Country: {COUNTRY_A_NAME} ---")

    # 1. Load data from S3
    indicator_df, countries_df = load_data()
    country_name_to_id = {row["name_1"]: row["id"] for _, row in countries_df.iterrows()}

    # 1b. #509 (2026-04-28): apply MIN_YEAR_CUTOFF to filter pre-1960
    # rows. V-Dem v16 brought 1789-2025 coverage, but pre-1960 data is
    # analytically uninformative for QGI's "find modern precedent" use
    # case AND massively expands the SCDI search space. Filter applies
    # BEFORE preprocess_data finds the longest streak per country, so
    # the streak-finder operates only on cutoff-eligible years.
    indicator_df = apply_year_cutoff(indicator_df, MIN_YEAR_CUTOFF)

    # 2. Load Indicator Map
    indicator_map = load_indicator_map(S3_BUCKET)
    indicator_numeric_id = indicator_map.get(INDICATOR_ID)
    if indicator_numeric_id is None:
        logging.error(f"Numeric ID for indicator '{INDICATOR_ID}' not found in map. Exiting.")
        raise ValueError(f"Numeric ID for indicator '{INDICATOR_ID}' not found in map.")

    # 3. Preprocess data
    countries = indicator_df["country"].unique()
    preprocessed_data = preprocess_data(indicator_df, countries, MIN_LENGTH)
    logging.info(f"Successfully preprocessed data for {len(preprocessed_data)} countries.")

    # 4. Find and save SDCIs using the new parallel, checkpointing method
    find_and_save_sdcis_parallel(
        preprocessed_data,
        country_name_to_id,
        indicator_numeric_id,
    )

    logging.info(f"--- Job for Indicator {INDICATOR_ID}, Country {COUNTRY_A_NAME} completed successfully. ---")


def find_sdcis_with_fft(
    country_a_data: Dict[str, Any], country_b_data: Dict[str, Any], country_name_to_id: Dict[str, int], segment_len: int
) -> List[SDCI]:
    """Uses FFT-based cross-correlation to find SDCIs for a single segment length."""

    values_a = country_a_data["values"]
    values_b = country_b_data["values"]
    # #461: per-row is_predicted flag from indicators_completed. Falls back
    # to all-False when the upstream parquet predates D7 (older snapshots)
    # so the script remains runnable against legacy data.
    is_predicted_a = country_a_data.get("is_predicted")
    is_predicted_b = country_b_data.get("is_predicted")
    sdcis = []

    if len(values_b) < segment_len:
        return sdcis

    # #128: tier-aware Pearson floor for this specific segment length
    threshold = tier_threshold(segment_len)

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

        # --- START FIX ---
        # This is the full cross-correlation, but it's not yet Pearson
        correlations = signal.correlate(values_b, norm_segment_a, mode="valid")

        # We must apply the full, robust formula to correct for
        # floating point errors and non-zero means.
        sum_z_a = np.sum(norm_segment_a)

        # #461: precompute whether segment_a touches a predicted year.
        # Done once per (start_a, segment_len); start_b varies inside
        # the inner loop. False whenever the upstream parquet didn't
        # carry is_predicted (legacy snapshot).
        seg_a_predicted = bool(is_predicted_a is not None and np.any(is_predicted_a[start_a : start_a + segment_len]))

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

            if pearson_corr >= threshold:
                # #461: contains_predicted = OR over segment_a + segment_b.
                seg_b_predicted = bool(
                    is_predicted_b is not None and np.any(is_predicted_b[start_b : start_b + segment_len])
                )
                sdcis.append(
                    SDCI(
                        country_a_id=country_name_to_id.get(country_a_data["country"], 0),
                        country_b_id=country_name_to_id.get(country_b_data["country"], 0),
                        length=segment_len,
                        correlation=min(1.0, pearson_corr),
                        start_year_a=country_a_data["data"].iloc[start_a]["year"],
                        start_year_b=country_b_data["data"].iloc[start_b]["year"],
                        contains_predicted=seg_a_predicted or seg_b_predicted,
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
    This is the robust way to "delete a folder".
    """
    paginator = s3_client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

    # The delete_objects API call is limited to 1000 keys per request.
    # We must batch our deletions into chunks of 1000.
    keys_to_delete = []
    for page in pages:
        for obj in page.get("Contents", []):
            keys_to_delete.append({"Key": obj["Key"]})
            if len(keys_to_delete) == 1000:
                s3_client.delete_objects(Bucket=bucket, Delete={"Objects": keys_to_delete})
                logging.info(f"Deleted a batch of {len(keys_to_delete)} temporary files.")
                keys_to_delete = []  # Reset the batch

    # Delete the final remaining batch
    if keys_to_delete:
        s3_client.delete_objects(Bucket=bucket, Delete={"Objects": keys_to_delete})
        logging.info(f"Deleted the final batch of {len(keys_to_delete)} temporary files.")


def find_and_save_sdcis_parallel(
    preprocessed_data: list,
    country_name_to_id: dict,
    indicator_numeric_id: int,
):
    """
    Orchestrates the parallel processing of country pairs with checkpointing and robust cleanup.
    """
    country_a_data = next((c for c in preprocessed_data if c["country"] == COUNTRY_A_NAME), None)
    if not country_a_data:
        logging.warning(f"Country '{COUNTRY_A_NAME}' not found. Exiting job.")
        return

    # 1. Get the numeric ID for Country A to use in the partition path.
    country_a_id = country_name_to_id.get(COUNTRY_A_NAME)
    if not country_a_id:
        logging.error(
            f"Could not find numeric ID for country '{COUNTRY_A_NAME}'. Cannot determine partition path. Exiting."
        )
        return

    # 2. Define the new, correctly partitioned final output path.
    # The output is now a single Parquet file inside a Hive-style partition folder.
    tmp_output_prefix = f"pipeline-B-scdi-finder/tmp/{INDICATOR_ID}/{COUNTRY_A_NAME}/"
    final_output_key = f"{S3_OUTPUT_PREFIX}/country_a_id={country_a_id}/{INDICATOR_ID}.parquet"

    logging.info(f"This job will write its final output to: s3://{S3_BUCKET}/{final_output_key}")

    # 1. Check for completed work (checkpointing)
    completed_country_b = set()
    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=S3_BUCKET, Prefix=tmp_output_prefix)
        for page in pages:
            for obj in page.get("Contents", []):
                done_country = os.path.splitext(os.path.basename(obj["Key"]))[0]
                completed_country_b.add(done_country)
        if completed_country_b:
            logging.info(f"Resuming job, found {len(completed_country_b)} completed checkpoints.")
    except Exception:
        logging.warning("Could not list checkpoints, starting from scratch.")

    # 2. Set up and run the parallel processing pool
    country_a_index = preprocessed_data.index(country_a_data)
    tasks = [
        (country_a_data, country_b_data, country_name_to_id)
        for country_b_data in preprocessed_data[country_a_index + 1 :]
        if country_b_data["country"] not in completed_country_b
    ]
    if not tasks:
        logging.info("All country pair comparisons are already complete.")
    else:
        num_workers = psutil.cpu_count()
        logging.info(f"Starting ProcessPoolExecutor with {num_workers} workers for {len(tasks)} tasks.")
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
                        logging.info(f"Checkpointed {len(sdcis)} SDCIs for pair ({COUNTRY_A_NAME}, {country_b_name})")
                except Exception as e:
                    failed_country_b = futures[future][1]["country"]
                    logging.error(f"Comparison with {failed_country_b} failed: {e}", exc_info=True)

    # 3. Consolidate results
    logging.info("Consolidating all partial results...")
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
        logging.error(f"Failed during consolidation: {e}", exc_info=True)
        # We will still attempt to clean up even if consolidation fails.

    # 4. Save final output
    if all_dfs:
        final_df = pd.concat(all_dfs, ignore_index=True)

        if "country_a_id" in final_df.columns:
            final_df = final_df.drop(columns=["country_a_id"])

        # #502: BH-FDR removed per founder veto. Survivors of the
        # tier-aware |r| floor (TIER_THRESHOLD_S/M/L/XL, see #128) are
        # the canonical SCDI output. Spurious correlations are filtered
        # downstream via Phase C/D pattern aggregation requiring
        # COUNT >= 2 indicators per country pair, plus recipe binding
        # to events.

        # Add the indicator_numeric_id column
        final_df["indicator_numeric_id"] = indicator_numeric_id
        # Optional: Cast to a smaller integer type if desired
        final_df["indicator_numeric_id"] = final_df["indicator_numeric_id"].astype("uint16")

        buffer = BytesIO()
        final_df.to_parquet(buffer, index=False, compression="snappy")
        s3_client.put_object(Bucket=S3_BUCKET, Key=final_output_key, Body=buffer.getvalue())
        logging.info(f"Saved final output with {len(final_df)} SDCIs to s3://{S3_BUCKET}/{final_output_key}")

    # 5. Cleanup (using the new robust function)
    logging.info(f"Cleaning up temporary prefix: {tmp_output_prefix}")
    try:
        delete_s3_prefix(S3_BUCKET, tmp_output_prefix)
        logging.info("Cleanup of temporary prefix complete.")
    except Exception as e:
        logging.error(f"An error occurred during cleanup: {e}", exc_info=True)


def load_data() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Loads the main indicator file and the countries mapping file from S3."""
    try:
        indicator_key = f"{S3_INPUT_PREFIX.rstrip('/')}/{INDICATOR_ID}/{INDICATOR_ID}.parquet"
        logging.info(f"Loading indicator data from s3://{S3_BUCKET}/{indicator_key}")
        indicator_obj = s3_client.get_object(Bucket=S3_BUCKET, Key=indicator_key)
        indicator_df = pd.read_parquet(BytesIO(indicator_obj["Body"].read()))

        # #413 — canonical path after #370 dual-location consolidation.
        # Was `pipeline-A-indicator-extractor/input/countries.csv`; moved
        # because that prefix is a shared Phase 1 input surface where
        # any new indicator-map CSV can appear, and the Glue table for
        # this file needed a dedicated non-shared prefix.
        countries_key = "pipeline-A-indicator-extractor/countries/countries.csv"
        logging.info(f"Loading countries mapping from s3://{S3_BUCKET}/{countries_key}")
        countries_obj = s3_client.get_object(Bucket=S3_BUCKET, Key=countries_key)
        countries_df = pd.read_csv(countries_obj["Body"])
        return indicator_df, countries_df
    except Exception as e:
        logging.error(f"Failed to load data from S3: {e}", exc_info=True)
        raise


def preprocess_data(df: pd.DataFrame, countries: list, min_len: int) -> list:
    """
    Prepares data for each country by finding the longest possible continuous
    streak of data, filling at most one NaN if it connects two longer streaks.

    #461: when the upstream parquet (indicators_completed) carries the
    `is_predicted` column, it is sliced + carried through alongside the
    `values` array so find_sdcis_with_fft can compute contains_predicted
    per (segment_a, segment_b) without re-reading the source data.
    """
    has_predicted_col = "is_predicted" in df.columns
    preprocessed_data = []
    for country in countries:
        country_data = df[df["country"] == country].sort_values("year").reset_index(drop=True)
        if country_data.empty or len(country_data) < min_len:
            continue

        values = country_data["value"].values.copy()
        # #461: aligned is_predicted vector. Pre-completed parquets (legacy
        # snapshots) skip the column → preprocessed entry is_predicted=None
        # → find_sdcis_with_fft falls back to contains_predicted=False.
        is_predicted_full = (
            country_data["is_predicted"].fillna(False).astype(bool).to_numpy() if has_predicted_col else None
        )
        not_nan = ~np.isnan(values)

        if not np.any(not_nan):
            continue

        # Find the start and end indices of all continuous non-NaN blocks
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

        # --- Find the best possible streak ---
        best_streak_start, best_streak_end, longest_len = -1, -1, 0

        # 1. Find the single longest natural block
        for start, end in blocks:
            if (end - start) > longest_len:
                longest_len = end - start
                best_streak_start, best_streak_end = start, end

        # 2. Check if filling a single NaN between two blocks creates a longer streak
        for i in range(len(blocks) - 1):
            gap_start, gap_end = blocks[i][1], blocks[i + 1][0]
            if gap_end - gap_start == 1:  # A gap of exactly one NaN
                merged_len = blocks[i + 1][1] - blocks[i][0]
                if merged_len > longest_len:
                    longest_len = merged_len
                    best_streak_start, best_streak_end = blocks[i][0], blocks[i + 1][1]

        # --- Process the best streak found ---
        if longest_len >= min_len:
            final_data_slice = country_data.iloc[best_streak_start:best_streak_end].copy()
            final_values_slice = values[best_streak_start:best_streak_end].copy()

            # If the best streak was a merged one, fill the single NaN
            nan_indices = np.isnan(final_values_slice)
            if np.sum(nan_indices) == 1:
                nan_pos = np.where(nan_indices)[0][0]
                if 0 < nan_pos < len(final_values_slice) - 1:
                    final_values_slice[nan_pos] = (
                        final_values_slice[nan_pos - 1] + final_values_slice[nan_pos + 1]
                    ) / 2
                else:
                    # This case is unlikely due to the logic, but as a safeguard, we discard
                    continue

            # Final check for any remaining NaNs
            if np.any(np.isnan(final_values_slice)):
                continue

            entry = {
                "country": country,
                "data": final_data_slice.reset_index(drop=True),
                "values": final_values_slice,
            }
            # #461: slice is_predicted alongside values so segment indices
            # map 1:1. Legacy parquets without the column → key omitted.
            if is_predicted_full is not None:
                entry["is_predicted"] = is_predicted_full[best_streak_start:best_streak_end].copy()
            preprocessed_data.append(entry)

    return preprocessed_data


def convert_sdcis_to_df(sdcis: List[SDCI]) -> pd.DataFrame:
    """Converts a list of SDCI objects to a memory-optimized DataFrame."""
    if not sdcis:
        return pd.DataFrame()
    df = pd.DataFrame([sdc.__dict__ for sdc in sdcis]).astype(
        {
            "country_a_id": "uint16",
            "country_b_id": "uint16",
            "length": "uint16",
            "start_year_a": "uint16",
            "start_year_b": "uint16",
            "correlation": "float32",
        }
    )
    # #461: contains_predicted carried as boolean. Pandas writes it as
    # parquet bool, matching the Glue scdis schema added in qgi-infra.
    if "contains_predicted" in df.columns:
        df["contains_predicted"] = df["contains_predicted"].astype("bool")
    return df


if __name__ == "__main__":
    run_pipeline()
