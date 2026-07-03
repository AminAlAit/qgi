"""
Contract tests for pipeline-recipe-engine-list-formatter — length-bucket
axis edition (#534).

Verifies that the list-formatter correctly emits chunks keyed on
(country_a_id, event_category, length_bucket) instead of the legacy
pattern_tier (S/M/L/XL). All recipe-identity guarantees from the prior
edition still hold; the only output-shape change is `length_bucket`
replacing `pattern_tier` as the chunking dimension. The recipe rows
emitted by the chunked INSERTs continue to carry a `pattern_tier`
column (S/M/L/XL) for downstream/frontend consumers.

Coverage map
------------
1.  Seed is the chunk with the fewest patterns
2.  Tier-3 INSERTs carry country + category + length_bucket filters
3.  Seed SQL is CTAS, all others are INSERT
4.  Empty enumerate results raise RuntimeError
5.  cutoff_year is threaded into all generated SQL
6.  drop_partition_sql is a SELECT 1 no-op (Glue contention fix)
7.  partitions_total equals total chunk count
8.  All 71 taxonomy categories are representable
9.  All 12 length_buckets are representable
10. CTAS and INSERT have schema-identical SELECT column lists
11. Single-chunk input still produces a valid result
12. chunk_id format (cid_cat_bucket with '*' for None)
13. Tier-1 country emits 1 chunk (country filter only)
14. Tier-2 country chunks by category only
15. Tier-3 country chunks by (category, length_bucket)
16. Tier-4 country falls through to Tier-3 with warning
17. Tier boundaries: 99,999 → tier1; 100,000 → tier2
18. length_to_bucket boundary tests for all 12 buckets
19. length_to_bucket Python ↔ SQL CASE consistency (regression guard)
20. b58_plus uses `>=` filter (open-ended), not `BETWEEN`
21. Output recipe schema still contains pattern_tier column (S/M/L/XL)
22. Recipe-identity preserved: chunked GROUP BY produces same recipes as unchunked
23. Invalid length_bucket raises ValueError
"""

import importlib.util
import json
import os
import re
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_LAMBDAS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "lambdas"
_LAMBDA_FILE = _LAMBDAS_DIR / "pipeline-recipe-engine-list-formatter" / "lambda_function.py"

# ---------------------------------------------------------------------------
# Taxonomy: all 71 layer-3 category slugs (from qgi-data/events/taxonomy_hierarchy.json)
# ---------------------------------------------------------------------------
ALL_LAYER3_CATEGORIES = [
    "elections_and_voting",
    "government_formation",
    "constitutional_change",
    "decentralization_and_federalism",
    "democratic_transition",
    "executive_power_consolidation",
    "military_coup",
    "transitional_justice",
    "peacekeeping_and_peace_process",
    "interstate_war",
    "civil_war_and_insurgency",
    "terrorist_attack",
    "foreign_intervention",
    "ethnic_and_communal_conflict",
    "political_violence",
    "political_repression",
    "political_corruption",
    "human_rights_violation",
    "human_rights_reform",
    "military_policy_and_reform",
    "currency_crisis",
    "banking_and_financial_crisis",
    "economic_recession",
    "fiscal_policy_change",
    "monetary_policy_change",
    "economic_liberalization",
    "economic_nationalization",
    "economic_recovery",
    "economic_growth_milestone",
    "trade_agreement",
    "trade_dispute",
    "foreign_direct_investment",
    "industrial_policy",
    "sanctions_and_arms_embargo",
    "foreign_aid_and_development",
    "mass_protest",
    "labor_action",
    "social_policy_reform",
    "public_health_reform",
    "poverty_and_inequality_crisis",
    "religious_and_social_movement",
    "migration_and_refugees",
    "bilateral_treaty",
    "multilateral_agreement",
    "diplomatic_rupture",
    "territorial_disputes",
    "regional_integration",
    "earthquake",
    "flood_and_cyclone",
    "volcanic_eruption",
    "natural_disaster",
    "drought_and_famine",
    "epidemic_and_pandemic",
    "humanitarian_crisis",
    "water_crisis",
    "energy_policy",
    "oil_and_gas",
    "renewable_energy",
    "environmental_policy",
    "climate_agreement",
    "resource_conflict",
    "infrastructure_project",
    "urban_development",
    "education_reform",
    "education_and_research",
    "digital_policy",
    "technology_breakthrough",
    "cyberattack",
    "cultural_and_heritage",
    "sport_and_international_event",
    "agricultural_policy",
]
assert len(ALL_LAYER3_CATEGORIES) == 71, f"Expected 71 layer-3 categories, got {len(ALL_LAYER3_CATEGORIES)}"

ALL_LENGTH_BUCKETS = (
    "b03_07",
    "b08_12",
    "b13_17",
    "b18_22",
    "b23_27",
    "b28_32",
    "b33_37",
    "b38_42",
    "b43_47",
    "b48_52",
    "b53_57",
    "b58_plus",
)


# ---------------------------------------------------------------------------
# Test harness helpers
# ---------------------------------------------------------------------------


def _make_athena_results(chunks):
    """Build a mock get_query_results response.

    chunks: list of (country_a_id, event_category, length_bucket, count)
    """
    rows = [
        {
            "Data": [
                {"VarCharValue": "country_a_id"},
                {"VarCharValue": "event_category"},
                {"VarCharValue": "length_bucket"},
                {"VarCharValue": "pc"},
            ]
        }
    ]
    for cid, cat, bucket, cnt in chunks:
        rows.append(
            {
                "Data": [
                    {"VarCharValue": str(cid)},
                    {"VarCharValue": cat},
                    {"VarCharValue": bucket},
                    {"VarCharValue": str(cnt)},
                ]
            }
        )
    return {"ResultSet": {"Rows": rows}}


def _load_module(chunks):
    """Load list-formatter with mocked athena + s3 clients.

    chunks: list of (country_a_id, event_category, length_bucket, count)

    Returns (mod, s3_mock, athena_mock) — athena_mock exposed so tests can
    inspect the SQL sent to start_query_execution (#534 QA review CR-2).
    """
    athena_mock = MagicMock()
    athena_mock.start_query_execution.return_value = {"QueryExecutionId": "q-enum-1"}
    athena_mock.get_query_execution.return_value = {"QueryExecution": {"Status": {"State": "SUCCEEDED"}}}
    athena_mock.get_query_results.return_value = _make_athena_results(chunks)

    s3_mock = MagicMock()
    s3_mock._captured_items = None

    original_put = s3_mock.put_object

    def capture_put(**kwargs):
        body = kwargs.get("Body", "{}")
        s3_mock._captured_items = json.loads(body)
        return original_put(**kwargs)

    s3_mock.put_object = MagicMock(side_effect=capture_put)

    def client_factory(name, *a, **kw):
        if name == "athena":
            return athena_mock
        if name == "s3":
            return s3_mock
        return MagicMock()

    boto3_stub = types.ModuleType("boto3")
    boto3_stub.client = MagicMock(side_effect=client_factory)

    env = {
        "ATHENA_DATABASE": "qgi_data",
        "ATHENA_WORKGROUP": "test-wg",
        "S3_BUCKET": "test-bucket",
    }
    with patch.dict(sys.modules, {"boto3": boto3_stub}), patch.dict(os.environ, env):
        spec = importlib.util.spec_from_file_location(
            "list_formatter_chunked",
            str(_LAMBDA_FILE),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.time.sleep = lambda *_: None
    return mod, s3_mock, athena_mock


def _load_module_no_chunks():
    """Load module without invoking lambda_handler — for direct function tests."""
    return _load_module([(1, "elections_and_voting", "b03_07", 1)])[0]


# ===========================================================================
# Test 1: seed is the smallest-by-count chunk
# ===========================================================================


def test_seed_is_smallest_chunk():
    chunks = [
        (99, "elections_and_voting", "b03_07", 5),
        (42, "mass_protest", "b13_17", 200),
        (1, "economic_recession", "b58_plus", 50_000),
    ]
    mod, s3_mock, _ = _load_module(chunks)
    result = mod.lambda_handler({"run_id": "test"}, None)

    assert result["seed_country_id"] == 99, f"seed should be country 99 (5 patterns), got {result['seed_country_id']}"
    assert result["seed_pattern_count"] == 5


# ===========================================================================
# Test 2: Tier-3 INSERTs carry all three chunk filters
# ===========================================================================


def test_tier3_inserts_have_all_chunk_filters():
    """Tier-3 chunks (>1M, <10M total) emit chunks with country + category +
    length_bucket filters in the INSERT SQL.
    """
    chunks = [
        (5, "elections_and_voting", "b03_07", 1_500_000),
        (10, "mass_protest", "b13_17", 1_500_000),
        (20, "economic_recession", "b23_27", 2_500_000),
    ]
    mod, s3_mock, _ = _load_module(chunks)
    result = mod.lambda_handler({"run_id": "test"}, None)

    # Seed is the smallest Tier-3 chunk
    assert "p.country_a_id = 5" in result["seed_sql"]
    assert "elections_and_voting" in result["seed_sql"]
    # b03_07 → length BETWEEN 0 AND 7 (covers sub-floor defensive case per CR-1)
    assert "p.length BETWEEN 0 AND 7" in result["seed_sql"]

    for item in s3_mock._captured_items:
        cid = item["country_a_id"]
        cat = item["event_category"]
        bucket = item["length_bucket"]
        sql = item["insert_sql"]
        assert f"p.country_a_id = {cid}" in sql, f"INSERT chunk {cid}/{cat}/{bucket} missing country filter"
        assert f"'{cat}'" in sql, f"INSERT chunk {cid}/{cat}/{bucket} missing event_category filter"
        # Verify the bucket filter is present (BETWEEN or >= depending on bucket)
        if bucket == "b58_plus":
            assert "p.length >= 58" in sql, f"b58_plus chunk {cid}/{cat} should use >= 58, got: {sql[:300]}"
        else:
            # Lookup expected range
            from itertools import chain

            ranges = mod.BUCKET_RANGES
            lo, hi = ranges[bucket]
            assert f"p.length BETWEEN {lo} AND {hi}" in sql, (
                f"chunk {cid}/{cat}/{bucket} missing length BETWEEN {lo} AND {hi}"
            )


# ===========================================================================
# Test 3: seed is INSERT (post-#622, was CTAS pre-2026-05-16), rest are INSERT
# DDL is emitted alongside as the ddl_sql output field
# ===========================================================================


def test_seed_is_insert_and_ddl_is_emitted():
    chunks = [
        (5, "elections_and_voting", "b03_07", 1),
        (10, "mass_protest", "b13_17", 100),
        (20, "economic_recession", "b23_27", 200),
    ]
    mod, s3_mock, _ = _load_module(chunks)
    result = mod.lambda_handler({"run_id": "test"}, None)

    # #622: seed is now INSERT INTO, not CTAS. The cost-leak relocation
    # flipped this. CREATE TABLE must NOT appear in seed_sql — that was
    # the pattern that landed data in query_results/tables/<uuid>/.
    assert "INSERT INTO" in result["seed_sql"]
    assert "CREATE TABLE" not in result["seed_sql"]

    # #622: DDL is emitted as a separate top-level field so SF state
    # 5b.2 can run CREATE EXTERNAL TABLE before the seed INSERT.
    assert "ddl_sql" in result, "Lambda must emit ddl_sql field for SF 5b.3a"
    assert "CREATE EXTERNAL TABLE" in result["ddl_sql"]
    assert "qgi_data.recipes" in result["ddl_sql"]
    # The DDL must point at the stable prefix (not query_results/tables/).
    assert "pipeline-recipe-engine/output/recipes/" in result["ddl_sql"]
    assert "query_results/tables" not in result["ddl_sql"]

    # All Map-state inserts are also INSERT INTO (unchanged from pre-#622).
    for item in s3_mock._captured_items:
        assert "INSERT INTO" in item["insert_sql"]
        assert "CREATE TABLE" not in item["insert_sql"]


# ===========================================================================
# Test 4: empty enumerate results raise RuntimeError
# ===========================================================================


def test_empty_chunk_list_raises():
    mod, _, _ = _load_module([])
    with pytest.raises(RuntimeError) as exc_info:
        mod.lambda_handler({"run_id": "test"}, None)
    msg = str(exc_info.value).lower()
    assert "country_a_id" in msg or "combo" in msg or "no (" in msg


# ===========================================================================
# Test 5: cutoff_year is threaded into all SQL
# ===========================================================================


def test_cutoff_year_threaded_into_sql():
    chunks = [
        (5, "elections_and_voting", "b03_07", 1),
        (10, "mass_protest", "b13_17", 100),
    ]
    mod, s3_mock, _ = _load_module(chunks)
    result = mod.lambda_handler({"run_id": "test", "cutoff_year": 2020}, None)

    assert "2020" in result["seed_sql"], "seed SQL missing cutoff_year filter"
    for item in s3_mock._captured_items:
        assert "2020" in item["insert_sql"], f"INSERT chunk {item['chunk_id']} missing cutoff_year"


# ===========================================================================
# Test 6: drop_partition_sql is a no-op (post 2026-04-29 fix)
# ===========================================================================


def test_drop_partition_sql_is_noop():
    chunks = [
        (5, "elections_and_voting", "b03_07", 1),
        (5, "mass_protest", "b13_17", 50),
        (10, "economic_recession", "b23_27", 200),
    ]
    mod, s3_mock, _ = _load_module(chunks)
    mod.lambda_handler({"run_id": "test"}, None)

    for item in s3_mock._captured_items:
        sql = item["drop_partition_sql"]
        assert sql == "SELECT 1", (
            f"drop_partition_sql must be 'SELECT 1' (chunk {item['chunk_id']}); "
            f"got {sql!r}. Per-chunk Glue partition deletes cause AccessDenied "
            f"contention under parallel fan-out."
        )
        assert "DROP" not in sql.upper()
        assert "PARTITION" not in sql.upper()


# ===========================================================================
# Test 7: partitions_total equals total chunk count
# ===========================================================================


def test_partitions_total_equals_chunk_count():
    chunks = [
        (5, "elections_and_voting", "b03_07", 1),
        (10, "mass_protest", "b13_17", 100),
        (20, "economic_recession", "b23_27", 200),
        (30, "military_coup", "b58_plus", 300),
    ]
    mod, s3_mock, _ = _load_module(chunks)
    result = mod.lambda_handler({"run_id": "test"}, None)

    # All Tier-1 (each country has <100K patterns) → 1 chunk per country
    assert result["partitions_total"] == 4
    assert len(s3_mock._captured_items) == 3  # 4 total minus 1 seed


# ===========================================================================
# Test 8: all 71 taxonomy categories representable
# ===========================================================================


def test_all_71_categories_representable():
    """build_recipe_query must not raise for any of the 71 taxonomy categories."""
    mod = _load_module_no_chunks()

    for cat in ALL_LAYER3_CATEGORIES:
        try:
            sql = mod.build_recipe_query(
                cutoff_year=None,
                country_a_id=42,
                event_category=cat,
                length_bucket="b13_17",
                mode="insert",
            )
        except Exception as exc:
            raise AssertionError(f"build_recipe_query raised for category {cat!r}: {exc}") from exc
        assert f"'{cat}'" in sql, f"category {cat!r} not found in generated SQL"


# ===========================================================================
# Test 9: all 12 length_buckets representable
# ===========================================================================


def test_all_12_length_buckets_representable():
    mod = _load_module_no_chunks()

    for bucket in ALL_LENGTH_BUCKETS:
        sql = mod.build_recipe_query(
            cutoff_year=None,
            country_a_id=42,
            event_category="elections_and_voting",
            length_bucket=bucket,
            mode="insert",
        )
        # Each bucket should produce either a BETWEEN or >= filter on p.length
        if bucket == "b58_plus":
            assert "p.length >= 58" in sql, f"b58_plus missing >= filter in SQL: {sql[:400]}"
        else:
            lo, hi = mod.BUCKET_RANGES[bucket]
            assert f"p.length BETWEEN {lo} AND {hi}" in sql, f"bucket {bucket} missing 'BETWEEN {lo} AND {hi}' in SQL"


# ===========================================================================
# Test 10: CTAS and INSERT produce schema-identical SELECT column list
# ===========================================================================


def test_ctas_and_insert_same_select_columns():
    """The final SELECT column list must be the same in both modes (#163)."""
    mod = _load_module_no_chunks()

    ctas_sql = mod.build_recipe_query(
        country_a_id=1,
        event_category="elections_and_voting",
        length_bucket="b03_07",
        mode="ctas",
    )
    insert_sql = mod.build_recipe_query(
        country_a_id=1,
        event_category="elections_and_voting",
        length_bucket="b03_07",
        mode="insert",
    )

    shared_columns = [
        "recipe_id",
        "event_category",
        "pattern_id",
        "country_b_id",
        "country_a_name",
        "country_b_name",
        "start_year_a",
        "start_year_b",
        "length",
        "avg_correlation",
        "end_year_a",
        "end_year_b",
        "event_window",
        "event_year_a",
        "event_year_b",
        "event_title_a",
        "event_title_b",
        "indicator_count",
        "pattern_power_score",
        "instance_count",
        "pattern_tier",
        "median_lead_time_b",
        "min_lead_time_b",
        "max_lead_time_b",
        "median_lead_time_a",
        "pps",
        "contains_predicted",
        "country_a_id",
    ]
    for col in shared_columns:
        assert col in ctas_sql, f"Column {col!r} missing from CTAS SQL"
        assert col in insert_sql, f"Column {col!r} missing from INSERT SQL"


# ===========================================================================
# Test 11: single-chunk input produces a valid result
# ===========================================================================


def test_single_chunk_input():
    chunks = [(42, "elections_and_voting", "b03_07", 99)]
    mod, s3_mock, _ = _load_module(chunks)
    result = mod.lambda_handler({"run_id": "test"}, None)

    assert result["seed_country_id"] == 42
    assert result["seed_pattern_count"] == 99
    # #622: seed is INSERT INTO (was CTAS pre-2026-05-16).
    assert "INSERT INTO" in result["seed_sql"]
    assert "CREATE TABLE" not in result["seed_sql"]
    # #622: DDL is emitted even on a single-chunk run so SF state 5b.2
    # has something to execute on the first build.
    assert "ddl_sql" in result
    assert "CREATE EXTERNAL TABLE" in result["ddl_sql"]
    assert s3_mock._captured_items == []
    assert result["partitions_total"] == 1


# ===========================================================================
# Test 12: chunk_id format
# ===========================================================================


def test_chunk_id_format():
    """chunk_id format: '{cid}_{cat or *}_{bucket or *}'.

    Tier-1 chunks use '*' for both cat and bucket. Tier-2 uses '*' for bucket.
    Tier-3+ uses the full triple.
    """
    chunks = [
        (1, "elections_and_voting", "b03_07", 5),  # tier-1 country
        (2, "mass_protest", "b13_17", 10),  # tier-1 country
    ]
    mod, s3_mock, _ = _load_module(chunks)
    mod.lambda_handler({"run_id": "test"}, None)

    for item in s3_mock._captured_items:
        cat = item["event_category"] if item["event_category"] is not None else "*"
        bucket = item["length_bucket"] if item["length_bucket"] is not None else "*"
        expected = f"{item['country_a_id']}_{cat}_{bucket}"
        assert item["chunk_id"] == expected, f"chunk_id mismatch: expected {expected!r}, got {item['chunk_id']!r}"


# ===========================================================================
# Test 13: Tier-1 country emits one chunk
# ===========================================================================


def test_tier1_country_emits_one_chunk():
    """Country with <100K patterns emits a single combined chunk with no
    event_category or length_bucket filter.
    """
    chunks = [
        (5, "elections_and_voting", "b03_07", 25_000),
        (5, "mass_protest", "b13_17", 25_000),
        (5, "economic_recession", "b23_27", 25_000),
    ]
    mod, s3_mock, _ = _load_module(chunks)
    result = mod.lambda_handler({"run_id": "test"}, None)

    assert result["partitions_total"] == 1
    assert s3_mock._captured_items == []

    seed_sql = result["seed_sql"]
    assert "p.country_a_id = 5" in seed_sql
    assert "ea.category_normalized = '" not in seed_sql, "Tier-1 seed must not have event_category filter"
    # Length-bucket filter in the WHERE clause is wrapped in parens by
    # build_recipe_query: `(p.length BETWEEN ...)` or `(p.length >= 58)`.
    # The pattern_tier CASE in the SELECT also contains "p.length BETWEEN
    # 3 AND 8" etc. — that's the OUTPUT schema, not a chunking filter.
    # So pin to the leading paren to disambiguate.
    assert "(p.length BETWEEN" not in seed_sql, "Tier-1 seed must not have length_bucket WHERE filter"
    assert "(p.length >=" not in seed_sql, "Tier-1 seed must not have length_bucket WHERE filter"

    assert result["tier_distribution"]["tier1"] == 1


# ===========================================================================
# Test 14: Tier-2 country chunks by category only
# ===========================================================================


def test_tier2_country_chunks_by_category_only():
    """Country with 100K-1M patterns chunks by event_category, not by bucket."""
    # 6 combos for country 5: 3 categories × 2 buckets each. Sum = 600K (Tier-2)
    chunks = [
        (5, "elections_and_voting", "b03_07", 100_000),
        (5, "elections_and_voting", "b13_17", 100_000),
        (5, "mass_protest", "b03_07", 100_000),
        (5, "mass_protest", "b13_17", 100_000),
        (5, "economic_recession", "b03_07", 100_000),
        (5, "economic_recession", "b13_17", 100_000),
    ]
    mod, s3_mock, _ = _load_module(chunks)
    result = mod.lambda_handler({"run_id": "test"}, None)

    # 3 distinct categories → 3 chunks total
    assert result["partitions_total"] == 3
    assert len(s3_mock._captured_items) == 2

    for item in s3_mock._captured_items:
        assert item["event_category"] is not None, f"Tier-2 chunk must have event_category set: got {item}"
        assert item["length_bucket"] is None, f"Tier-2 chunk must have length_bucket=None: got {item}"
        sql = item["insert_sql"]
        assert "ea.category_normalized = '" in sql
        assert "(p.length BETWEEN" not in sql
        assert "(p.length >=" not in sql

    assert result["tier_distribution"]["tier2"] == 1


# ===========================================================================
# Test 15: Tier-3 country chunks by (category × length_bucket)
# ===========================================================================


def test_tier3_country_chunks_by_category_and_bucket():
    """Country with 1M-10M patterns chunks by (category × length_bucket)."""
    # 4 combos for country 5: 2 categories × 2 buckets. Sum = 4M (Tier-3)
    chunks = [
        (5, "elections_and_voting", "b03_07", 1_000_000),
        (5, "elections_and_voting", "b13_17", 1_000_000),
        (5, "mass_protest", "b03_07", 1_000_000),
        (5, "mass_protest", "b13_17", 1_000_000),
    ]
    mod, s3_mock, _ = _load_module(chunks)
    result = mod.lambda_handler({"run_id": "test"}, None)

    assert result["partitions_total"] == 4
    assert len(s3_mock._captured_items) == 3

    for item in s3_mock._captured_items:
        assert item["event_category"] is not None
        assert item["length_bucket"] is not None
        sql = item["insert_sql"]
        assert "ea.category_normalized = '" in sql
        assert "p.length BETWEEN" in sql or "p.length >=" in sql

    assert result["tier_distribution"]["tier3"] == 1


# ===========================================================================
# Test 16: Tier-4 falls through to Tier-3 with warning
# ===========================================================================


def test_tier4_country_falls_through_to_tier3_with_warning(caplog):
    import logging

    # 4 chunks × 3M each = 12M total → Tier-4 classification (>10M).
    # Per-chunk sizes intentionally kept < 5M to stay under the seed
    # pattern_count guard added in #622 — the test is asserting tier
    # CLASSIFICATION, not chunk size. (Pre-#622 these were 12-13M
    # synthetic numbers that tripped the new guard.)
    chunks = [
        (5, "elections_and_voting", "b03_07", 3_000_000),
        (5, "elections_and_voting", "b13_17", 3_000_000),
        (5, "mass_protest", "b03_07", 3_000_000),
        (5, "mass_protest", "b13_17", 3_000_000),
    ]
    mod, s3_mock, _ = _load_module(chunks)
    with caplog.at_level(logging.WARNING):
        result = mod.lambda_handler({"run_id": "test"}, None)

    assert result["partitions_total"] == 4
    assert result["tier_distribution"]["tier4"] == 1

    warning_messages = [r.message for r in caplog.records if r.levelname == "WARNING"]
    assert any("Tier-4" in msg for msg in warning_messages), (
        f"Expected a Tier-4 fall-through warning; got {warning_messages}"
    )


# ===========================================================================
# Test 17: Tier boundaries 99,999 → tier1 vs 100,000 → tier2
# ===========================================================================


def test_tier_boundary_99k_at_tier1():
    chunks = [
        (1, "elections_and_voting", "b03_07", 33_333),
        (1, "mass_protest", "b13_17", 33_333),
        (1, "economic_recession", "b23_27", 33_333),
    ]
    mod, s3_mock, _ = _load_module(chunks)
    result = mod.lambda_handler({"run_id": "test"}, None)

    assert result["tier_distribution"]["tier1"] == 1
    assert result["partitions_total"] == 1
    assert result["seed_pattern_count"] == 99_999
    assert "ea.category_normalized = '" not in result["seed_sql"]
    assert "(p.length BETWEEN" not in result["seed_sql"]


def test_tier_boundary_100k_at_tier2():
    # 100,002 total patterns — just over the 100K boundary
    chunks = [
        (1, "elections_and_voting", "b03_07", 33_334),
        (1, "mass_protest", "b13_17", 33_334),
        (1, "economic_recession", "b23_27", 33_334),
    ]
    mod, s3_mock, _ = _load_module(chunks)
    result = mod.lambda_handler({"run_id": "test"}, None)

    assert result["tier_distribution"]["tier1"] == 0
    assert result["tier_distribution"]["tier2"] == 1
    assert result["partitions_total"] == 3
    assert "ea.category_normalized = '" in result["seed_sql"]
    assert "(p.length BETWEEN" not in result["seed_sql"]


# ===========================================================================
# Test 18: length_to_bucket boundary tests
# ===========================================================================


@pytest.mark.parametrize(
    "length,expected",
    [
        # Lower edge cases
        (3, "b03_07"),
        (7, "b03_07"),
        (8, "b08_12"),
        (12, "b08_12"),
        (13, "b13_17"),
        # Mid buckets
        (17, "b13_17"),
        (18, "b18_22"),
        (22, "b18_22"),
        (23, "b23_27"),
        (27, "b23_27"),
        (28, "b28_32"),
        (32, "b28_32"),
        (33, "b33_37"),
        (37, "b33_37"),
        (38, "b38_42"),
        (42, "b38_42"),
        (43, "b43_47"),
        (47, "b43_47"),
        (48, "b48_52"),
        (52, "b48_52"),
        (53, "b53_57"),
        (57, "b53_57"),
        # Upper catch-all (incl. very large lengths beyond test 19's range, per QA N-4)
        (58, "b58_plus"),
        (100, "b58_plus"),
        (120, "b58_plus"),
        (200, "b58_plus"),
        (500, "b58_plus"),
        # Below floor (defensive — shouldn't happen in practice; per QA N-3)
        (0, "b03_07"),
        (1, "b03_07"),
        (2, "b03_07"),
    ],
)
def test_length_to_bucket_boundaries(length, expected):
    mod = _load_module_no_chunks()
    actual = mod.length_to_bucket(length)
    assert actual == expected, f"length_to_bucket({length}) = {actual!r}, expected {expected!r}"


# ===========================================================================
# Test 19: length_to_bucket Python ↔ SQL CASE consistency (regression guard)
# ===========================================================================


def test_length_to_bucket_python_matches_sql_case():
    """The Python length_to_bucket() function MUST emit the same labels as
    the LENGTH_BUCKET_CASE_SQL CASE expression. Parse the SQL and verify
    every length 3..120 maps to the same bucket in both.
    """
    mod = _load_module_no_chunks()

    # Parse LENGTH_BUCKET_CASE_SQL into ordered rules. Two rule shapes:
    #   1. "WHEN p.length < N THEN 'label'"          (single open-lower bound)
    #   2. "WHEN p.length BETWEEN A AND B THEN 'label'"
    case_sql = mod.LENGTH_BUCKET_CASE_SQL

    # Capture WHEN clauses in order so first-match-wins semantics holds.
    when_re = re.compile(r"WHEN p\.length (?:< (\d+)|BETWEEN (\d+) AND (\d+)) THEN '(\w+)'")
    sql_rules = []
    for m in when_re.finditer(case_sql):
        lt_n, btwn_lo, btwn_hi, label = m.groups()
        if lt_n is not None:
            sql_rules.append(("lt", int(lt_n), label))
        else:
            sql_rules.append(("btwn", int(btwn_lo), int(btwn_hi), label))

    else_match = re.search(r"ELSE '(\w+)'", case_sql)
    assert else_match, "LENGTH_BUCKET_CASE_SQL is missing an ELSE clause"
    sql_else_label = else_match.group(1)

    def sql_lookup(length):
        for rule in sql_rules:
            if rule[0] == "lt" and length < rule[1]:
                return rule[2]
            if rule[0] == "btwn" and rule[1] <= length <= rule[2]:
                return rule[3]
        return sql_else_label

    # Range extended to 0..200 per QA N-4 (V-Dem can produce patterns up
    # to ~150y; large-length consistency is documented).
    for length in range(0, 201):
        py_label = mod.length_to_bucket(length)
        sql_label = sql_lookup(length)
        assert py_label == sql_label, (
            f"Mismatch at length={length}: Python={py_label!r}, SQL CASE={sql_label!r}. Update one to match the other."
        )


# ===========================================================================
# Test 20: b58_plus uses '>=' filter (open-ended), not BETWEEN
# ===========================================================================


def test_b03_07_filter_covers_sub_floor_lengths():
    """Per QA review CR-1: the b03_07 INSERT filter must use
    `BETWEEN 0 AND 7`, not `BETWEEN 3 AND 7`. The enumerate query's CASE
    has a defensive `WHEN p.length < 3 THEN 'b03_07'` clause; if any
    sub-floor pattern slips through (say a corruption upstream), the
    INSERT must catch it instead of silently dropping the row.

    Defense-in-depth: in steady state, length<3 cannot occur (SCDI floor),
    but if it ever did, we'd want loud rather than quiet.
    """
    mod = _load_module_no_chunks()

    sql = mod.build_recipe_query(
        country_a_id=1,
        event_category="elections_and_voting",
        length_bucket="b03_07",
        mode="insert",
    )
    assert "p.length BETWEEN 0 AND 7" in sql, (
        "b03_07 INSERT filter must include sub-floor lengths (BETWEEN 0 AND 7), "
        "not BETWEEN 3 AND 7. Otherwise rows enumerated as b03_07 with length<3 "
        "would be silently dropped."
    )
    # Negative regression — the old (3,7) filter must not be present:
    assert "p.length BETWEEN 3 AND 7" not in sql, (
        "Stale filter 'BETWEEN 3 AND 7' detected — should be 'BETWEEN 0 AND 7'."
    )


def test_b58_plus_uses_gte_filter():
    """b58_plus is the unbounded catch-all bucket. The SQL filter must use
    `p.length >= 58`, not `BETWEEN 58 AND <sentinel>` — keeps the query plan
    clean and avoids leaning on the 999999 sentinel.
    """
    mod = _load_module_no_chunks()

    sql = mod.build_recipe_query(
        country_a_id=1,
        event_category="elections_and_voting",
        length_bucket="b58_plus",
        mode="insert",
    )
    assert "p.length >= 58" in sql
    assert "p.length BETWEEN 58 AND 999999" not in sql, "b58_plus must use >= 58, not BETWEEN with sentinel"


# ===========================================================================
# Test 21: Output recipe schema preserves pattern_tier (S/M/L/XL)
# ===========================================================================


def test_output_recipe_still_has_pattern_tier_column():
    """The chunking dimension change is INTERNAL — the output recipe row
    must still contain `pattern_tier` (S/M/L/XL) as a column for the
    frontend / downstream consumers.

    This guards against an accidental drop of the pattern_tier column from
    the recipes_aggregated CTE or the final SELECT.
    """
    mod = _load_module_no_chunks()

    sql = mod.build_recipe_query(
        country_a_id=42,
        event_category="elections_and_voting",
        length_bucket="b13_17",
        mode="insert",
    )

    # The raw_recipes CTE still derives pattern_tier from length:
    assert "AS pattern_tier" in sql, "raw_recipes must compute pattern_tier"
    assert "WHEN p.length BETWEEN 3 AND 8" in sql, "raw_recipes must keep the S/M/L/XL CASE expression"
    assert "'S'" in sql and "'M'" in sql and "'L'" in sql and "'XL'" in sql, (
        "raw_recipes must keep all 4 pattern_tier labels"
    )

    # recipes_aggregated must keep pattern_tier in the GROUP BY output:
    assert "arbitrary(pattern_tier)" in sql

    # The final SELECT must emit pattern_tier:
    assert "r.pattern_tier" in sql


# ===========================================================================
# Test 22: Recipe-identity preserved across chunking
# ===========================================================================


def test_recipe_identity_preserved_via_recipe_id_components():
    """recipe_id = country_a + country_b + start_year_a + length + event_category.
    Splitting on length (a recipe_id component) produces strictly disjoint
    recipes — no recipe can span two chunks. This test verifies the recipe_id
    formula in build_recipe_query has not regressed.
    """
    mod = _load_module_no_chunks()

    sql = mod.build_recipe_query(
        country_a_id=42,
        event_category="elections_and_voting",
        length_bucket="b13_17",
        mode="insert",
    )

    # The recipe_id concat must include all 5 components in this exact order.
    # Use a regex that allows for whitespace variation but pins the structure.
    expected_concat = (
        r"concat\(cast\(p\.country_a_id as varchar\),\s*'-',\s*"
        r"cast\(p\.country_b_id as varchar\),\s*'-',\s*"
        r"cast\(p\.start_year_a as varchar\),\s*'-',\s*"
        r"cast\(p\.length as varchar\),\s*'-',\s*"
        r"ea\.category_normalized\)\s*as recipe_id"
    )
    assert re.search(expected_concat, sql, re.IGNORECASE), (
        "recipe_id concat structure regressed. recipe_id MUST be "
        "country_a + country_b + start_year_a + length + event_category. "
        "Any change breaks the recipe-identity contract that lets us chunk "
        "by length without producing duplicate or missing recipes."
    )


# ===========================================================================
# Test 23: invalid length_bucket raises ValueError
# ===========================================================================


def test_invalid_length_bucket_raises():
    mod = _load_module_no_chunks()

    with pytest.raises(ValueError) as exc_info:
        mod.build_recipe_query(
            country_a_id=42,
            event_category="elections_and_voting",
            length_bucket="not_a_bucket",
            mode="insert",
        )
    assert "Unknown length_bucket" in str(exc_info.value)


# ===========================================================================
# Test 24: enumerate query SQL uses the new length_bucket CASE
# ===========================================================================


def test_enumerate_query_uses_length_bucket_case():
    """The enumerate query (which emits the chunks list) must group by
    length_bucket via the LENGTH_BUCKET_CASE_SQL expression — not by the
    legacy pattern_tier (S/M/L/XL). Inspect the actual SQL sent to Athena
    via start_query_execution to verify (#534 QA review CR-2).
    """
    chunks = [(1, "elections_and_voting", "b03_07", 1)]
    mod, _, athena_mock = _load_module(chunks)
    mod.lambda_handler({"run_id": "test"}, None)

    # The Lambda calls start_query_execution exactly once for the enumerate
    # query. Inspect that call's SQL string.
    assert athena_mock.start_query_execution.call_count >= 1, "enumerate query must invoke start_query_execution"
    enum_call = athena_mock.start_query_execution.call_args_list[0]
    enum_sql = enum_call.kwargs["QueryString"]

    # The CASE expression for length_bucket must be substituted into both
    # SELECT and GROUP BY (Presto/Athena does not support alias references
    # in GROUP BY, so the CASE appears twice).
    assert mod.LENGTH_BUCKET_CASE_SQL.strip() in enum_sql, (
        "Enumerate query must contain the LENGTH_BUCKET_CASE_SQL expression "
        "embedded for length_bucket grouping. SQL was:\n" + enum_sql[:1000]
    )
    # Both representative buckets must appear:
    assert "b03_07" in enum_sql
    assert "b58_plus" in enum_sql
    # GROUP BY must include length_bucket grouping:
    assert "GROUP BY" in enum_sql
    # Chunking CASE must NOT use legacy S/M/L/XL labels:
    for old_label in ("'S'", "'M'", "'L'", "'XL'"):
        assert old_label not in mod.LENGTH_BUCKET_CASE_SQL, (
            f"Chunking CASE expression must not reference legacy pattern_tier "
            f"label {old_label} — that's the output recipe schema, not the "
            f"chunking axis."
        )


# ===========================================================================
# Test 25: classify_country_tier boundaries
# ===========================================================================


@pytest.mark.parametrize(
    "count,expected",
    [
        (0, "tier1"),
        (1, "tier1"),
        (99_999, "tier1"),
        (100_000, "tier2"),
        (999_999, "tier2"),
        (1_000_000, "tier3"),
        (9_999_999, "tier3"),
        (10_000_000, "tier4"),
        (1_000_000_000, "tier4"),
    ],
)
def test_classify_country_tier(count, expected):
    mod = _load_module_no_chunks()
    actual = mod.classify_country_tier(count)
    assert actual == expected, f"classify_country_tier({count}) = {actual!r}, expected {expected!r}"


# ===========================================================================
# Test 26: smart-chunking output schema invariants
# ===========================================================================


def test_chunk_dict_schema():
    """Every emitted chunk (seed + insert_items) must have the canonical
    schema: country_a_id, event_category, length_bucket, chunk_id,
    pattern_count, drop_partition_sql, insert_sql.

    Specifically: NO `pattern_tier` field at the chunk level (output recipe
    rows still have it; chunk metadata does not).
    """
    chunks = [
        (5, "elections_and_voting", "b03_07", 100),
        (5, "mass_protest", "b13_17", 200),
    ]
    mod, s3_mock, _ = _load_module(chunks)
    mod.lambda_handler({"run_id": "test"}, None)

    expected_keys = {
        "country_a_id",
        "event_category",
        "length_bucket",
        "chunk_id",
        "pattern_count",
        "drop_partition_sql",
        "insert_sql",
    }
    for item in s3_mock._captured_items:
        assert set(item.keys()) == expected_keys, (
            f"Chunk schema mismatch: extra={set(item.keys()) - expected_keys}, "
            f"missing={expected_keys - set(item.keys())}"
        )
        assert "pattern_tier" not in item, (
            "Chunk metadata must not carry pattern_tier (replaced by length_bucket "
            "in #534). pattern_tier remains a column in OUTPUT recipe rows only."
        )


# ===========================================================================
# Test 24 (#622, 2026-05-16): DDL column list matches the SELECT column list
# ===========================================================================


def test_ddl_select_column_parity():
    """The CREATE EXTERNAL TABLE DDL column names+order MUST match the
    SELECT in build_recipe_query exactly.

    If they ever drift, Athena will fail every INSERT INTO with a cryptic
    schema-mismatch error at runtime. This test catches the drift at
    test time — the highest-value regression guard on the #622 fix.

    Cross-check against the existing test_ctas_and_insert_same_select_columns
    list (the canonical 27 SELECT columns + country_a_id partition).
    """
    mod = _load_module_no_chunks()

    # 1. DDL column list (source of truth, no partition column).
    ddl_columns = [name for name, _ctype in mod.RECIPES_COLUMNS]

    # 2. Canonical 27-data-column list (mirrors test 10's shared_columns,
    #    minus the trailing country_a_id partition). Hardcoded here as the
    #    source-of-truth contract — if a future PR changes the SELECT, both
    #    this list and RECIPES_COLUMNS must update in lockstep.
    canonical_select_data_columns = [
        "recipe_id",
        "event_category",
        "pattern_id",
        "country_b_id",
        "country_a_name",
        "country_b_name",
        "start_year_a",
        "start_year_b",
        "length",
        "avg_correlation",
        "end_year_a",
        "end_year_b",
        "event_window",
        "event_year_a",
        "event_year_b",
        "event_title_a",
        "event_title_b",
        "indicator_count",
        "pattern_power_score",
        "instance_count",
        "pattern_tier",
        "median_lead_time_b",
        "min_lead_time_b",
        "max_lead_time_b",
        "median_lead_time_a",
        "pps",
        "contains_predicted",
    ]

    # 3. Sanity: every canonical column appears in the actual SELECT SQL.
    sql = mod.build_recipe_query(
        country_a_id=1,
        event_category="elections_and_voting",
        length_bucket="b03_07",
        mode="insert",
    )
    for col in canonical_select_data_columns:
        # Each appears either as `r.<col>` or `AS <col>` (e.g. pps).
        # Use word-boundary regex (not substring) so a future column named
        # e.g. `recipe_id_extra` doesn't substring-match `recipe_id` and
        # mask a real drift (QA review N-1, 2026-05-16).
        col_esc = re.escape(col)
        present = bool(re.search(rf"\br\.{col_esc}\b", sql)) or bool(re.search(rf"\bAS\s+{col_esc}\b", sql))
        assert present, (
            f"Canonical column {col!r} not found in built INSERT SQL — "
            "the SELECT body has drifted from the canonical 27-column "
            "contract. Update canonical_select_data_columns OR fix "
            "build_recipe_query."
        )

    # 4. DDL must list every canonical column in the exact same order.
    assert len(ddl_columns) == len(canonical_select_data_columns) == 27, (
        f"Column count: DDL={len(ddl_columns)}, canonical={len(canonical_select_data_columns)}. Expected 27 each."
    )
    assert ddl_columns == canonical_select_data_columns, (
        f"DDL/SELECT column ORDER drift:\n"
        f"  canonical SELECT: {canonical_select_data_columns}\n"
        f"  RECIPES_COLUMNS:  {ddl_columns}\n"
        f"Update RECIPES_COLUMNS or the SELECT to match — Athena INSERT "
        f"will fail on schema mismatch otherwise."
    )


# ===========================================================================
# Test 25 (#622): DDL points at the stable S3 prefix, NOT query_results
# ===========================================================================


def test_ddl_uses_stable_prefix_not_query_results():
    """The whole point of #622 — the DDL LOCATION must be the stable
    s3://{bucket}/pipeline-recipe-engine/output/recipes/ prefix.

    The pre-fix CTAS landed data at query_results/tables/<uuid>/ with
    1-day S3 expiry, which caused every Lambda re-run to cycle
    DROP -> CTAS -> expire -> re-CTAS, dominating the May 2-5 cost
    spike (~$13/day, 99.6% of GETs against the most recent uuid dir).
    """
    mod = _load_module_no_chunks()
    ddl = mod.build_external_table_ddl(s3_bucket="qgi-data-lake-staging")

    assert "LOCATION 's3://qgi-data-lake-staging/pipeline-recipe-engine/output/recipes/'" in ddl, (
        f"DDL missing the stable-prefix LOCATION clause. Full DDL:\n{ddl}"
    )
    assert "query_results/tables" not in ddl, (
        "DDL must NOT reference query_results/tables/ — that's the 1-day-expiry trap that caused the #622 cost leak."
    )
    assert "PARTITIONED BY (country_a_id smallint)" in ddl, (
        "DDL must declare country_a_id as the partition column (matches the patterns table partitioning)."
    )
    assert "STORED AS PARQUET" in ddl
    assert "CREATE EXTERNAL TABLE IF NOT EXISTS qgi_data.recipes" in ddl, (
        "DDL must use CREATE EXTERNAL TABLE IF NOT EXISTS for idempotency."
    )
    # Convention parity with the other QGI external tables
    # (qgi-infra/modules/storage/main.tf uses parquet.compress + EXTERNAL=TRUE).
    assert "'parquet.compress' = 'SNAPPY'" in ddl
    assert "'EXTERNAL' = 'TRUE'" in ddl


# ===========================================================================
# Test 26 (#622): seed chunk pattern_count guard
# ===========================================================================


def test_seed_chunk_pattern_count_guard_raises_on_oversized_seed():
    """Defense-in-depth: if the smart-chunking math ever degrades and
    routes a Tier-3+ slice through the seed slot, fail fast rather than
    silently OOM-ing the Athena query 30 minutes later.

    The chunks list is sorted ASC by pattern_count (line 305), so a
    healthy seed is far below the 5M guard. This guard fires only on a
    pathological regression — the largest production-observed chunk
    runs at 76s wall-clock for 263M reported rows (2026-04-29 calibration).
    """
    # Single chunk with pattern_count > guard (5M).
    chunks = [(5, "elections_and_voting", "b03_07", 10_000_000)]
    mod, _, _ = _load_module(chunks)

    with pytest.raises(RuntimeError) as exc_info:
        mod.lambda_handler({"run_id": "test"}, None)

    msg = str(exc_info.value)
    assert "Seed chunk pattern_count=10000000" in msg
    assert "smart-chunking" in msg, "Guard error message should explain the failure mode."
    assert "30-min Athena DML wall" in msg, "Guard error message should reference the consequence."


def test_pre_ddl_s3_cleanup_clears_stable_prefix():
    """#622 (QA review on qgi-infra PR #25, BLOCK-level data-correctness
    fix): the Lambda must call _s3_delete_prefix(RECIPES_STABLE_PREFIX)
    before generating ddl_sql.

    Without the pre-clean, every re-run accumulates partition files at
    the stable prefix → 5b.3a CREATE EXTERNAL TABLE IF NOT EXISTS
    re-attaches the old files → downstream INSERTs add new partitions
    on top → duplicate rows after the 2nd run. The cost-leak fix would
    introduce a data-correctness regression.

    The fix lives in this Lambda (not a new SF state) to avoid a
    cold-start + state-transition cost (~1s/run) for a 200ms paginated
    delete. The Lambda already has the S3 client + the stable-prefix
    constant.
    """
    # Mock the paginator to return 2 pages × 3 stale objects so we
    # exercise both the per-page accumulator AND the final flush.
    chunks = [(5, "elections_and_voting", "b03_07", 100)]
    mod, s3_mock, _ = _load_module(chunks)

    # Simulate 6 stale objects across 2 pages from list_objects_v2.
    stale_keys = [{"Key": f"pipeline-recipe-engine/output/recipes/country_a_id={i}/p-{i}.parquet"} for i in range(1, 7)]
    pages = [{"Contents": stale_keys[:3]}, {"Contents": stale_keys[3:]}]

    paginator_mock = MagicMock()
    paginator_mock.paginate.return_value = pages
    s3_mock.get_paginator.return_value = paginator_mock

    mod.lambda_handler({"run_id": "test"}, None)

    # The paginator was acquired for list_objects_v2.
    s3_mock.get_paginator.assert_called_with("list_objects_v2")
    # paginate was called with the stable prefix.
    paginator_mock.paginate.assert_called_once_with(
        Bucket="test-bucket",
        Prefix=mod.RECIPES_STABLE_PREFIX,
    )
    # delete_objects was invoked at least once with the stable-prefix keys.
    delete_calls = [c for c in s3_mock.delete_objects.call_args_list]
    assert delete_calls, (
        "Expected s3.delete_objects to be called for pre-DDL cleanup; "
        "got zero invocations. Without this, recipes table will accumulate "
        "duplicate rows across pipeline runs."
    )
    deleted_keys = []
    for call in delete_calls:
        objects = call.kwargs.get("Delete", {}).get("Objects", [])
        deleted_keys.extend(o["Key"] for o in objects)
    assert len(deleted_keys) == 6, f"Expected 6 stale keys deleted, got {len(deleted_keys)}: {deleted_keys}"
    for k in deleted_keys:
        assert k.startswith(mod.RECIPES_STABLE_PREFIX), (
            f"delete_objects targeted a key outside the stable prefix: {k!r}"
        )


def test_pre_ddl_s3_cleanup_handles_empty_prefix():
    """First-ever pipeline run: the stable prefix has zero objects.
    The cleanup must complete silently — no delete_objects call (S3
    API rejects empty Delete lists)."""
    chunks = [(5, "elections_and_voting", "b03_07", 100)]
    mod, s3_mock, _ = _load_module(chunks)

    # Empty pages — first run.
    paginator_mock = MagicMock()
    paginator_mock.paginate.return_value = [{"Contents": []}]
    s3_mock.get_paginator.return_value = paginator_mock

    # Should not raise.
    mod.lambda_handler({"run_id": "test"}, None)

    # delete_objects MUST NOT be called when there's nothing to delete
    # (S3 rejects empty Delete.Objects lists).
    assert s3_mock.delete_objects.call_count == 0, (
        f"Expected zero delete_objects calls on an empty prefix; got {s3_mock.delete_objects.call_count}."
    )


def test_seed_chunk_pattern_count_guard_passes_on_healthy_seed():
    """Boundary: a seed at 5M (exactly AT the guard) passes; the
    guard fires only on STRICTLY GREATER. Documents that the guard
    threshold is intentionally generous to avoid false alarms on
    realistic Tier-3+ countries.
    """
    chunks = [
        (5, "elections_and_voting", "b03_07", 5_000_000),  # exactly at guard
        (5, "mass_protest", "b13_17", 6_000_000),
    ]
    mod, _, _ = _load_module(chunks)
    # Should NOT raise.
    result = mod.lambda_handler({"run_id": "test"}, None)
    assert result["seed_pattern_count"] == 5_000_000
