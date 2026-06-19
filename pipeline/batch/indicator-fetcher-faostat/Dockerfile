# FAOSTAT bulk-download Fargate Spot fetcher (enrichment stage 2).
#
# Spec-driven: src/specs.json carries all FAOSTAT indicators; adding a new
# indicator requires only a JSON entry + image rebuild.  No code change.
#
# One task per FS-xxx / SDGB-xxx / ET-xxx / TC-xxx indicator.  Downloads the
# relevant bulk ZIP (2 MB – 278 MB), filters to the indicator, writes Parquet
# to the same parquet-completed layout as the WB and ILOSTAT fetchers so
# Phase 2 SCDI is provider-agnostic.
#
# BUILD CONTEXT = qgi-pipeline/batch/  (NOT this dir) so the shared base can
# be COPYed in:
#     docker build --platform=linux/arm64 \
#       -f indicator-fetcher-faostat/Dockerfile \
#       -t <ecr>/qgi-pipeline-a-indicator-fetcher-faostat:<tag> \
#       qgi-pipeline/batch
FROM --platform=linux/arm64 public.ecr.aws/lambda/python:3.13-arm64 AS base

WORKDIR /app

COPY indicator-fetcher-faostat/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Shared base library (sibling dir) + this fetcher's source + baked specs
COPY _fetcher_base/qgi_fetcher_base.py /app/qgi_fetcher_base.py
COPY indicator-fetcher-faostat/src/ ./src/

ENTRYPOINT ["python", "-u", "/app/src/fetch_faostat.py"]
