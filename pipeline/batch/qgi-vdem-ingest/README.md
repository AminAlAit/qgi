# qgi-vdem-ingest

V-Dem ingest Fargate Spot job (#494 step 4). Wraps `qgi-data/scripts/ingest_vdem.py` for the Step Functions annual-refresh pipeline.

## Pipeline position

```
[human drops V-Dem ZIP at s3://qgi-data-lake-*/vdem-staging/incoming/]
            │
            ▼
   S3 EventBridge trigger
            │
            ▼
  Step Functions execution (#494 step 6)
            │
   ┌────────┼────────┐
   ▼        ▼        ▼
[unzip   [THIS    [SNS
 Lambda]  Batch]   notify]
            │
            ▼
   per-indicator parquet
   in qgi_data.indicators
```

- **Unzip Lambda** (#494 step 5, sibling): extracts the V-Dem CSV from the uploaded ZIP, writes to a known S3 key
- **THIS Batch job**: downloads the unzipped CSV, runs `ingest_vdem.py`, uploads parquets, runs `MSCK REPAIR`
- **SNS notify**: success/failure email to `qgintelligence@gmail.com`

## Build context — the staging step

This Dockerfile expects three artifacts in `_staged/` that come from `qgi-data` at build time:

```
_staged/
├── ingest_vdem.py         # qgi-data/scripts/ingest_vdem.py
├── vdem_country_map.yaml  # qgi-data/registries/vdem_country_map.yaml
└── control-surface.xlsx   # qgi-data/indicators/control-surface.xlsx
```

These are NOT committed to qgi-pipeline (`_staged/` is `.gitignore`'d). The CI workflow (`.github/workflows/ecr-push.yml`) checks out `qgi-data` alongside `qgi-pipeline` and copies them into place before running `docker build`.

For local builds:

```bash
cd batch/qgi-vdem-ingest/
./stage-qgi-data-assets.sh ../../../qgi-data
docker build -t qgi-vdem-ingest:local .
```

## Runtime contract — env vars

The Step Functions definition sets these on the Batch job:

| Env var | Required | Description |
|---|---|---|
| `S3_BUCKET` | yes | Data lake bucket (e.g. `qgi-data-lake-771606957899`) |
| `VDEM_CSV_S3_KEY` | yes | S3 key of the unzipped V-Dem CSV in `S3_BUCKET` |
| `AWS_REGION` | yes | `eu-central-1` |
| `ATHENA_WORKGROUP` | no | Default `QGI-Lambda-Workgroup` |
| `DRY_RUN` | no | `"true"` to skip S3 writes (validation-only) |
| `SKIP_REPAIR` | no | `"true"` to skip `MSCK REPAIR TABLE qgi_data.indicators` |

The Dockerfile also sets `INDICATOR_CATALOG_XLSX_PATH=/app/indicators/control-surface.xlsx` so `ingest_vdem.py`'s `resolve_xlsx_path()` finds the catalog without `--xlsx-path` being passed explicitly.

## Exit codes

- `0` — success
- `1` — env-var validation or bundled-artifact missing
- `2` — S3 download of the V-Dem CSV failed
- `3+` — propagated from `ingest_vdem.py`

## Cost — instance-type discipline

Per the Batch instance-type rule, this job's compute environment is restricted to `m7g.xlarge` / `m7g.2xlarge` only. Defined in the Terraform module (#494 step 6, `qgi-infra/modules/pipeline/vdem.tf`).

Annual cadence + ARM64 + Fargate Spot keeps the per-run cost negligible (single-digit USD per V-Dem release).

## Tests

Unit tests for `run_ingest.py` (env-var translation + worker invocation) live in `qgi-pipeline/tests/unit/qgi-vdem-ingest/`. Run with:

```bash
cd qgi-pipeline/
python -m pytest tests/unit/qgi-vdem-ingest/ -v
```

The worker script's tests (`ingest_vdem.py` correctness, XLSX loader behaviour) live in `qgi-data/tests/`. Both suites must pass before this image ships.
