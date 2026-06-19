# UCDP Fargate Spot fetcher (enrichment stage 2).
#
# One task per UC-xx indicator (GED-derived: UC-01 battle deaths, UC-04 one-sided).
# Writes parquet-completed via the shared base.
#
# BUILD CONTEXT = qgi-pipeline/batch/ :
#     docker build --platform=linux/arm64 \
#       -f indicator-fetcher-ucdp/Dockerfile \
#       -t <ecr>/qgi-pipeline-a-indicator-fetcher-ucdp:<tag> \
#       qgi-pipeline/batch
FROM --platform=linux/arm64 public.ecr.aws/lambda/python:3.13-arm64 AS base

WORKDIR /app

COPY indicator-fetcher-ucdp/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY _fetcher_base/qgi_fetcher_base.py /app/qgi_fetcher_base.py
COPY indicator-fetcher-ucdp/src/ ./src/

ENTRYPOINT ["python", "-u", "/app/src/fetch_ucdp.py"]
