#!/usr/bin/env python3
"""
Events Ingestion Script — Converts legacy unstructured (.txt) and structured (.json)
events into unified Parquet on S3, partitioned by country_id.

Usage:
    python ingest_events.py --bucket qgi-data-lake-771606957899 --region eu-central-1

Reads:
    - Legacy events:      qgi-4.0/data/events/*.txt
    - Structured events:  qgi-pipeline/data/events/batches/*.json
    - Countries CSV:      s3://{bucket}/pipeline-A-indicator-extractor/input/countries.csv

Writes:
    - s3://{bucket}/events/country_id={id}/events.parquet
    - s3://{bucket}/baselines/persistence.parquet
    - s3://{bucket}/baselines/base_rates.parquet
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from io import BytesIO

# ─── Paths ────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
LEGACY_EVENTS_DIR = Path(r"C:\Users\Amin\Desktop\trojan\qgi-4.0\data\events")
STRUCTURED_EVENTS_DIR = REPO_ROOT / "data" / "events" / "batches"
CURATED_EVENTS_DIR = REPO_ROOT / "data" / "events" / "curated"

S3_EVENTS_PREFIX = "events/"
S3_BASELINES_PREFIX = "baselines/"
S3_EVENTS_SOURCE_PREFIX = "events-source/curated/"  # Mirror of local curated/ — source of truth (#141)
COUNTRIES_KEY = "pipeline-A-indicator-extractor/input/countries.csv"
CATEGORY_MAPPING_FILE = REPO_ROOT / "data" / "events" / "category_mapping.json"
TRACKING_FILE = REPO_ROOT / "data" / "events" / "TRACKING.md"


# ─── Category Normalization ──────────────────────────────────────────────
_category_mapping = None


def load_category_mapping():
    """Load the 60-category mapping from JSON file."""
    global _category_mapping
    if _category_mapping is None:
        with open(CATEGORY_MAPPING_FILE, encoding="utf-8") as f:
            data = json.load(f)
        _category_mapping = data["mapping"]
        print(f"Loaded category mapping: {len(_category_mapping)} entries -> {len(data['taxonomy'])} categories")
    return _category_mapping


def normalize_category(cat: str) -> str:
    """Normalize to one of 60 categories using the mapping file."""
    if not cat or not isinstance(cat, str):
        return "other"
    mapping = load_category_mapping()
    # Try exact match first
    if cat in mapping:
        return mapping[cat]
    # Try stripped match
    cat_stripped = cat.strip()
    if cat_stripped in mapping:
        return mapping[cat_stripped]
    # Fallback: simple normalization for unmapped
    return "other"


# ─── Load Countries Mapping ──────────────────────────────────────────────
def load_countries(s3_client, bucket: str) -> pd.DataFrame:
    """Load countries.csv from S3, build name->id lookup across all name columns."""
    obj = s3_client.get_object(Bucket=bucket, Key=COUNTRIES_KEY)
    df = pd.read_csv(obj["Body"])

    # Build lookup: every name variant -> numeric id
    name_cols = [c for c in df.columns if c.startswith("name_")]
    lookup = {}
    for _, row in df.iterrows():
        cid = int(row["id"])
        for col in name_cols:
            name = row[col]
            if pd.notna(name) and str(name).strip():
                lookup[str(name).strip().lower()] = cid
                # Also store the primary name for this id
                if col == "name_1":
                    lookup[f"__primary_{cid}"] = str(name).strip()

    return df, lookup


def resolve_country_id(name: str, lookup: dict) -> tuple:
    """Resolve country name to (country_id, canonical_name). Returns (None, None) if not found."""
    if not name:
        return None, None
    key = name.strip().lower()

    # Direct match
    if key in lookup:
        cid = lookup[key]
        canonical = lookup.get(f"__primary_{cid}", name)
        return cid, canonical

    # Try common substitutions
    variants = [
        key.replace("ivory coast", "côte d'ivoire"),
        key.replace("cote d'ivoire", "côte d'ivoire"),
        key.replace("türkiye", "turkey"),
        key.replace("czech republic", "czechia"),
        key.replace("south korea", "korea, republic of"),
        key.replace("north korea", "korea, democratic people's republic of"),
        key.replace("usa", "united states"),
        key.replace("uk", "united kingdom"),
    ]
    for v in variants:
        if v in lookup:
            cid = lookup[v]
            canonical = lookup.get(f"__primary_{cid}", name)
            return cid, canonical

    return None, None


# ─── Parse Legacy Events ─────────────────────────────────────────────────
def parse_legacy_events(events_dir: Path) -> list:
    """Parse legacy pipe-delimited .txt files."""
    events = []
    if not events_dir.exists():
        print(f"WARNING: Legacy events dir not found: {events_dir}")
        return events

    for txt_file in sorted(events_dir.glob("*.txt")):
        for line in txt_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or not line.startswith("."):
                continue
            # Format: ". Country | Year | Category | Description"
            parts = line[1:].split("|")  # skip leading dot
            if len(parts) < 4:
                continue
            country = parts[0].strip()
            try:
                year = int(parts[1].strip())
            except ValueError:
                continue
            category = parts[2].strip()
            description = parts[3].strip()

            events.append(
                {
                    "country_name": country,
                    "year": year,
                    "title": category,  # Legacy doesn't have separate title
                    "description": description,
                    "category": category,
                    "source": "legacy_unstructured",
                }
            )

    print(f"Parsed {len(events)} legacy events from {events_dir}")
    return events


# ─── Parse Structured Events ─────────────────────────────────────────────
def parse_structured_events(batches_dir: Path, curated_dir: Path | None = None) -> list:
    """Parse structured JSON batch files.

    Per #141: when curated_dir is provided AND a `{country}.json` exists there,
    use it instead of the corresponding file in batches_dir. Curated files have
    been through the E1-E5 cleanup pass and represent the canonical source.
    """
    events = []
    if not batches_dir.exists():
        print(f"WARNING: Structured events dir not found: {batches_dir}")
        return events

    curated_files = set()
    if curated_dir and curated_dir.exists():
        curated_files = {f.name for f in curated_dir.glob("*.json")}
        print(f"Found {len(curated_files)} curated event files (will override batches/)")

    curated_used = 0
    batches_used = 0
    for json_file in sorted(batches_dir.glob("*.json")):
        # Prefer curated version if it exists
        if json_file.name in curated_files:
            actual_file = curated_dir / json_file.name
            source_label = "structured_curated"
            curated_used += 1
        else:
            actual_file = json_file
            source_label = "structured"
            batches_used += 1

        # Country name is derived from the filename (e.g. jordan.json -> Jordan)
        # because curated files don't preserve the legacy `country` field.
        # Convert snake_case → Title Case for resolve_country_id().
        derived_country = json_file.stem.replace("_", " ").title()

        try:
            for entry in _read_json_with_fallback(actual_file):
                # Curated entries don't carry a `country` field; raw batches do.
                country_name = entry.get("country") or derived_country
                events.append(
                    {
                        "country_name": country_name,
                        "year": int(entry.get("year", 0)),
                        "title": entry.get("title", ""),
                        "description": entry.get("description", ""),
                        "category": entry.get("category", ""),
                        "source": source_label,
                    }
                )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"WARNING: Failed to parse {actual_file.name}: {e}")

    print(f"Parsed {len(events)} structured events ({curated_used} curated + {batches_used} raw batches)")
    return events


def _read_json_with_fallback(path: Path) -> list:
    """Read a JSON file, falling back to latin-1 if utf-8 decoding fails."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return json.loads(path.read_text(encoding="latin-1"))


# ─── Compute Baselines ───────────────────────────────────────────────────
def compute_baselines(df: pd.DataFrame, bucket: str, s3_client) -> None:
    """Compute persistence and base rate baselines, upload to S3."""

    # 1. Persistence baseline: for each country-year, did last year's events repeat?
    persistence_rows = []
    for (cid, cat), group in df.groupby(["country_id", "category_normalized"]):
        years = sorted(group["year"].unique())
        for i, y in enumerate(years):
            if i > 0:
                prev_year = years[i - 1]
                persisted = (y - prev_year) == 1  # consecutive year = persistence hit
                persistence_rows.append({"country_id": cid, "category": cat, "year": y, "persisted": persisted})

    if persistence_rows:
        p_df = pd.DataFrame(persistence_rows)
        buf = BytesIO()
        p_df.to_parquet(buf, engine="pyarrow", compression="snappy", index=False)
        buf.seek(0)
        s3_client.put_object(Bucket=bucket, Key=f"{S3_BASELINES_PREFIX}persistence.parquet", Body=buf.getvalue())
        hit_rate = p_df["persisted"].mean() * 100
        print(f"Persistence baseline: {hit_rate:.1f}% hit rate, {len(p_df)} rows -> S3")

    # 2. Base rates: frequency of each event category per country
    base_rates = (
        df.groupby(["country_id", "category_normalized"])
        .agg(event_count=("year", "count"), year_span=("year", lambda x: x.max() - x.min() + 1))
        .reset_index()
    )
    base_rates["annual_rate"] = base_rates["event_count"] / base_rates["year_span"].clip(lower=1)

    buf = BytesIO()
    base_rates.to_parquet(buf, engine="pyarrow", compression="snappy", index=False)
    buf.seek(0)
    s3_client.put_object(Bucket=bucket, Key=f"{S3_BASELINES_PREFIX}base_rates.parquet", Body=buf.getvalue())
    print(f"Base rates: {len(base_rates)} country-category pairs -> S3")

    # 3. Global base rates
    global_rates = (
        df.groupby("category_normalized")
        .agg(total_events=("year", "count"), countries=("country_id", "nunique"))
        .reset_index()
    )
    global_rates["global_annual_rate"] = (
        global_rates["total_events"]
        / (df["year"].max() - df["year"].min() + 1)
        / global_rates["countries"].clip(lower=1)
    )

    buf = BytesIO()
    global_rates.to_parquet(buf, engine="pyarrow", compression="snappy", index=False)
    buf.seek(0)
    s3_client.put_object(Bucket=bucket, Key=f"{S3_BASELINES_PREFIX}global_rates.parquet", Body=buf.getvalue())
    print(f"Global rates: {len(global_rates)} categories -> S3")


# ─── Main ────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Ingest events to S3 Parquet")
    parser.add_argument("--bucket", required=True, help="S3 bucket name")
    parser.add_argument("--region", default="eu-central-1")
    parser.add_argument("--role-arn", help="Cross-account role ARN to assume")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no upload")
    parser.add_argument(
        "--structured-only",
        "--verified-only",
        dest="structured_only",
        action="store_true",
        help="Use only structured events, skip legacy",
    )
    args = parser.parse_args()

    if args.role_arn:
        sts = boto3.client("sts", region_name=args.region)
        creds = sts.assume_role(RoleArn=args.role_arn, RoleSessionName="events-ingestion")["Credentials"]
        s3_client = boto3.client(
            "s3",
            region_name=args.region,
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )
    else:
        s3_client = boto3.client("s3", region_name=args.region)

    # 1. Load countries mapping
    print("Loading countries mapping...")
    countries_df, country_lookup = load_countries(s3_client, args.bucket)
    print(f"Loaded {len(countries_df)} countries with {len(country_lookup)} name variants")

    # 2. Parse events
    if args.structured_only:
        legacy_events = []
        print("Structured-only mode: skipping legacy events")
    else:
        legacy_events = parse_legacy_events(LEGACY_EVENTS_DIR)
    structured_events = parse_structured_events(STRUCTURED_EVENTS_DIR, CURATED_EVENTS_DIR)
    all_events = legacy_events + structured_events
    print(f"\nTotal events: {len(all_events)} ({len(legacy_events)} legacy + {len(structured_events)} structured)")

    # 3. Build DataFrame and resolve country IDs
    df = pd.DataFrame(all_events)
    resolved = df["country_name"].apply(lambda n: resolve_country_id(n, country_lookup))
    df["country_id"] = resolved.apply(lambda x: x[0])
    df["country_name_canonical"] = resolved.apply(lambda x: x[1])

    # Report unresolved
    unresolved = df[df["country_id"].isna()]["country_name"].unique()
    if len(unresolved) > 0:
        print(f"\nWARNING: {len(unresolved)} unresolved country names:")
        for name in sorted(unresolved)[:20]:
            print(f"  - {name}")

    # Drop unresolved
    df = df.dropna(subset=["country_id"])
    df["country_id"] = df["country_id"].astype(int)

    # 4. Normalize categories
    df["category_normalized"] = df["category"].apply(normalize_category)

    # Use canonical name as country_name
    df["country_name"] = df["country_name_canonical"]
    df = df.drop(columns=["country_name_canonical"])

    print(
        f"\nFinal dataset: {len(df)} events, {df['country_id'].nunique()} countries, "
        f"{df['category_normalized'].nunique()} unique categories"
    )
    print(f"Sources: {df['source'].value_counts().to_dict()}")
    print(f"Year range: {df['year'].min()} - {df['year'].max()}")

    if args.dry_run:
        print("\n[DRY RUN] No upload performed.")
        print("\nTop 10 categories:")
        print(df["category_normalized"].value_counts().head(10).to_string())
        return

    # 5. Upload to S3 partitioned by country_id
    print(f"\nUploading to s3://{args.bucket}/{S3_EVENTS_PREFIX} ...")
    uploaded = 0
    for cid, group in df.groupby("country_id"):
        # Select columns for output
        out = group[
            ["country_name", "year", "title", "description", "category", "category_normalized", "source"]
        ].copy()
        out["year"] = out["year"].astype("int16")

        buf = BytesIO()
        out.to_parquet(buf, engine="pyarrow", compression="snappy", index=False)
        buf.seek(0)

        key = f"{S3_EVENTS_PREFIX}country_id={int(cid)}/events.parquet"
        s3_client.put_object(Bucket=args.bucket, Key=key, Body=buf.getvalue())
        uploaded += 1

    print(f"Uploaded {uploaded} country partitions to S3")

    # 6. Compute baselines
    print("\nComputing baselines...")
    compute_baselines(df, args.bucket, s3_client)

    print("\n✓ Done!")


if __name__ == "__main__":
    main()
