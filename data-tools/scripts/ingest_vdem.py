#!/usr/bin/env python3
"""
ingest_vdem.py — V-Dem Country-Year ingestion (#487, V-Dem #4 of 6 under #348).

Reads a V-Dem v15+ Country-Year CSV (downloaded manually from v-dem.net
because their site has a click-through), filters to the curated V-Dem
indicators (currently 39: VD-01..VD-39 per
`docs/specs/methodology/indicator-catalog-detailed.md`), applies the
country-name mapping (`registries/vdem_country_map.yaml`), pivots
wide → long, and writes per-indicator parquet partitions to the
data lake's `pipeline-A-indicator-extractor/output/parquet/` location.

Each row in the output is `(country, year, value, provider='VDEM')`,
with `indicator_id` carried as the bare path component (no Hive
`indicator_id=` prefix — see #510, 2026-04-28). The `provider` column
was added to `qgi_data.indicators` in #485 — legacy WB/FAO rows are
NULL there until the next full pipeline regeneration.

**Indicator selection is XLSX-driven** (#494 step 2, 2026-04-28). The
script reads the active V-Dem indicator list from the
`vdem_indicators` sheet of `qgi-data/indicators/control-surface.xlsx`
at runtime — same pattern WB indicators use today via the
`phase_2_indicators` sheet. Adding/removing a V-Dem indicator is a
spreadsheet edit reviewable in a PR diff, not a code change to this
script.

Filter contract: rows with `status == "process"` are ingested; rows
with `status == "hold"` are skipped (mirrors how WB's active/hold
distinction works).

Manual download flow (annual):
  1. Visit https://v-dem.net/data/the-v-dem-dataset/
  2. Click "Country-Year, Full+Others" to download (CSV or ZIP)
  3. Unzip if needed; pass the .csv path to this script via --vdem-csv-path

Usage:
  python qgi-data/scripts/ingest_vdem.py \\
      --vdem-csv-path /path/to/V-Dem-CY-Full+Others-v15.csv \\
      --bucket qgi-data-lake-771606957899 \\
      --workgroup QGI-Lambda-Workgroup \\
      --region eu-central-1 \\
      [--xlsx-path /path/to/control-surface.xlsx]   # default: ../indicators/control-surface.xlsx
      [--dry-run]   # validate transform, skip S3 writes
      [--repair]    # also run MSCK REPAIR TABLE qgi_data.indicators

Container deployment (#494 step 4 Batch image): the Dockerfile COPYs
`indicators/control-surface.xlsx` into `/app/indicators/` and sets
`INDICATOR_CATALOG_XLSX_PATH=/app/indicators/control-surface.xlsx` so
the script discovers the catalog without --xlsx-path being passed
explicitly.

Anti-patterns (per design doc docs/specs/internal/design/v-dem-integration.md):
  - Don't make this a Lambda. Annual cadence — manual run is fine.
  - Don't fork into a separate qgi_data.indicators_vdem table — single table.
  - Don't hardcode the indicator list back into this file — the XLSX is the
    source of truth (#494 step 2). Adding a V-Dem indicator means editing
    the spreadsheet, not editing this script.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import boto3
import openpyxl
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml


SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
COUNTRY_MAP_FILE = REPO_ROOT / "registries" / "vdem_country_map.yaml"
DEFAULT_XLSX_PATH = REPO_ROOT / "indicators" / "control-surface.xlsx"
XLSX_ENV_VAR = "INDICATOR_CATALOG_XLSX_PATH"

S3_PARQUET_PREFIX = "pipeline-A-indicator-extractor/output/parquet"

VDEM_SHEET_NAME = "vdem_indicators"
ACTIVE_STATUS = "process"  # rows with this status get ingested; "hold" is skipped


def resolve_xlsx_path(cli_path: Path | None) -> Path:
    """Resolve the indicator-catalog XLSX path. Precedence:
       1. --xlsx-path CLI override
       2. INDICATOR_CATALOG_XLSX_PATH env var (Batch container path)
       3. Default: <repo_root>/indicators/control-surface.xlsx
    """
    if cli_path is not None:
        return cli_path
    env_path = os.environ.get(XLSX_ENV_VAR)
    if env_path:
        return Path(env_path)
    return DEFAULT_XLSX_PATH


def load_vdem_indicators_from_xlsx(xlsx_path: Path) -> list[str]:
    """Load the active V-Dem id_string list from `control-surface.xlsx`.

    Reads the `vdem_indicators` sheet, filters to rows with
    `status == ACTIVE_STATUS` (default "process"), and returns id_strings
    in sheet order. Sheet order is meaningful — it preserves the VD-XX
    catalog ordering documented in indicator-catalog-detailed.md, so
    downstream summaries / logs read in a stable order.

    Header expected: id_string, numeric_id, name, status, category, description.
    See `qgi-data/tests/test_control_surface_schema.py` for the schema
    contract this loader depends on.
    """
    if not xlsx_path.exists():
        raise FileNotFoundError(
            f"indicator catalog XLSX not found at {xlsx_path}. "
            f"Override with --xlsx-path or set ${XLSX_ENV_VAR}."
        )
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    if VDEM_SHEET_NAME not in wb.sheetnames:
        raise ValueError(
            f"sheet {VDEM_SHEET_NAME!r} missing from {xlsx_path}. "
            f"Ensure indicators/control-surface.xlsx has the "
            f"{VDEM_SHEET_NAME!r} sheet — see scripts/add_vdem_sheet.py "
            f"for the expected schema (the script itself is # THROWAWAY "
            f"per #373 and is not safely re-runnable on a populated XLSX)."
        )
    ws = wb[VDEM_SHEET_NAME]

    indicators: list[str] = []
    skipped_hold: list[str] = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue  # header
        if row is None or row[0] is None:
            continue  # empty trailer row
        id_string, _numeric_id, _name, status, _category, _description = row
        if status == ACTIVE_STATUS:
            indicators.append(id_string)
        else:
            skipped_hold.append(id_string)

    if not indicators:
        raise ValueError(
            f"no V-Dem indicators with status={ACTIVE_STATUS!r} found in "
            f"{xlsx_path}. Spreadsheet may have drifted — run the schema "
            f"test to investigate: python -m pytest tests/test_control_surface_schema.py"
        )

    # Log held + skipped indicators so an empty production set is visibly
    # empty (vs silently empty from a status-typo or a future status value
    # like 'deprecated' that the loader doesn't recognise). Catches bugs
    # the schema test's status vocabulary check would also flag — but
    # this surface is closer to the actual ingest, so the log lands in
    # the operator's terminal during the annual run.
    if skipped_hold:
        print(
            f"[init] skipped {len(skipped_hold)} held V-Dem indicators: "
            f"{skipped_hold}"
        )
    return indicators


def load_country_map(path: Path) -> tuple[dict[str, str], set[str], set[str]]:
    """Returns (mappings: alpha-3 → qgi name, drop_set, watch_set)."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    mappings = {k: v for k, v in (raw.get("mappings") or {}).items()}
    drop = set((raw.get("drop") or {}).keys())
    watch = set((raw.get("watch") or {}).keys())
    return mappings, drop, watch


def load_vdem_csv(path: Path, indicators: list[str]) -> pd.DataFrame:
    """Read V-Dem CSV with only the columns we need.

    V-Dem v15+ uses 'country_text_id' (alpha-3) and 'year' as the row keys.
    We add the indicator columns by name. Extras are dropped at read
    time to keep memory under ~50MB.

    `indicators` is the active V-Dem id_string list loaded from the
    `vdem_indicators` sheet of `control-surface.xlsx` via
    `load_vdem_indicators_from_xlsx`.
    """
    needed_cols = ["country_text_id", "year", "country_name"] + indicators
    print(f"[load] reading V-Dem CSV: {path}")
    df = pd.read_csv(path, usecols=needed_cols, low_memory=False)
    print(f"[load] {len(df):,} rows × {len(df.columns)} columns")
    print(f"[load] year range: {int(df['year'].min())}..{int(df['year'].max())}")
    print(f"[load] distinct countries: {df['country_text_id'].nunique()}")
    return df


def normalize_countries(df: pd.DataFrame, mappings: dict[str, str],
                        drop_set: set[str], watch_set: set[str]) -> pd.DataFrame:
    """Apply alpha-3 → qgi-canonical-name mapping; drop / warn per registry."""
    initial = len(df)

    # Drop list — silent
    df_drop = df[df["country_text_id"].isin(drop_set)]
    if not df_drop.empty:
        print(f"[normalize] DROP (historical entities): {df_drop['country_text_id'].value_counts().to_dict()}")
    df = df[~df["country_text_id"].isin(drop_set)].copy()

    # Watch list — warn
    df_watch = df[df["country_text_id"].isin(watch_set)]
    if not df_watch.empty:
        print(f"[normalize] WATCH (in V-Dem, not in qgi): "
              f"{df_watch['country_text_id'].value_counts().to_dict()}")
    df = df[~df["country_text_id"].isin(watch_set)].copy()

    # Unmapped — anything left that's NOT in mappings is a surprise
    unmapped_mask = ~df["country_text_id"].isin(mappings)
    if unmapped_mask.any():
        unmapped_codes = df.loc[unmapped_mask, "country_text_id"].value_counts()
        print(f"[normalize] WARN unmapped alpha-3 (will be dropped): {unmapped_codes.to_dict()}")
        df = df[~unmapped_mask].copy()

    # Apply the alpha-3 → qgi name mapping
    df["country"] = df["country_text_id"].map(mappings)
    final = len(df)
    print(f"[normalize] kept {final:,} / {initial:,} rows ({100*final/initial:.1f}%) after country filter")
    return df


def pivot_to_long(df: pd.DataFrame, indicators: list[str]) -> pd.DataFrame:
    """Wide CSV → long format. Output columns:
        country (string), year (int32), value (float64), provider (string),
        indicator_id (string — partition key on Athena side).

    `indicators` is the active V-Dem id_string list (XLSX-driven, see
    `load_vdem_indicators_from_xlsx`).
    """
    keep = ["country", "year"] + indicators
    long_df = df[keep].melt(
        id_vars=["country", "year"], value_vars=indicators,
        var_name="indicator_id", value_name="value"
    )
    # Drop NULL values — V-Dem has many missing cells (e.g. state_capacity
    # only covers 180 countries). Aligns with how WB/FAO are stored too.
    before = len(long_df)
    long_df = long_df.dropna(subset=["value"]).copy()
    after = len(long_df)
    print(f"[pivot] {before:,} → {after:,} rows after dropping NULL values "
          f"(NULL share: {100*(before-after)/before:.1f}%)")

    long_df["year"] = long_df["year"].astype("int32")
    long_df["value"] = long_df["value"].astype("float64")
    long_df["provider"] = "VDEM"
    return long_df[["country", "year", "value", "provider", "indicator_id"]]


def upload_per_indicator_parquet(df: pd.DataFrame, bucket: str, region: str,
                                 dry_run: bool) -> dict[str, int]:
    """Group by indicator_id, write each as parquet to its own partition.

    Path: s3://{bucket}/pipeline-A-indicator-extractor/output/parquet/
          {ind}/{ind}.parquet

    **Bare layout** (#510 fix, 2026-04-28): we used to write Hive-style
    `indicator_id={ind}/{ind}.parquet` paths. That layout doesn't match
    the WB/FAO sibling pattern and the Phase A completer + Phase B SCDI
    orchestrator wouldn't discover V-Dem indicators. Switching to bare
    `{ind}/{ind}.parquet` so V-Dem joins the same auto-discovery flow
    WB/FAO use:
      - Phase 1.5 completer iterates `output/parquet/` for indicators
        in BARE layout, writes `output/parquet-completed/{ind}/{ind}.parquet`
      - Phase 2 SCDI orchestrator scans `output/parquet-completed/` and
        treats each subdir name as the indicator_id

    Existing parquet at the same key is OVERWRITTEN (idempotent re-runs).
    Other indicators (WB, FAO) live in their own partitions and are not
    touched.
    """
    s3 = boto3.client("s3", region_name=region)
    counts: dict[str, int] = {}
    for ind, sub in df.groupby("indicator_id"):
        key = f"{S3_PARQUET_PREFIX}/{ind}/{ind}.parquet"
        # Drop the partition column before writing (Athena reads it from path)
        write_df = sub.drop(columns=["indicator_id"]).reset_index(drop=True)
        # Schema: country (string), year (int32), value (float64), provider (string)
        table = pa.Table.from_pandas(write_df, preserve_index=False)
        if dry_run:
            print(f"[upload] DRY {key}: {len(write_df):,} rows (skipped)")
        else:
            buf = pa.BufferOutputStream()
            pq.write_table(table, buf, compression="snappy")
            s3.put_object(Bucket=bucket, Key=key, Body=buf.getvalue().to_pybytes())
            print(f"[upload] s3://{bucket}/{key}: {len(write_df):,} rows")
        counts[ind] = len(write_df)
    return counts


def repair_table(bucket: str, workgroup: str, region: str) -> None:
    """Athena MSCK REPAIR TABLE — registers the new partitions in Glue."""
    ath = boto3.client("athena", region_name=region)
    sql = "MSCK REPAIR TABLE qgi_data.indicators"
    print(f"[repair] {sql}")
    r = ath.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": "qgi_data"},
        WorkGroup=workgroup,
        ResultConfiguration={"OutputLocation": f"s3://{bucket}/query_results/"},
    )
    qid = r["QueryExecutionId"]
    while True:
        time.sleep(2)
        s = ath.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        if s["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
    if s["State"] != "SUCCEEDED":
        raise RuntimeError(f"MSCK REPAIR {s['State']}: {s.get('StateChangeReason', '?')}")
    print("[repair] OK")


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--vdem-csv-path", type=Path, required=True,
                   help="Path to a manually-downloaded V-Dem Country-Year CSV "
                        "(v15 or later).")
    p.add_argument("--bucket", required=True, help="S3 data lake bucket")
    p.add_argument("--workgroup", default="QGI-Lambda-Workgroup")
    p.add_argument("--region", default="eu-central-1")
    p.add_argument("--country-map", type=Path, default=COUNTRY_MAP_FILE,
                   help="Override the V-Dem country map YAML path "
                        "(default: qgi-data/registries/vdem_country_map.yaml)")
    p.add_argument("--xlsx-path", type=Path, default=None,
                   help=f"Override the indicator-catalog XLSX path. "
                        f"Default precedence: --xlsx-path > "
                        f"${XLSX_ENV_VAR} env var > "
                        f"{DEFAULT_XLSX_PATH}.")
    p.add_argument("--dry-run", action="store_true",
                   help="Validate transform end-to-end without S3 writes or MSCK")
    p.add_argument("--repair", action="store_true",
                   help="After successful upload, run MSCK REPAIR TABLE qgi_data.indicators")
    args = p.parse_args()

    if not args.vdem_csv_path.exists():
        print(f"[error] V-Dem CSV not found: {args.vdem_csv_path}", file=sys.stderr)
        return 1
    if not args.country_map.exists():
        print(f"[error] country map not found: {args.country_map}", file=sys.stderr)
        return 1

    # Load the active V-Dem indicator list from the XLSX. The schema test
    # in tests/test_control_surface_schema.py guards the contract this
    # loader depends on; if it has drifted, the loader raises before we
    # touch the V-Dem CSV.
    xlsx_path = resolve_xlsx_path(args.xlsx_path)
    try:
        indicators = load_vdem_indicators_from_xlsx(xlsx_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1
    print(f"[init] indicator catalog: {len(indicators)} active V-Dem indicators "
          f"loaded from {xlsx_path}")

    mappings, drop_set, watch_set = load_country_map(args.country_map)
    print(f"[init] country map: {len(mappings)} mappings, {len(drop_set)} drop, {len(watch_set)} watch")

    df = load_vdem_csv(args.vdem_csv_path, indicators)
    df = normalize_countries(df, mappings, drop_set, watch_set)
    long_df = pivot_to_long(df, indicators)

    counts = upload_per_indicator_parquet(long_df, args.bucket, args.region, args.dry_run)
    print(f"\n[summary] per-indicator row counts:")
    for ind in indicators:
        print(f"  {ind:25s} {counts.get(ind, 0):>7,d} rows")

    if args.repair and not args.dry_run:
        repair_table(args.bucket, args.workgroup, args.region)

    if args.dry_run:
        print("\n[dry-run] no writes performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
