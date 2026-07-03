"""
Pipeline A — Sheet Fetcher Lambda

Reads the Pipeline_Indicator_Catalog XLSX from S3, generates per-provider
indicator_map_<provider>.csv files, plus a combined legacy indicator_map.csv,
plus an indicators.json output for the dispatcher.

MULTI-PROVIDER MODE (new 2026-04-16, ticket #240):
- If the XLSX has multiple sheets, treats each as a provider.
- Sheet name → provider name (e.g., "WB", "FAOSTAT", "V-Dem").
- Special case: legacy sheet "phase_2_indicators" is treated as provider "WB".
- Sheets starting with "_" or named "archive"/"meta" are skipped.

Backward compatibility:
- If only the legacy sheet exists, behaves exactly like before.
- The legacy combined indicator_map.csv is always written (consumed by scdi-finder Batch job that may not be multi-provider-aware).

Env Vars:
- INPUT_BUCKET: S3 bucket containing the XLSX
- INPUT_KEY: S3 key of the XLSX
- OUTPUT_BUCKET: where to write outputs
- OUTPUT_KEY: where to write the per-indicator JSON (e.g., indicators/indicators.json)
- INDICATOR_MAP_KEY: where to write the legacy combined CSV (optional)
- INDICATOR_MAP_PREFIX: where to write per-provider CSVs as
  {prefix}/indicator_map_<provider>.csv (optional, defaults to dirname(INDICATOR_MAP_KEY))
"""

import boto3
import os
import json
import pandas as pd
import io
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")

# Legacy sheet name treated as 'WB' provider for backward compat
LEGACY_SHEET_NAME = "phase_2_indicators"
LEGACY_SHEET_PROVIDER = "WB"

# Sheets to skip when iterating multi-sheet XLSX
SKIP_SHEET_PREFIXES = ("_",)
SKIP_SHEET_NAMES = {"archive", "meta", "notes", "readme"}


def _provider_name_for_sheet(sheet_name: str) -> str:
    """Map a sheet name to a canonical provider name."""
    if sheet_name == LEGACY_SHEET_NAME:
        return LEGACY_SHEET_PROVIDER
    return sheet_name.upper().replace(" ", "_").replace("-", "_")


def _should_skip_sheet(sheet_name: str) -> bool:
    if any(sheet_name.startswith(p) for p in SKIP_SHEET_PREFIXES):
        return True
    if sheet_name.lower() in SKIP_SHEET_NAMES:
        return True
    return False


# Columns that _parse_sheet handles explicitly (type-coerced). Everything
# else in the sheet is passed through as-is so provider-specific columns
# (wb_indicator_code, fao_domain_code, fao_item_code, fao_element_code,
# fao_unit, vdem_var_name, etc.) flow into the output JSON without a
# per-provider code change each time we add a new provider.
_ESSENTIAL_COLUMNS = {"id_string", "numeric_id", "name", "status"}


def _parse_sheet(file_content: bytes, sheet_name: str) -> list[dict]:
    """Parse one sheet into a list of indicator dicts.

    Essential columns (must be present): ``id_string``, ``numeric_id``,
    ``name``, ``status``. A row missing ``id_string`` or ``numeric_id``
    is silently skipped (blank row in the XLSX). All OTHER columns are
    passed through as-is — provider-specific columns like
    ``fao_domain_code`` get included without a code change here.
    """
    df = pd.read_excel(
        io.BytesIO(file_content),
        engine="openpyxl",
        sheet_name=sheet_name,
    )
    df.columns = df.columns.str.strip()
    passthrough_cols = [c for c in df.columns if c not in _ESSENTIAL_COLUMNS]

    indicators = []
    for _, row in df.iterrows():
        # Basic validation: skip if ID or numeric_id missing
        if pd.isna(row.get("id_string")) or pd.isna(row.get("numeric_id")):
            continue

        ind = {
            "id_string": str(row["id_string"]).strip(),
            "numeric_id": int(row["numeric_id"]),
            "name": str(row.get("name", "")).strip(),
            "status": str(row["status"]).strip().lower() if not pd.isna(row.get("status")) else "hold",
        }
        # Pass through EVERY non-essential column. Preserves int/float
        # types for numeric codes (FAOSTAT item codes, V-Dem var numbers)
        # instead of stringifying them.
        for col in passthrough_cols:
            val = row.get(col)
            if pd.isna(val):
                continue
            if isinstance(val, bool):
                ind[col] = bool(val)
            elif isinstance(val, (int, float)):
                # Preserve int shape when the Excel cell round-trips as int
                as_int = int(val)
                ind[col] = as_int if as_int == val else float(val)
            else:
                ind[col] = str(val).strip()
        indicators.append(ind)
    return indicators


def lambda_handler(event, context):
    try:
        input_bucket = os.environ["INPUT_BUCKET"]
        input_key = os.environ["INPUT_KEY"]
        output_bucket = os.environ["OUTPUT_BUCKET"]
        output_key = os.environ["OUTPUT_KEY"]
        indicator_map_key = os.environ.get("INDICATOR_MAP_KEY")
        # Per-provider CSV prefix; defaults to same dir as legacy CSV
        if indicator_map_key:
            default_prefix = "/".join(indicator_map_key.split("/")[:-1])
            indicator_map_prefix = os.environ.get("INDICATOR_MAP_PREFIX", default_prefix)
        else:
            indicator_map_prefix = os.environ.get("INDICATOR_MAP_PREFIX")

        logger.info(f"Reading Excel from s3://{input_bucket}/{input_key}")

        # 1. Get object from S3
        response = s3_client.get_object(Bucket=input_bucket, Key=input_key)
        file_content = response["Body"].read()

        # 2. Discover sheets
        xl = pd.ExcelFile(io.BytesIO(file_content), engine="openpyxl")
        sheet_names = xl.sheet_names
        logger.info(f"Discovered sheets: {sheet_names}")

        eligible_sheets = [s for s in sheet_names if not _should_skip_sheet(s)]
        if not eligible_sheets:
            raise ValueError(f"No eligible sheets found in XLSX. Sheets present: {sheet_names}")

        # 3. Parse each sheet
        providers_data: dict[str, list[dict]] = {}
        for sheet_name in eligible_sheets:
            provider = _provider_name_for_sheet(sheet_name)
            try:
                inds = _parse_sheet(file_content, sheet_name)
                # #240 follow-up: tag each indicator with its provider so
                # downstream consumers (dispatcher, per-provider Fargate
                # fetcher routing) don't have to recompute from the
                # nested `providers` structure. Matches the "catalog.json"
                # schema from the 2026-04-19 QA storage memo.
                for ind in inds:
                    ind["provider"] = provider
                providers_data[provider] = inds
                logger.info(f"  Sheet {sheet_name!r} -> provider {provider!r}: {len(inds)} indicators")
            except Exception as e:
                logger.warning(f"  Failed to parse sheet {sheet_name!r}: {e}. Skipping.")

        if not providers_data or not any(providers_data.values()):
            raise ValueError("No valid indicators found in any sheet.")

        # 4. Write per-provider CSVs
        per_provider_keys = []
        if indicator_map_prefix:
            for provider, indicators in providers_data.items():
                if not indicators:
                    continue
                map_rows = [f"{ind['id_string']},{ind['numeric_id']}" for ind in indicators]
                map_csv = "id_string,numeric_id\n" + "\n".join(map_rows)
                per_provider_key = f"{indicator_map_prefix.rstrip('/')}/indicator_map_{provider.lower()}.csv"
                s3_client.put_object(
                    Bucket=output_bucket,
                    Key=per_provider_key,
                    Body=map_csv,
                    ContentType="text/csv",
                )
                per_provider_keys.append(per_provider_key)
                logger.info(
                    f"  Wrote {provider} CSV ({len(indicators)} rows) to s3://{output_bucket}/{per_provider_key}"
                )

        # 5. Write legacy combined CSV (backward compat for scdi-finder)
        all_indicators = [ind for inds in providers_data.values() for ind in inds]
        if indicator_map_key:
            map_rows = [f"{ind['id_string']},{ind['numeric_id']}" for ind in all_indicators]
            map_csv = "id_string,numeric_id\n" + "\n".join(map_rows)
            s3_client.put_object(
                Bucket=output_bucket,
                Key=indicator_map_key,
                Body=map_csv,
                ContentType="text/csv",
            )
            logger.info(
                f"Wrote legacy combined indicator_map.csv ({len(all_indicators)} rows) to s3://{output_bucket}/{indicator_map_key}"
            )

        # 6. Write JSON output (with provider info)
        # Backward compat: keep the flat "indicators" array; ADD a "providers" structure.
        output_body = json.dumps(
            {
                "indicators": all_indicators,  # flat, backward-compat
                "providers": [
                    {"name": provider, "indicators": indicators} for provider, indicators in providers_data.items()
                ],
                "metadata": {
                    "sheet_count": len(eligible_sheets),
                    "provider_count": len(providers_data),
                    "total_indicators": len(all_indicators),
                    "active_indicators": sum(1 for ind in all_indicators if ind.get("status") == "process"),
                },
            },
            indent=2,
        )

        s3_client.put_object(
            Bucket=output_bucket,
            Key=output_key,
            Body=output_body,
            ContentType="application/json",
        )
        logger.info(
            f"Wrote indicators.json ({len(all_indicators)} indicators across {len(providers_data)} providers) to s3://{output_bucket}/{output_key}"
        )

        return {
            "status": "Success",
            "indicators_fetched": len(all_indicators),
            "active_indicators": sum(1 for ind in all_indicators if ind.get("status") == "process"),
            "providers": list(providers_data.keys()),
            "per_provider_csv_keys": per_provider_keys,
        }

    except Exception as e:
        logger.error(f"Sheet Fetcher Failed: {e}", exc_info=True)
        raise e
