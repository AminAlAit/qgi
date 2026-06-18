# DSCDI Finder for AWS Batch (Phase 5 v0.0b Stage F).
#
# Wraps the pure-function library at src/dscdi_finder.py with the
# orchestration in src/run_dscdi_entrypoint.py. Built for linux/arm64
# (Graviton Spot) to match the qgi-pipeline-b-spot-environment compute
# environment.
#
# Mirrors batch/scdi-finder/Dockerfile exactly except for the entrypoint.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./src/ .

CMD ["python", "run_dscdi_entrypoint.py"]
