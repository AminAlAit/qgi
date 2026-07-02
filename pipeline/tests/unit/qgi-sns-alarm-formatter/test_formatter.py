"""Unit tests for qgi-sns-alarm-formatter."""

import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# Load the Lambda module from its directory. Mirrors the pattern used by
# other unit tests in this repo (e.g. test_country_risks_scoring.py).
_LAMBDA_DIR = Path(__file__).resolve().parents[3] / "lambdas" / "qgi-sns-alarm-formatter"
_SPEC = importlib.util.spec_from_file_location("sns_alarm_formatter_handler", _LAMBDA_DIR / "lambda_function.py")


@pytest.fixture(scope="module")
def handler():
    """Module-level import of the Lambda handler, with SES mocked."""
    # Preset env to deterministic values for subject/body assertions.
    os.environ.setdefault("SENDER_EMAIL", "alerts@qgintelligence.com")
    os.environ.setdefault("RECIPIENT_EMAIL", "qgintelligence@gmail.com")
    os.environ.setdefault("SES_REGION", "eu-central-1")

    with patch("boto3.client") as mock_boto:
        mock_ses = MagicMock()
        mock_boto.return_value = mock_ses
        module = importlib.util.module_from_spec(_SPEC)
        sys.modules["sns_alarm_formatter_handler"] = module
        _SPEC.loader.exec_module(module)
        module._test_ses = mock_ses  # expose for assertions
        yield module


# ---------------------------------------------------------------------------
# Dispatcher routing
# ---------------------------------------------------------------------------


def test_dispatcher_routes_high_country_count(handler):
    alarm = {
        "AlarmName": "qgi-v191-high-country-count-out-of-band-high",
        "NewStateValue": "ALARM",
        "OldStateValue": "OK",
    }
    subject, body = handler.format_alarm(alarm)
    assert "HIGH_COUNTRY_COUNT" in subject
    assert "above 60" in subject
    assert "target band" in body.lower()


def test_dispatcher_routes_median_salience_low(handler):
    alarm = {
        "AlarmName": "qgi-v191-median-salience-out-of-band-low",
        "NewStateValue": "ALARM",
    }
    subject, body = handler.format_alarm(alarm)
    assert "MEDIAN_SALIENCE" in subject
    assert "below 0.2" in subject


def test_dispatcher_routes_country_risks_bytes(handler):
    alarm = {
        "AlarmName": "qgi-v191-country-risks-bytes-out-of-band-low",
        "NewStateValue": "ALARM",
    }
    subject, body = handler.format_alarm(alarm)
    assert "COUNTRY_RISKS_BYTES" in subject
    assert "[ALARM-ONLY]" in subject  # tagged to indicate no-page


def test_dispatcher_routes_caught_exception(handler):
    alarm = {
        "AlarmName": "qgi-caught-exception-finalize-country-risks",
        "NewStateValue": "ALARM",
        "OldStateValue": "OK",
        "Trigger": {
            "Dimensions": [
                {"name": "Lambda", "value": "qgi-pipeline-recipe-engine-finalize"},
                {"name": "Location", "value": "write_country_risks_json"},
            ]
        },
    }
    subject, body = handler.format_alarm(alarm)
    assert "Silent exception" in subject
    assert "qgi-pipeline-recipe-engine-finalize" in subject
    assert "write_country_risks_json" in body
    # Logs Insights URL should be region-templated.
    assert "logs-insights" in body
    assert "eu-central-1" in body


def test_dispatcher_routes_unknown_to_fallback(handler):
    alarm = {
        "AlarmName": "some-unknown-alarm-name",
        "NewStateValue": "ALARM",
        "OldStateValue": "OK",
        "StateReason": "threshold breach",
    }
    subject, body = handler.format_alarm(alarm)
    assert "some-unknown-alarm-name" in subject
    assert "no specific formatter matched" in body


# ---------------------------------------------------------------------------
# Individual formatter details
# ---------------------------------------------------------------------------


def test_high_country_count_low_has_scoring_collapse_hint(handler):
    alarm = {
        "AlarmName": "qgi-v191-high-country-count-out-of-band-low",
        "NewStateValue": "ALARM",
    }
    _, body = handler.format_alarm(alarm)
    assert "scoring collapse" in body.lower() or "upstream data loss" in body.lower()


def test_country_risks_bytes_alarm_only_mentioned(handler):
    alarm = {"AlarmName": "qgi-v191-country-risks-bytes-out-of-band-high"}
    _, body = handler.format_alarm(alarm)
    assert "ALARM-only" in body or "Not paged" in body


def test_caught_exception_missing_dimensions_graceful(handler):
    # Alarm without Dimensions — should still render with '(unknown)' values.
    alarm = {
        "AlarmName": "qgi-caught-exception-xyz",
        "NewStateValue": "ALARM",
    }
    subject, body = handler.format_alarm(alarm)
    assert "unknown" in body  # Lambda: (unknown)


def test_fallback_includes_payload_dump(handler):
    alarm = {"AlarmName": "truly-new-alarm", "NewStateValue": "ALARM"}
    _, body = handler.format_alarm(alarm)
    # Should tell the reader to extend the formatter registry.
    assert "qgi-sns-alarm-formatter" in body


# ---------------------------------------------------------------------------
# lambda_handler end-to-end (SES mocked)
# ---------------------------------------------------------------------------


def _sns_record(alarm_dict):
    return {"Sns": {"Message": json.dumps(alarm_dict)}}


def test_lambda_handler_sends_email_for_each_record(handler):
    handler._test_ses.reset_mock()
    handler._test_ses.send_email.return_value = {"MessageId": "test"}

    event = {
        "Records": [
            _sns_record({"AlarmName": "qgi-caught-exception-a", "NewStateValue": "ALARM"}),
            _sns_record({"AlarmName": "qgi-caught-exception-b", "NewStateValue": "ALARM"}),
        ]
    }
    result = handler.lambda_handler(event, context=None)
    assert result == {"statusCode": 200, "sent": 2, "failed": 0}
    assert handler._test_ses.send_email.call_count == 2


def test_lambda_handler_raises_on_ses_failure(handler):
    """SES failure must re-raise so SNS retries — don't swallow."""
    handler._test_ses.reset_mock()
    handler._test_ses.send_email.side_effect = RuntimeError("SES broken")

    event = {
        "Records": [
            _sns_record({"AlarmName": "qgi-caught-exception-a", "NewStateValue": "ALARM"}),
        ]
    }
    with pytest.raises(RuntimeError, match="SES broken"):
        handler.lambda_handler(event, context=None)


def test_lambda_handler_malformed_sns_falls_back_gracefully(handler):
    """Non-JSON SNS message → fallback formatter, still sends an email."""
    handler._test_ses.reset_mock()
    handler._test_ses.send_email.side_effect = None  # clear any leak from prior tests
    handler._test_ses.send_email.return_value = {"MessageId": "test"}

    event = {"Records": [{"Sns": {"Message": "this is not json"}}]}
    result = handler.lambda_handler(event, context=None)
    assert result["sent"] == 1
    assert handler._test_ses.send_email.call_count == 1
    call_kwargs = handler._test_ses.send_email.call_args.kwargs
    assert "malformed-sns-payload" in call_kwargs["Message"]["Subject"]["Data"]
