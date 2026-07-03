"""
Unit tests for pipeline-c-dispatcher: verifies the dispatcher queries SCDIs
(not all countries) to determine which country IDs to fan out.
"""

import sys
import types
import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest

_LAMBDAS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "lambdas"


def _make_boto3_stub():
    stub = types.ModuleType("boto3")
    stub.client = MagicMock(return_value=MagicMock())
    stub.resource = MagicMock(return_value=MagicMock())
    return stub


def _load_module():
    boto3_stub = _make_boto3_stub()
    with patch.dict(sys.modules, {"boto3": boto3_stub}):
        spec = importlib.util.spec_from_file_location(
            "c_dispatcher",
            str(_LAMBDAS_DIR / "pipeline-c-dispatcher" / "lambda_function.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


MODULE = _load_module()


class TestDispatcherUsesScdiCountries:
    """Dispatcher must query scdis table, not all-countries table."""

    def _make_env(self, sqdis_table="scdis"):
        return {
            "S3_BUCKET": "test-bucket",
            "ATHENA_DATABASE": "qgi_data",
            "COUNTRIES_NAMES_TABLE": "countries",
            "SCDIS_TABLE": sqdis_table,
            "ATHENA_WORKGROUP": "QGI-Lambda-Workgroup",
            "S3_OUTPUT_LOCATION": "s3://test-bucket/query_results/",
            "SQS_QUEUE_URL": "https://sqs.test/queue",
        }

    def test_countries_query_uses_scdis_table(self, monkeypatch):
        """
        The SELECT query sent to Athena must reference the scdis table,
        not the countries/COUNTRIES_NAMES_TABLE. This ensures we only
        dispatch countries that have actual SCDI data.
        """
        env = self._make_env()
        for k, v in env.items():
            monkeypatch.setenv(k, v)

        captured_queries = []

        def fake_run_athena_query(query_string, *args, **kwargs):
            captured_queries.append(query_string)
            # Return a fake S3 path for the countries query (first call)
            if "expects_result_path" in kwargs and kwargs["expects_result_path"]:
                return "s3://test-bucket/query_results/abc123.csv"
            return None

        # Stub S3 get_object to return a small CSV of country IDs
        fake_csv = "country_a_id\n1\n5\n42\n"
        fake_s3 = MagicMock()
        fake_s3.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=fake_csv.encode()))}
        # Stub SQS (purge + send), and the Glue table creation no-ops
        fake_sqs = MagicMock()

        with (
            patch.object(MODULE, "run_athena_query", side_effect=fake_run_athena_query),
            patch.object(MODULE, "clean_s3_prefix"),
            patch.object(MODULE.s3_client, "get_object", fake_s3.get_object),
            patch.object(MODULE.sqs_client, "purge_queue"),
            patch.object(MODULE.sqs_client, "send_message"),
            patch("time.sleep"),
        ):
            MODULE.lambda_handler(
                {"action": "start", "run_id": "test-run-1"},
                {},
            )

        # First Athena query must be the countries SELECT — it must reference scdis
        countries_query = captured_queries[0]
        assert "scdis" in countries_query.lower(), (
            f"Expected query to reference 'scdis' table, got: {countries_query!r}"
        )
        assert "countries" not in countries_query.lower(), (
            f"Query must NOT reference the countries table, got: {countries_query!r}"
        )

    def test_dispatched_count_matches_scdis_rows(self, monkeypatch):
        """Only countries returned by the scdis query are dispatched to SQS."""
        env = self._make_env()
        for k, v in env.items():
            monkeypatch.setenv(k, v)

        fake_csv = "country_a_id\n10\n20\n30\n"  # 3 countries with SCDIs

        def fake_run_athena(query_string, *args, **kwargs):
            if kwargs.get("expects_result_path"):
                return "s3://test-bucket/query_results/xyz.csv"
            return None

        fake_s3_get = MagicMock(return_value={"Body": MagicMock(read=MagicMock(return_value=fake_csv.encode()))})
        sent_messages = []

        with (
            patch.object(MODULE, "run_athena_query", side_effect=fake_run_athena),
            patch.object(MODULE, "clean_s3_prefix"),
            patch.object(MODULE.s3_client, "get_object", fake_s3_get),
            patch.object(MODULE.sqs_client, "purge_queue"),
            patch.object(MODULE.sqs_client, "send_message", side_effect=lambda **kw: sent_messages.append(kw)),
            patch("time.sleep"),
        ):
            result = MODULE.lambda_handler(
                {"action": "start", "run_id": "test-run-2"},
                {},
            )

        assert result["dispatched_count"] == 3
        assert len(sent_messages) == 3
