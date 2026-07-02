"""Root pytest conftest — adds lambdas/ to sys.path for shared-module imports.

The deploy workflow at .github/workflows/deploy-lambdas.yml copies
lambdas/_shared/ into each Lambda's bundle before zipping, so production
Lambdas import via `from _shared.pattern_tier import ...` with _shared/
at the zip root. In test mode the Lambda module is loaded via
importlib.util.spec_from_file_location, which uses the test-runner's
sys.path — _shared/ is at lambdas/_shared/, not on sys.path by default.

This conftest adds the lambdas/ directory to sys.path so the same
import statement resolves identically in tests and in production. The
prepend ordering (insert at position 0) ensures the test environment's
_shared/ is found before any same-named module that might live elsewhere.
"""

from __future__ import annotations

import sys
from pathlib import Path

_LAMBDAS_DIR = Path(__file__).resolve().parent.parent / "lambdas"

if str(_LAMBDAS_DIR) not in sys.path:
    sys.path.insert(0, str(_LAMBDAS_DIR))
