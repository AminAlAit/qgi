# V-Dem ingest Fargate Spot job (#494 step 4).
#
# Wraps qgi-data/scripts/ingest_vdem.py for the Step Functions
# annual-refresh pipeline:
#   1. Human drops a V-Dem ZIP at s3://qgi-data-lake-*/vdem-staging/incoming/
#   2. S3 EventBridge triggers SF
#   3. Lambda unzip step extracts the CSV and writes it to a known S3 key
#   4. THIS Batch job downloads the unzipped CSV, runs ingest_vdem.py,
#      uploads per-indicator parquets, runs MSCK REPAIR
#   5. SNS notification on success/failure
#
# Sibling of:
#   - batch/indicator-fetcher/         WB API fetcher
#   - batch/indicator-fetcher-fao/     FAOSTAT bulk fetcher
#   - batch/scdi-finder/               Phase 2 SCDI Batch job
#
# Build context note: this Dockerfile expects three artifacts in
# `_staged/` that come from the qgi-data repo at build time:
#   _staged/ingest_vdem.py         (the worker script)
#   _staged/vdem_country_map.yaml  (alpha-3 → qgi-canonical name map)
#   _staged/control-surface.xlsx   (indicator catalog with vdem_indicators sheet)
# These are NOT committed to qgi-pipeline. The CI workflow checks out
# qgi-data alongside qgi-pipeline and copies them into _staged/ before
# `docker build`. For local builds, run the helper script:
#   ./scripts/stage-qgi-data-assets.sh ../qgi-data
# (See README.md in this directory.)
FROM --platform=linux/arm64 public.ecr.aws/lambda/python:3.13-arm64 AS base

# Lambda base image gives us same Python + ARM64 wheel binaries as the
# other Batch images. We don't use the Lambda runtime — override
# ENTRYPOINT to run our entry script.

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Layer-cache discipline (PR #8 review item 1): the qgi-data-owned
# artifacts (especially `control-surface.xlsx`, a binary blob) change
# less frequently than the orchestrator code in src/. Putting the
# staged artifacts first keeps the heavier layer cached across
# orchestrator-only iterations. Reverse-ordered from the FAO sibling
# because FAO has no staged-from-another-repo dependency.
COPY _staged/ingest_vdem.py        ./ingest_vdem.py
COPY _staged/vdem_country_map.yaml ./registries/vdem_country_map.yaml
COPY _staged/control-surface.xlsx  ./indicators/control-surface.xlsx

# qgi-pipeline-owned code — entry orchestrator
COPY src/ ./src/

# Set env so ingest_vdem.py's resolve_xlsx_path() finds the catalog
# without needing --xlsx-path passed explicitly.
ENV INDICATOR_CATALOG_XLSX_PATH=/app/indicators/control-surface.xlsx

# qgi-data version stamp — LABEL is populated by the CI staging step via
# `--build-arg QGI_DATA_SHA=$(git -C __qgi-data rev-parse HEAD)` and is
# what makes a built image traceable back to the exact qgi-data commit
# whose artifacts it bundles. Without this, the ECR image tag (which is
# qgi-pipeline's GITHUB_SHA) carries zero info about the bundled
# qgi-data version. Default `unknown` lets local builds via
# `stage-qgi-data-assets.sh` skip the build-arg without erroring.
ARG QGI_DATA_SHA=unknown
LABEL qgi.data.sha=$QGI_DATA_SHA
ENV QGI_DATA_SHA=$QGI_DATA_SHA

ENTRYPOINT ["python", "-u", "/app/src/run_ingest.py"]
