"""
conftest.py for pipeline-recipe-engine-finalize unit tests.

Sets QGI_TEST_ALLOW_LIST so the lambda module's #591 allow-list cache
is pre-populated at module import. Without this, tests that exercise
write_recipes_aggregated_table() with generic-MagicMock s3 patches would
trigger _load_indicator_allow_list() → json.loads on a MagicMock → TypeError.

Test-specific overrides (test_591_allow_list_filter.py) clear/repopulate
the cache directly per-test in their own fixtures.

Each test file loads the lambda under its own importlib name and the
module instance is NOT registered in sys.modules — so a per-test fixture
can't iterate to find it. Setting the env var BEFORE any test import is
the only injection point that works across all instances.
"""

from __future__ import annotations

import os

# Test-default seed: 3 V-Dem catalog ids known to be in the live allow-list.
# Sufficient for SQL-shape assertions; ignored by tests that don't care.
os.environ.setdefault("QGI_TEST_ALLOW_LIST", "276,277,287")
os.environ.setdefault("S3_BUCKET", "test-bucket")
