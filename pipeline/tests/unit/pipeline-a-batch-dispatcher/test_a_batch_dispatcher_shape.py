"""
Contract test for pipeline-a-batch-dispatcher (#FAR-1, issue #154).

The Step Function pulls $.dispatch_a_output.phase1_started_at out of the
dispatcher result and feeds it into the checker as an input parameter.
A prior iteration (run far1-test-20260408-005530) failed because the
dispatcher didn't return phase1_started_at — the SF JSONPath resolution
exploded with 'invalid path'.

This test locks down the shape: {dispatched, total, phase1_started_at,
submit_failures, run_id}.
"""

import importlib.util
import json
import os
import sys
import types
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

_LAMBDAS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "lambdas"


def _load_dispatcher(indicators, jobdef_map: str | None = None):
    """Load dispatcher module with mocked boto3.

    `jobdef_map`: optional JSON-encoded map passed as
    BATCH_JOB_DEFINITION_MAP env var (#240 Phase A per-provider
    routing). When None, the legacy single-JobDef path is exercised.
    """
    body = BytesIO(json.dumps({"indicators": indicators}).encode("utf-8"))
    s3_client = MagicMock()
    s3_client.get_object.return_value = {"Body": body}

    batch_client = MagicMock()
    batch_client.submit_job.side_effect = lambda **kw: {"jobId": f"job-{kw['jobName']}"}

    table = MagicMock()
    ddb_resource = MagicMock()
    ddb_resource.Table.return_value = table

    def client_factory(name, *a, **kw):
        return {"s3": s3_client, "batch": batch_client}.get(name, MagicMock())

    boto3_stub = types.ModuleType("boto3")
    boto3_stub.client = MagicMock(side_effect=client_factory)
    boto3_stub.resource = MagicMock(return_value=ddb_resource)

    env = {
        "S3_BUCKET": "test-bucket",
        "BATCH_JOB_QUEUE": "test-queue",
        "BATCH_JOB_DEFINITION": "test-jobdef-default",
        "COUNTER_TABLE": "qgi-pipeline-a-counter",
    }
    if jobdef_map is not None:
        env["BATCH_JOB_DEFINITION_MAP"] = jobdef_map
    with patch.dict(sys.modules, {"boto3": boto3_stub}), patch.dict(os.environ, env):
        spec = importlib.util.spec_from_file_location(
            "a_batch_dispatcher",
            str(_LAMBDAS_DIR / "pipeline-a-batch-dispatcher" / "lambda_function.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod, batch_client, table


_REQUIRED_KEYS = {"dispatched", "total", "phase1_started_at", "submit_failures", "run_id"}


def test_return_shape_has_phase1_started_at():
    """SF 'Phase 1: Check Counter' passes $.dispatch_a_output.phase1_started_at
    to the checker — missing key = JSONPath crash. Regression guard."""
    mod, _, _ = _load_dispatcher(
        [
            {"id_string": "NY.GDP.MKTP.CD", "status": "process"},
            {"id_string": "SP.POP.TOTL", "status": "process"},
        ]
    )
    result = mod.lambda_handler({"run_id": "test-run"}, None)
    missing = _REQUIRED_KEYS - set(result.keys())
    assert not missing, f"missing keys {missing}. Got {result}"
    assert isinstance(result["phase1_started_at"], int)
    assert result["phase1_started_at"] > 1_700_000_000  # post-2023 epoch sanity


def test_dispatched_and_total_match_process_status_count():
    mod, batch_client, _ = _load_dispatcher(
        [
            {"id_string": "A", "status": "process"},
            {"id_string": "B", "status": "process"},
            {"id_string": "C", "status": "hold"},  # filtered out
            {"id_string": "D", "status": "process"},
        ]
    )
    result = mod.lambda_handler({"run_id": "test-run"}, None)
    assert result["dispatched"] == 3
    assert result["total"] == 3
    assert batch_client.submit_job.call_count == 3
    assert result["submit_failures"] == []


def test_empty_process_list_seeds_counter_zero():
    """Edge case: nothing to do. Must not crash, must seed counter=0."""
    mod, batch_client, table = _load_dispatcher(
        [
            {"id_string": "A", "status": "hold"},
        ]
    )
    result = mod.lambda_handler({"run_id": "test-run"}, None)
    assert result["dispatched"] == 0
    assert batch_client.submit_job.call_count == 0
    # counter was seeded
    table.put_item.assert_called_once()


# --------------------------------------------------------------------- #
# #240 Phase A — per-provider JobDef routing                            #
# --------------------------------------------------------------------- #


def test_per_provider_routing_sends_each_indicator_to_its_jobdef():
    """WB indicators should land on the WB JobDef, FAOSTAT on the
    FAOSTAT JobDef. Core acceptance test for the per-provider dispatch
    layer that #241's FAOSTAT fetcher depends on.

    Note: when FAOSTAT indicators share a fao_domain_code, they're
    grouped into ONE task-unit (submits as INDICATORS_JSON, not
    INDICATOR_ID). This test uses the SAME domain for both FA
    entries to exercise the #241 Phase B domain grouping at the
    same time as per-provider routing."""
    jobdef_map = json.dumps(
        {
            "WB": "arn:aws:batch:eu-central-1:123:job-definition/wb-fetcher:1",
            "FAOSTAT": "arn:aws:batch:eu-central-1:123:job-definition/fao-fetcher:1",
        }
    )
    mod, batch_client, _ = _load_dispatcher(
        [
            {"id_string": "NY.GDP.MKTP.CD", "numeric_id": 1, "status": "process", "provider": "WB"},
            {
                "id_string": "FA-01",
                "numeric_id": 59,
                "status": "process",
                "provider": "FAOSTAT",
                "fao_domain_code": "FS",
                "fao_item_code": 21010,
                "fao_element_code": 6121,
            },
            {
                "id_string": "FA-04",
                "numeric_id": 62,
                "status": "process",
                "provider": "FAOSTAT",
                "fao_domain_code": "FS",
                "fao_item_code": 21013,
                "fao_element_code": 6128,
            },
        ],
        jobdef_map=jobdef_map,
    )
    result = mod.lambda_handler({"run_id": "test-run"}, None)

    # WB: 1 task-unit (one indicator), FAOSTAT: 1 task-unit (both
    # share domain=FS). So 2 submit_job calls total.
    assert batch_client.submit_job.call_count == 2

    by_jobdef: dict[str, dict] = {}
    for call in batch_client.submit_job.call_args_list:
        jd = call.kwargs["jobDefinition"]
        env_items = call.kwargs["containerOverrides"]["environment"]
        env_map = {e["name"]: e["value"] for e in env_items}
        by_jobdef[jd] = env_map

    wb_arn = "arn:aws:batch:eu-central-1:123:job-definition/wb-fetcher:1"
    fao_arn = "arn:aws:batch:eu-central-1:123:job-definition/fao-fetcher:1"
    assert wb_arn in by_jobdef and fao_arn in by_jobdef

    # WB path: INDICATOR_ID set, no DOMAIN_CODE
    assert by_jobdef[wb_arn]["INDICATOR_ID"] == "NY.GDP.MKTP.CD"
    assert "DOMAIN_CODE" not in by_jobdef[wb_arn]

    # FAOSTAT path: DOMAIN_CODE + INDICATORS_JSON, no INDICATOR_ID
    assert by_jobdef[fao_arn]["DOMAIN_CODE"] == "FS"
    ind_list = json.loads(by_jobdef[fao_arn]["INDICATORS_JSON"])
    assert {i["id_string"] for i in ind_list} == {"FA-01", "FA-04"}
    # Provider-specific fields are passed through
    assert all("fao_item_code" in i for i in ind_list)
    assert "INDICATOR_ID" not in by_jobdef[fao_arn]

    # "dispatched" is in INDICATOR units (3), not task-unit units (2)
    assert result["dispatched"] == 3
    assert result["dispatched_task_units"] == 2
    assert result["per_provider_counts"] == {"WB": 1, "FAOSTAT": 2}


def test_unknown_provider_falls_back_to_default_jobdef():
    """An indicator with a provider that's not in the map (e.g., future
    V-Dem before its JobDef is wired up) should go to the default
    BATCH_JOB_DEFINITION so we never drop it silently."""
    jobdef_map = json.dumps(
        {
            "WB": "arn:aws:batch:eu-central-1:123:job-definition/wb-fetcher:1",
        }
    )
    mod, batch_client, _ = _load_dispatcher(
        [
            {"id_string": "NY.GDP.MKTP.CD", "status": "process", "provider": "WB"},
            {"id_string": "V-01", "status": "process", "provider": "V_DEM"},
        ],
        jobdef_map=jobdef_map,
    )
    result = mod.lambda_handler({"run_id": "test-run"}, None)

    by_jobdef: dict[str, list[str]] = {}
    for call in batch_client.submit_job.call_args_list:
        jd = call.kwargs["jobDefinition"]
        env_items = call.kwargs["containerOverrides"]["environment"]
        ind_id = next(e["value"] for e in env_items if e["name"] == "INDICATOR_ID")
        by_jobdef.setdefault(jd, []).append(ind_id)

    assert "arn:aws:batch:eu-central-1:123:job-definition/wb-fetcher:1" in by_jobdef
    assert "test-jobdef-default" in by_jobdef
    assert by_jobdef["test-jobdef-default"] == ["V-01"]
    assert result["dispatched"] == 2


def test_missing_provider_field_defaults_to_wb_then_default_jobdef():
    """Legacy indicators.json without a `provider` field on each entry
    (pre-#240 data) should default to provider='WB' so nothing breaks
    during the rollout window."""
    mod, batch_client, _ = _load_dispatcher(
        [
            {"id_string": "NY.GDP.MKTP.CD", "status": "process"},  # no provider field
        ]
    )
    result = mod.lambda_handler({"run_id": "test-run"}, None)

    call = batch_client.submit_job.call_args_list[0]
    # No map env var set → falls back to legacy single JobDef for every provider
    assert call.kwargs["jobDefinition"] == "test-jobdef-default"
    env_items = call.kwargs["containerOverrides"]["environment"]
    provider_env = next((e for e in env_items if e["name"] == "PROVIDER"), None)
    assert provider_env is not None and provider_env["value"] == "WB"
    assert result["per_provider_counts"] == {"WB": 1}


def test_malformed_jobdef_map_env_falls_back_gracefully():
    """If BATCH_JOB_DEFINITION_MAP is set to something that isn't
    valid JSON (operator error during a TF apply), don't crash — log
    and fall back to legacy single-JobDef mode."""
    mod, batch_client, _ = _load_dispatcher(
        [{"id_string": "A", "status": "process", "provider": "WB"}],
        jobdef_map="not-json-at-all",
    )
    result = mod.lambda_handler({"run_id": "test-run"}, None)
    assert result["dispatched"] == 1
    assert batch_client.submit_job.call_args_list[0].kwargs["jobDefinition"] == ("test-jobdef-default")


def test_provider_env_var_injected_into_fargate_task():
    """The fetcher container needs the PROVIDER env var to know which
    fetch pattern to run (in case one image handles multiple providers
    down the line, or for structured logging). FAOSTAT single-indicator
    units now use DOMAIN_CODE + INDICATORS_JSON instead of INDICATOR_ID."""
    mod, batch_client, _ = _load_dispatcher(
        [
            {
                "id_string": "FA-01",
                "numeric_id": 59,
                "status": "process",
                "provider": "FAOSTAT",
                "fao_domain_code": "FS",
                "fao_item_code": 21010,
                "fao_element_code": 6121,
            },
        ]
    )
    mod.lambda_handler({"run_id": "test-run"}, None)
    call = batch_client.submit_job.call_args_list[0]
    env_items = call.kwargs["containerOverrides"]["environment"]
    env_map = {e["name"]: e["value"] for e in env_items}
    assert env_map["PROVIDER"] == "FAOSTAT"
    # FAOSTAT uses multi-indicator shape even when only 1 indicator in
    # the batch — it's still grouped by fao_domain_code.
    assert env_map["DOMAIN_CODE"] == "FS"
    payload = json.loads(env_map["INDICATORS_JSON"])
    assert len(payload) == 1
    assert payload[0]["id_string"] == "FA-01"
    assert payload[0]["fao_item_code"] == 21010


# --------------------------------------------------------------------- #
# #241 Phase B — task-unit grouping (FAOSTAT domain bundling)          #
# --------------------------------------------------------------------- #


def test_faostat_indicators_group_by_domain():
    """Six FAOSTAT indicators in the FS domain should produce ONE
    Batch task (not 6). The task's INDICATORS_JSON contains all 6."""
    indicators = [
        {
            "id_string": f"FA-{i:02d}",
            "numeric_id": 58 + i,
            "status": "process",
            "provider": "FAOSTAT",
            "fao_domain_code": "FS",
            "fao_item_code": 21010 + i,
            "fao_element_code": 6121,
        }
        for i in range(1, 7)  # FA-01 through FA-06, all in FS
    ]
    mod, batch_client, _ = _load_dispatcher(indicators)
    result = mod.lambda_handler({"run_id": "test-run"}, None)

    # ONE Fargate task for all 6 indicators
    assert batch_client.submit_job.call_count == 1
    assert result["dispatched"] == 6
    assert result["dispatched_task_units"] == 1
    call = batch_client.submit_job.call_args_list[0]
    env_map = {e["name"]: e["value"] for e in call.kwargs["containerOverrides"]["environment"]}
    assert env_map["DOMAIN_CODE"] == "FS"
    payload = json.loads(env_map["INDICATORS_JSON"])
    assert len(payload) == 6
    assert {i["id_string"] for i in payload} == {"FA-01", "FA-02", "FA-03", "FA-04", "FA-05", "FA-06"}


def test_faostat_indicators_split_across_domains_produce_multiple_tasks():
    """Mix of FS and RL domains → 2 tasks (one per domain)."""
    indicators = [
        {"id_string": "FA-01", "numeric_id": 59, "status": "process", "provider": "FAOSTAT", "fao_domain_code": "FS"},
        {"id_string": "FA-06", "numeric_id": 64, "status": "process", "provider": "FAOSTAT", "fao_domain_code": "RL"},
        {"id_string": "FA-07", "numeric_id": 65, "status": "process", "provider": "FAOSTAT", "fao_domain_code": "RL"},
    ]
    mod, batch_client, _ = _load_dispatcher(indicators)
    result = mod.lambda_handler({"run_id": "test-run"}, None)

    assert batch_client.submit_job.call_count == 2
    assert result["dispatched"] == 3
    assert result["dispatched_task_units"] == 2

    domains_seen = set()
    for call in batch_client.submit_job.call_args_list:
        env_map = {e["name"]: e["value"] for e in call.kwargs["containerOverrides"]["environment"]}
        domains_seen.add(env_map["DOMAIN_CODE"])
    assert domains_seen == {"FS", "RL"}


def test_wb_indicators_still_submitted_one_per_task():
    """WB is not in _PROVIDER_TASK_GROUPING, so each indicator gets
    its own task (existing behaviour)."""
    indicators = [
        {"id_string": "NY.GDP.MKTP.CD", "numeric_id": 1, "status": "process", "provider": "WB"},
        {"id_string": "SP.POP.TOTL", "numeric_id": 2, "status": "process", "provider": "WB"},
        {"id_string": "NE.EXP.GNFS.CD", "numeric_id": 3, "status": "process", "provider": "WB"},
    ]
    mod, batch_client, _ = _load_dispatcher(indicators)
    result = mod.lambda_handler({"run_id": "test-run"}, None)

    assert batch_client.submit_job.call_count == 3
    assert result["dispatched"] == 3
    assert result["dispatched_task_units"] == 3
    # Each WB task has INDICATOR_ID (not DOMAIN_CODE / INDICATORS_JSON)
    for call in batch_client.submit_job.call_args_list:
        env_map = {e["name"]: e["value"] for e in call.kwargs["containerOverrides"]["environment"]}
        assert "INDICATOR_ID" in env_map
        assert "DOMAIN_CODE" not in env_map
        assert "INDICATORS_JSON" not in env_map


def test_mixed_wb_and_faostat_produces_correct_task_unit_split():
    """259 WB + 15 FAOSTAT (across 8 domains) → 259 + 8 = 267 task units.
    The per_provider_counts still count INDICATORS (259, 15)."""
    # Abbreviated: 3 WB + 3 FAOSTAT in 2 domains
    indicators = [
        {"id_string": "NY.GDP.MKTP.CD", "numeric_id": 1, "status": "process", "provider": "WB"},
        {"id_string": "SP.POP.TOTL", "numeric_id": 2, "status": "process", "provider": "WB"},
        {"id_string": "NE.EXP.GNFS.CD", "numeric_id": 3, "status": "process", "provider": "WB"},
        {"id_string": "FA-01", "numeric_id": 59, "status": "process", "provider": "FAOSTAT", "fao_domain_code": "FS"},
        {"id_string": "FA-04", "numeric_id": 62, "status": "process", "provider": "FAOSTAT", "fao_domain_code": "FS"},
        {"id_string": "FA-06", "numeric_id": 64, "status": "process", "provider": "FAOSTAT", "fao_domain_code": "RL"},
    ]
    mod, batch_client, _ = _load_dispatcher(indicators)
    result = mod.lambda_handler({"run_id": "test-run"}, None)

    # 3 WB tasks + 1 FS task + 1 RL task = 5 task units
    assert batch_client.submit_job.call_count == 5
    assert result["dispatched"] == 6  # indicators
    assert result["dispatched_task_units"] == 5
    # Per-provider counts are in INDICATORS, not tasks
    assert result["per_provider_counts"] == {"WB": 3, "FAOSTAT": 3}


def test_submit_failure_counts_indicator_size_not_task_count():
    """If a FAOSTAT domain task fails to submit (e.g., Batch throttling),
    the counter must be decremented by the number of INDICATORS in that
    task (not 1), otherwise Phase 1 hangs waiting for N-1 phantom
    indicators."""
    indicators = [
        {"id_string": "FA-01", "numeric_id": 59, "status": "process", "provider": "FAOSTAT", "fao_domain_code": "FS"},
        {"id_string": "FA-04", "numeric_id": 62, "status": "process", "provider": "FAOSTAT", "fao_domain_code": "FS"},
        {"id_string": "FA-06", "numeric_id": 64, "status": "process", "provider": "FAOSTAT", "fao_domain_code": "RL"},
    ]
    mod, batch_client, table = _load_dispatcher(indicators)
    # Make the FIRST submit_job call fail (FS domain, 2 indicators)
    # and let the second succeed (RL domain, 1 indicator).
    call_count = {"n": 0}

    def flaky_submit(**kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("Batch throttled")
        return {"jobId": f"job-{kw['jobName']}"}

    batch_client.submit_job.side_effect = flaky_submit

    result = mod.lambda_handler({"run_id": "test-run"}, None)

    # 1 unit succeeded (1 indicator), 1 unit failed (2 indicators).
    assert result["dispatched"] == 1
    # 2 indicators in submit_failures (FA-01 + FA-04, not just the unit)
    assert set(result["submit_failures"]) == {"FA-01", "FA-04"}
    # Counter should have been decremented by 2 (the failed indicator count)
    upd_calls = table.update_item.call_args_list
    assert any(c.kwargs["ExpressionAttributeValues"][":neg"] == -2 for c in upd_calls)
