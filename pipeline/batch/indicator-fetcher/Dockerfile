# Phase 1 Fargate Spot fetcher — one task per indicator (#FAR-1)
#
# Multi-stage build to keep the runtime image small (<200 MB) so Fargate
# Spot pulls quickly. Uses Python slim (Debian-based) instead of Alpine
# because pyarrow wheels don't ship for musl libc and source-building it
# would take 10+ minutes per build.
FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /opt/qgi

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ ./src/

# Run as non-root for defense in depth (Fargate doesn't enforce this but
# it's free hygiene)
RUN useradd --system --no-create-home --uid 1001 qgi && \
    chown -R qgi:qgi /opt/qgi
USER qgi

# Single entrypoint — the script reads everything from env vars
ENTRYPOINT ["python", "-u", "src/fetch_one.py"]
