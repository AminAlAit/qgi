#!/usr/bin/env bash
# stage-qgi-data-assets.sh — copy the qgi-data files this Dockerfile
# expects in `_staged/` into place, for local docker builds.
#
# Usage:
#   ./stage-qgi-data-assets.sh <path-to-qgi-data-checkout>
#
# Example (sibling repos):
#   ./stage-qgi-data-assets.sh ../../../qgi-data
#
# CI uses an equivalent inline `cp` step in `.github/workflows/ecr-push.yml`
# (see the `qgi-vdem-ingest` build steps there). This script is for
# local dev only — running `docker build` in this directory without
# first running this script will fail at COPY time.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <path-to-qgi-data-checkout>" >&2
  exit 1
fi

QGI_DATA_ROOT="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGED_DIR="${SCRIPT_DIR}/_staged"

# Sanity check the source paths
for rel_path in \
    "scripts/ingest_vdem.py" \
    "registries/vdem_country_map.yaml" \
    "indicators/control-surface.xlsx"; do
  if [[ ! -f "${QGI_DATA_ROOT}/${rel_path}" ]]; then
    echo "[error] missing in qgi-data checkout: ${rel_path}" >&2
    echo "[error] expected at: ${QGI_DATA_ROOT}/${rel_path}" >&2
    exit 1
  fi
done

mkdir -p "${STAGED_DIR}"

cp "${QGI_DATA_ROOT}/scripts/ingest_vdem.py"               "${STAGED_DIR}/ingest_vdem.py"
cp "${QGI_DATA_ROOT}/registries/vdem_country_map.yaml"     "${STAGED_DIR}/vdem_country_map.yaml"
cp "${QGI_DATA_ROOT}/indicators/control-surface.xlsx"      "${STAGED_DIR}/control-surface.xlsx"

echo "[stage] copied 3 artifacts from ${QGI_DATA_ROOT} into ${STAGED_DIR}"
ls -lh "${STAGED_DIR}"
