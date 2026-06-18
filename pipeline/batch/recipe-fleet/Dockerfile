# Recipe-fleet Batch container — arm64 / Graviton, Python 3.13.
#
# Design doc: docs/specs/internal/ops/ml-track/aws-recipe-fleet-design.md §7
# Build: docker buildx build --platform linux/arm64 -t qgi-recipe-fleet .
#
# Vendoring model for qgi-ml scripts:
#   The scripts/run_f_ml_1_poc.py + scripts/compute_*.py + src/ tree are
#   copied verbatim from the qgi-ml repo at CI build time via the Dockerfile
#   COPY instructions below. The CI/CD workflow (ecr-push.yml) must check out
#   qgi-ml as a sibling directory alongside qgi-pipeline and set the Docker
#   build context to the repo root, OR use a multi-repo checkout and adjust
#   COPY paths accordingly.
#
#   Build context expected layout (relative to docker build context root):
#     qgi-pipeline/batch/recipe-fleet/   <- this Dockerfile
#     qgi-pipeline/batch/recipe-fleet/recipe_fleet_entrypoint.py
#     qgi-ml/scripts/                    <- walked scripts + run driver
#     qgi-ml/src/                        <- shared Python modules
#
#   If CI checks out both repos side by side, build with:
#     docker buildx build \
#       --platform linux/arm64 \
#       --file qgi-pipeline/batch/recipe-fleet/Dockerfile \
#       --build-context qgi-ml=../qgi-ml \
#       -t <ecr-url>/qgi-recipe-fleet:latest \
#       qgi-pipeline/batch/recipe-fleet/
#
# Runtime entrypoint:
#   python /app/recipe_fleet_entrypoint.py
#   (configured in Batch job definition command override)

# ---- build args (traceability) -------------------------------------------
# QGI_ML_SHA is stamped at CI build time by ecr-push.yml (#130) so every
# image in ECR is traceable to the exact qgi-ml commit it bundles.
# Pass with: docker buildx build --build-arg QGI_ML_SHA="$(git -C __qgi-ml rev-parse HEAD)" ...
ARG QGI_ML_SHA=unknown

# ---- base ----------------------------------------------------------------
# python:3.13-slim for arm64 is the same convention as the scdi-finder
# Dockerfile in qgi-pipeline/batch/scdi-finder/Dockerfile (which uses 3.12).
# Updated to 3.13 to match the Lambda runtime and the Python 3.13 convention
# in the platform conventions.
FROM --platform=linux/arm64 python:3.13-slim

# BuildKit scope rule: an ARG declared BEFORE FROM lives in the global scope and is
# visible to FROM's image-ref expansion, but is NOT visible to instructions inside
# the build stage unless RE-DECLARED after FROM. Without this line the LABEL below
# would always read the literal empty string (or fall back to the global default
# `unknown`) regardless of what `--build-arg QGI_ML_SHA=...` the CI passes — the
# traceability claim would silently fail. Re-declaring here brings the build-arg
# into stage scope; the LABEL then records the real qgi-ml HEAD. (QA PR #42 nit.)
ARG QGI_ML_SHA=unknown

# Stamp the qgi-ml version into the image so `docker inspect` or ECR
# image metadata can be used to trace which qgi-ml commit is bundled.
LABEL qgi_ml_sha=$QGI_ML_SHA

# ---- system dependencies -------------------------------------------------
# libgomp1 is required by XGBoost for OpenMP (even with n_jobs=1 the lib
# links against it). psutil needs no extra libs on Debian slim.
RUN apt-get update && \
    apt-get install -y --no-install-recommends libgomp1 && \
    rm -rf /var/lib/apt/lists/*

# ---- Python dependencies -------------------------------------------------
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- application code ----------------------------------------------------
# Copy the entrypoint (lives alongside this Dockerfile in qgi-pipeline)
COPY recipe_fleet_entrypoint.py .

# Copy qgi-ml scripts tree (checked out as sibling at CI build time).
# See build context note above. Adjust COPY source paths if your CI
# build context differs.
COPY --from=qgi-ml scripts/ /app/scripts/
COPY --from=qgi-ml src/ /app/src/

# FIX 2 — copy positives / shape_inputs_v2 data into the image.
# run_f_ml_1_poc.py resolves --positives-csv from this path when passed
# explicitly. extract_shap_importances.py hard-codes REPO_ROOT/"data"/
# "shape_inputs_v2"/{recipe}/positives.csv where REPO_ROOT = /app, so
# this directory MUST exist in the image at /app/data/shape_inputs_v2/.
# The data is small and version-controlled in qgi-ml (a few CSV files per
# recipe); baking it into the image means no S3 fetch is needed for it.
COPY --from=qgi-ml data/shape_inputs_v2/ /app/data/shape_inputs_v2/

# Make scripts importable as top-level modules (run_f_ml_1_poc.py uses
# REPO_ROOT / "scripts" and REPO_ROOT / "src" path manipulation internally,
# so we also set PYTHONPATH to /app/scripts and /app/src for any direct
# imports).
ENV PYTHONPATH="/app/scripts:/app/src:/app"

# Pin every BLAS/OpenMP backend to a single thread process-wide. The #961 parallel grid runs
# N joblib worker threads, each of which would otherwise spin up its own full BLAS thread pool
# (N×N oversubscription → the parallel walk ran slower than one laptop core on the canary).
# Set BEFORE the Python process imports numpy/xgboost so the pools are created already-capped;
# threadpoolctl in run_f_ml_1_poc.py is the per-fold belt-and-suspenders. Bit-identical for the
# seeded XGBoost fleet path (the canary re-run confirms selection+AUC unchanged, §2.5).
ENV OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    VECLIB_MAXIMUM_THREADS=1

# ---- entrypoint ----------------------------------------------------------
# Batch job definition overrides this with:
#   "command": ["python", "/app/recipe_fleet_entrypoint.py"]
# The CMD here is a sane default for local docker run testing.
CMD ["python", "/app/recipe_fleet_entrypoint.py"]
