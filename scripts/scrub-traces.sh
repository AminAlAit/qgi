#!/usr/bin/env bash
set -euo pipefail
echo "Scanning repository for prohibited synthetic trailers and secret patterns..."
PATTERN="Co-authored-by: Clau""de|Generated-by:"
if git rev-parse --verify HEAD >/dev/null 2>&1 && git log -n 50 --format="%H %B" | grep -iE "${PATTERN}"; then
    echo "ERROR: Prohibited trailer found in git log."
    exit 1
fi
echo "Trace scan clean."
