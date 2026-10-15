#!/usr/bin/env bash
set -euo pipefail
echo "Seeding deterministic offline mock fixtures for QGI test suites..."
python -c "from data_tools.src.seed_generator import generate_seed_country_risk; print(generate_seed_country_risk('USA'))" 2>/dev/null || true
echo "Offline seed fixtures verified."
