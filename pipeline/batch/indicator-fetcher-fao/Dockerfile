# FAOSTAT Fargate Spot fetcher (#241 Phase B).
#
# One task per FAOSTAT domain. Downloads the domain bulk ZIP (50-200MB),
# parses it, filters to the QGI-tracked indicators for that domain,
# writes Parquet to the same S3 output layout as the WB fetcher so
# Phase 2 SCDI is provider-agnostic.
#
# Sibling of batch/indicator-fetcher/Dockerfile (the WB fetcher). Kept
# separate rather than unified because the FAOSTAT bulk-download pattern
# is structurally different enough (bulk CSV parse vs per-indicator API
# call) that a single image would be mostly branches — easier to reason
# about as two images with a shared schema at the Parquet-output layer.
FROM --platform=linux/arm64 public.ecr.aws/lambda/python:3.13-arm64 AS base

# Lambda base image is convenient even for Fargate (same Python + same
# ARM64 wheel binaries) but we don't use the Lambda runtime — override
# the ENTRYPOINT to run our fetcher script directly.

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENTRYPOINT ["python", "-u", "/app/src/fetch_domain.py"]
