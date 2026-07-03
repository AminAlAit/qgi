"""
Contract tests for pipeline-recipe-engine (#158 Layer 1).

Regression guard for the 2026-04-08 Phase 5b outage: the Recipe Engine ran a
single monolithic CTAS that scanned 43.7 GB of `patterns` with no partition
filter on `country_a_id`, reliably hitting Athena's 30-min DML cap and
blocking #146 dashboard JSON generation.

The #158 Layer 1 fix splits the work into one CTAS for the first country_a_id
(to create the table shell + first partition) plus per-country INSERT INTOs
for the remaining ids, dispatched in parallel waves with a concurrency cap.

These tests assert the query-splitting and per-country partition-filter
invariants hold, so we cannot silently regress to a full-table scan. They
also verify the fail-loud semantics on any per-country failure and the
concurrency cap is honored.

Tests are offline — boto3 is stubbed via importlib (mirroring the
pipeline-a-completer / pipeline-c-checker pattern). No AWS calls.
"""

import importlib.util
import os
import re
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

_LAMBDAS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "lambdas"
_LAMBDA_FILE = _LAMBDAS_DIR / "pipeline-recipe-engine" / "lambda_function.py"


# ---------------------------------------------------------------------------
# Mock Athena: records every start_query_execution call and drives the
# get_query_execution state machine from a per-query config.
# ---------------------------------------------------------------------------


class FakeAthena:
    def __init__(self, distinct_country_ids, per_query_state=None, running_polls=0, count_result="123"):
        """
        distinct_country_ids: list returned by the `SELECT DISTINCT country_a_id
            FROM qgi_data.patterns` query.
        per_query_state: optional dict {country_a_id: 'SUCCEEDED'|'FAILED'} to
            override the default SUCCEEDED state for the matching INSERT query.
        running_polls: how many RUNNING polls to report before flipping each
            per-country INSERT query to its terminal state. Used by the
            concurrency test to force the launcher to fill up before drains.
        count_result: value returned by the count(*) query.
        """
        self._counter = 0
        self.started_queries = []  # list of (query_id, sql)
        self.distinct_country_ids = distinct_country_ids
        self.per_query_state = per_query_state or {}
        self.running_polls = running_polls
        self.count_result = count_result
        # poll counter per query id (for the RUNNING→SUCCEEDED ramp)
        self._poll_counts = {}
        # track currently in-flight (non-terminal) per-country INSERT queries
        self._in_flight_ids = set()
        self.max_in_flight = 0
        # sql content per query_id so get_query_execution can derive the
        # per-country state override
        self._qid_to_sql = {}

    def start_query_execution(self, **kwargs):
        self._counter += 1
        qid = f"q{self._counter}"
        sql = kwargs.get("QueryString", "")
        self.started_queries.append((qid, sql))
        self._qid_to_sql[qid] = sql
        if self._is_per_country_insert(sql):
            self._in_flight_ids.add(qid)
            self.max_in_flight = max(self.max_in_flight, len(self._in_flight_ids))
        return {"QueryExecutionId": qid}

    @staticmethod
    def _is_per_country_insert(sql):
        return "INSERT INTO qgi_data.recipes" in sql

    @staticmethod
    def _extract_country_filter(sql):
        m = re.search(r"p\.country_a_id\s*=\s*(\d+)", sql)
        return int(m.group(1)) if m else None

    def get_query_execution(self, QueryExecutionId):
        qid = QueryExecutionId
        sql = self._qid_to_sql.get(qid, "")
        self._poll_counts[qid] = self._poll_counts.get(qid, 0) + 1

        if self._is_per_country_insert(sql):
            if self._poll_counts[qid] <= self.running_polls:
                return {
                    "QueryExecution": {
                        "Status": {"State": "RUNNING"},
                        "Statistics": {},
                    }
                }
            # terminal — remove from in-flight if still present
            self._in_flight_ids.discard(qid)
            cid = self._extract_country_filter(sql)
            state = self.per_query_state.get(cid, "SUCCEEDED")
            return {
                "QueryExecution": {
                    "Status": {
                        "State": state,
                        "StateChangeReason": "mocked failure" if state != "SUCCEEDED" else "",
                    },
                    "Statistics": {
                        "DataScannedInBytes": 200 * 1024 * 1024,
                        "EngineExecutionTimeInMillis": 2000,
                    },
                }
            }
        # Synchronous non-INSERT query (DROP, DISTINCT, CTAS, COUNT, ...)
        return {
            "QueryExecution": {
                "Status": {"State": "SUCCEEDED"},
                "Statistics": {},
            }
        }

    def get_query_results(self, QueryExecutionId, NextToken=None):
        sql = self._qid_to_sql.get(QueryExecutionId, "")
        # DISTINCT country_a_id FROM qgi_data.patterns
        if "DISTINCT country_a_id" in sql and "patterns" in sql:
            rows = [{"Data": [{"VarCharValue": "country_a_id"}]}] + [
                {"Data": [{"VarCharValue": str(i)}]} for i in self.distinct_country_ids
            ]
            return {"ResultSet": {"Rows": rows}}
        # count(*) FROM qgi_data.recipes
        if "count(*)" in sql and "qgi_data.recipes" in sql and "GROUP BY" not in sql:
            return {
                "ResultSet": {
                    "Rows": [
                        {"Data": [{"VarCharValue": "cnt"}]},
                        {"Data": [{"VarCharValue": self.count_result}]},
                    ]
                }
            }
        # event_category, count(*) … GROUP BY event_category
        if "event_category" in sql and "GROUP BY event_category" in sql:
            return {
                "ResultSet": {
                    "Rows": [
                        {"Data": [{"VarCharValue": "event_category"}, {"VarCharValue": "cnt"}]},
                        {"Data": [{"VarCharValue": "protest"}, {"VarCharValue": "10"}]},
                    ]
                }
            }
        # Dashboard queries — return just the header row (empty result set
        # is fine for shape tests; the handler still produces JSON with [] ).
        return {"ResultSet": {"Rows": [{"Data": [{"VarCharValue": ""}]}]}}


def _load_module(fake_athena):
    """Load pipeline-recipe-engine/lambda_function.py with boto3 stubbed."""
    s3_client = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = iter([{"Contents": []}])
    s3_client.get_paginator.return_value = paginator
    s3_client.put_object = MagicMock()
    s3_client.delete_objects = MagicMock()

    def client_factory(name, *a, **kw):
        if name == "athena":
            return fake_athena
        if name == "s3":
            return s3_client
        return MagicMock()

    boto3_stub = types.ModuleType("boto3")
    boto3_stub.client = MagicMock(side_effect=client_factory)
    boto3_stub.resource = MagicMock(return_value=MagicMock())

    env = {
        "S3_BUCKET": "test-bucket",
        "ATHENA_DATABASE": "qgi_data",
        "ATHENA_WORKGROUP": "QGI-Lambda-Workgroup",
        # Make the test fast — no real sleeping between polls
        "RECIPE_ENGINE_POLL_INTERVAL": "0",
        "RECIPE_ENGINE_MAX_CONCURRENCY": "20",
    }
    # Also stub time.sleep to a no-op so the synchronous run_query polling
    # loop doesn't slow the test suite.
    fake_time = types.ModuleType("time")
    fake_time.sleep = lambda *_a, **_k: None
    fake_time.time = __import__("time").time

    with patch.dict(sys.modules, {"boto3": boto3_stub}), patch.dict(os.environ, env):
        # patch time.sleep AFTER module load, on the module itself
        spec = importlib.util.spec_from_file_location(
            "recipe_engine",
            str(_LAMBDA_FILE),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.time.sleep = lambda *_a, **_k: None
    return mod, s3_client


# ---------------------------------------------------------------------------
# Test 1: CTAS is split into per-country queries (one CTAS + N-1 INSERTs)
# ---------------------------------------------------------------------------


def test_splits_ctas_into_per_country_inserts():
    """With 3 distinct country_a_id values, the Recipe Engine must submit
    exactly 1 CTAS (for the first id) and 2 INSERT INTO queries (for the
    remaining ids) — NOT a single full-table CTAS.

    This is the headline regression guard: if anyone ever reverts to the
    pre-#158 single-CTAS shape, this test fails immediately.
    """
    fake = FakeAthena(distinct_country_ids=[1, 2, 3])
    mod, _s3 = _load_module(fake)
    mod.lambda_handler({"run_id": "test"}, None)

    queries = [sql for _qid, sql in fake.started_queries]
    ctas_queries = [q for q in queries if "CREATE TABLE qgi_data.recipes" in q]
    insert_queries = [q for q in queries if "INSERT INTO qgi_data.recipes" in q]

    assert len(ctas_queries) == 1, (
        f"expected exactly 1 CTAS (shell + first partition), got "
        f"{len(ctas_queries)}. Regression toward pre-#158 full-scan shape."
    )
    assert len(insert_queries) == 2, (
        f"expected 2 per-country INSERTs for remaining ids (2 and 3), got {len(insert_queries)}."
    )
    # Bonus: no CTAS without a country_a_id filter should ever be submitted
    for q in ctas_queries:
        assert "p.country_a_id = " in q, (
            "CTAS must include a partition filter (country_a_id). Unfiltered CTAS is the 43 GB full-scan bug."
        )


# ---------------------------------------------------------------------------
# Test 2: every per-country query carries a WHERE p.country_a_id = N filter
# ---------------------------------------------------------------------------


def test_per_country_insert_contains_partition_filter():
    """Every CTAS and INSERT query submitted by the Recipe Engine must
    contain `p.country_a_id = <N>` — that is the literal partition filter
    Athena needs for partition pruning. This test fails loudly if anyone
    drops it while refactoring the SELECT body.
    """
    fake = FakeAthena(distinct_country_ids=[7, 42, 99, 214])
    mod, _s3 = _load_module(fake)
    mod.lambda_handler({"run_id": "test"}, None)

    recipe_writing_queries = [
        sql
        for _qid, sql in fake.started_queries
        if "CREATE TABLE qgi_data.recipes" in sql or "INSERT INTO qgi_data.recipes" in sql
    ]
    assert len(recipe_writing_queries) == 4

    observed_ids = set()
    for q in recipe_writing_queries:
        m = re.search(r"p\.country_a_id\s*=\s*(\d+)", q)
        assert m is not None, (
            f"Recipe query missing partition filter 'p.country_a_id = N'. "
            f"This is the #158 regression guard. Query head: {q[:200]!r}"
        )
        observed_ids.add(int(m.group(1)))

    assert observed_ids == {7, 42, 99, 214}, (
        f"partition filters don't match DISTINCT country_a_id set. observed={observed_ids}"
    )


# ---------------------------------------------------------------------------
# Test 3: fail-loudly on any per-country failure, do not continue to dashboards
# ---------------------------------------------------------------------------


def test_fails_loudly_if_any_per_country_query_fails():
    """If any per-country INSERT query fails, the handler must raise before
    running the dashboard JSON step. We'd rather fail Phase 5b entirely
    than publish partial dashboard data that misleads downstream users.
    """
    fake = FakeAthena(
        distinct_country_ids=[1, 2, 3, 4],
        per_query_state={3: "FAILED"},
    )
    mod, s3_client = _load_module(fake)

    raised = False
    try:
        mod.lambda_handler({"run_id": "test"}, None)
    except RuntimeError as exc:
        raised = True
        assert "country_a_id" in str(exc) or "Recipe Engine" in str(exc)
    assert raised, "handler must raise RuntimeError when a per-country INSERT fails"

    # Dashboard JSON uploads must NOT have happened — we bailed before that step
    assert s3_client.put_object.call_count == 0, (
        f"dashboard JSONs must not be written when per-country queries fail; "
        f"saw {s3_client.put_object.call_count} put_object calls"
    )


# ---------------------------------------------------------------------------
# Test 4: on full success, the three dashboard JSONs are still written
# ---------------------------------------------------------------------------


def test_dashboard_json_step_still_runs_on_success():
    """Happy path: all per-country queries succeed, convergence view is
    created, and the three dashboard JSONs (ranking, early-warning,
    recipes-top50) are uploaded to s3://{bucket}/dashboard/. This is what
    unblocks #146.
    """
    fake = FakeAthena(distinct_country_ids=[1, 2, 3])
    mod, s3_client = _load_module(fake)
    result = mod.lambda_handler({"run_id": "test"}, None)

    assert result["statusCode"] == 200
    # Three dashboard JSONs should have been uploaded
    uploaded_keys = [
        call.kwargs.get("Key") or call.args[1] if call.args else None for call in s3_client.put_object.call_args_list
    ]
    uploaded_keys = [call.kwargs.get("Key") for call in s3_client.put_object.call_args_list]
    assert "dashboard/ranking.json" in uploaded_keys, f"ranking.json not uploaded; keys={uploaded_keys}"
    assert "dashboard/early-warning.json" in uploaded_keys, f"early-warning.json not uploaded; keys={uploaded_keys}"
    assert "dashboard/recipes-top50.json" in uploaded_keys, f"recipes-top50.json not uploaded; keys={uploaded_keys}"


# ---------------------------------------------------------------------------
# Test 5: concurrency cap is respected (≤ 20 INSERTs in flight)
# ---------------------------------------------------------------------------


def test_concurrency_limit_respected():
    """With 50 distinct country_a_id values, the launcher must never have
    more than MAX_CONCURRENT_INSERTS (20) per-country INSERT queries in
    flight at any point. This protects against hitting the Athena default
    workgroup concurrent-DML limit and getting ThrottlingException.

    We simulate slow queries by having get_query_execution return RUNNING
    for the first few polls so the launcher has a reason to fill up the
    queue before any drains.
    """
    fake = FakeAthena(
        distinct_country_ids=list(range(1, 51)),  # 50 countries
        running_polls=5,  # each query stays RUNNING for 5 polls before SUCCEEDED
    )
    mod, _s3 = _load_module(fake)
    mod.lambda_handler({"run_id": "test"}, None)

    # 50 countries → 1 CTAS (first) + 49 INSERTs
    insert_count = sum(1 for _qid, sql in fake.started_queries if "INSERT INTO qgi_data.recipes" in sql)
    assert insert_count == 49, f"expected 49 INSERTs, got {insert_count}"

    # The invariant: at no point should more than 20 INSERTs have been in flight
    assert fake.max_in_flight <= 20, (
        f"concurrency cap breached: max in-flight INSERT queries was "
        f"{fake.max_in_flight}, must be ≤ 20. Risk of Athena "
        f"ThrottlingException in production."
    )
    # And we should have actually exercised the cap (not trivially passed by
    # only ever having 1 query at a time)
    assert fake.max_in_flight >= 2, f"test did not exercise parallelism; max_in_flight={fake.max_in_flight}"


# ---------------------------------------------------------------------------
# Test 6: recipes_normalized view exists and uses a GLOBAL max CROSS JOIN
# ---------------------------------------------------------------------------
#
# #158 follow-up (QA review): the per-country INSERT approach causes
# `global_stats` in build_recipe_query to be computed per-partition, so the
# `pps` column written to recipes is NOT comparable across countries. The
# fix is to overlay a view that recomputes pps using a CROSS JOIN against
# a global max subquery over the full recipes table.
#
# This test is the regression guard: if anyone removes the view, removes
# the CROSS JOIN, or points convergence/top50 back at `qgi_data.recipes`
# directly, this test fails and we don't silently ship per-partition pps.


def test_recipes_normalized_view_with_global_max_cross_join():
    """The Recipe Engine must CREATE OR REPLACE VIEW qgi_data.recipes_normalized
    with a CROSS JOIN to (SELECT max(instance_count), max(indicator_count)
    FROM qgi_data.recipes) so pps is globally comparable.
    """
    fake = FakeAthena(distinct_country_ids=[1, 2, 3])
    mod, _s3 = _load_module(fake)
    mod.lambda_handler({"run_id": "test"}, None)

    view_queries = [
        sql for _qid, sql in fake.started_queries if "CREATE OR REPLACE VIEW qgi_data.recipes_normalized" in sql
    ]
    assert len(view_queries) == 1, (
        f"expected exactly 1 recipes_normalized view creation, got "
        f"{len(view_queries)}. #158 follow-up regression: pps would be "
        f"per-partition wrong without this view."
    )
    view_sql = view_queries[0]

    # Must contain a CROSS JOIN to a global max subquery. This is the
    # whole point of the fix.
    assert "CROSS JOIN" in view_sql, "recipes_normalized view must CROSS JOIN a global max subquery"
    assert "max(instance_count)" in view_sql, "recipes_normalized view must compute global max(instance_count)"
    assert "max(indicator_count)" in view_sql, "recipes_normalized view must compute global max(indicator_count)"
    # Must redefine pps via SELECT * EXCEPT — otherwise the base `pps`
    # column collides and the fix is a no-op.
    assert "EXCEPT (pps)" in view_sql, (
        "recipes_normalized view must use SELECT * EXCEPT (pps) to override "
        "the per-partition-wrong pps column from the base table"
    )


# ---------------------------------------------------------------------------
# Test 7: convergence + top50 queries read from recipes_normalized, NOT recipes
# ---------------------------------------------------------------------------


def test_convergence_and_top50_read_from_normalized_view():
    """The downstream consumers of `pps` (convergence view and top50
    dashboard query) must read from qgi_data.recipes_normalized, NOT from
    qgi_data.recipes directly. Otherwise they pick up the per-partition-
    wrong pps and the ranking is silently broken.
    """
    fake = FakeAthena(distinct_country_ids=[1, 2, 3])
    mod, _s3 = _load_module(fake)
    mod.lambda_handler({"run_id": "test"}, None)

    # Convergence view DDL
    cv_creates = [
        sql for _qid, sql in fake.started_queries if "CREATE OR REPLACE VIEW qgi_data.recipe_convergence" in sql
    ]
    assert len(cv_creates) == 1, "expected one convergence view creation"
    cv_sql = cv_creates[0]
    assert "FROM qgi_data.recipes_normalized" in cv_sql, (
        "convergence view must read from recipes_normalized, not recipes"
    )

    # Top50 dashboard query (runs during write_dashboard_jsons)
    top50_queries = [
        sql
        for _qid, sql in fake.started_queries
        if "composite_sort_key" in sql and "INNER JOIN qgi_data.recipe_convergence" in sql
    ]
    assert len(top50_queries) == 1, "expected one top50 dashboard query"
    top50_sql = top50_queries[0]
    assert "FROM qgi_data.recipes_normalized" in top50_sql, (
        "top50 dashboard query must read from recipes_normalized, not recipes, so r.pps is globally normalized"
    )
