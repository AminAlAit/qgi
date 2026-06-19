# ILOSTAT SDMX Fargate Spot fetcher (enrichment stage 2).
#
# One task per IL-xx indicator. Pulls the ILOSTAT SDMX REST API and writes
# parquet-completed via the shared base, so Phase 2 SCDI / recipe-fleet read it
# provider-agnostically.
#
# BUILD CONTEXT = qgi-pipeline/batch/  (NOT this dir) so the shared base can be
# COPYed in:
#     docker build --platform=linux/arm64 \
#       -f indicator-fetcher-ilostat/Dockerfile \
#       -t <ecr>/qgi-pipeline-a-indicator-fetcher-ilostat:<tag> \
#       qgi-pipeline/batch
FROM --platform=linux/arm64 public.ecr.aws/lambda/python:3.13-arm64 AS base

WORKDIR /app

COPY indicator-fetcher-ilostat/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# shared base library (sibling dir) + this fetcher's source
COPY _fetcher_base/qgi_fetcher_base.py /app/qgi_fetcher_base.py
COPY indicator-fetcher-ilostat/src/ ./src/

ENTRYPOINT ["python", "-u", "/app/src/fetch_ilostat.py"]
