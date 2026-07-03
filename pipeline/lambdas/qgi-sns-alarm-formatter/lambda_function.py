"""
SNS alarm formatter — subscribed to `qgi-monthly-updates` SNS topic.

Parses CloudWatch alarm notifications from SNS, matches the alarm name
against a small registry of formatter templates, renders a human-readable
subject + plain-text body, and sends via SES to a single QGI ops inbox.

Filed as #412 after discovering the SNS topic had zero subscribers and
raw JSON email payloads are illegible on mobile.

## Alarm families supported

- `qgi-v191-high-country-count-*`   — drift in HIGH-country-count tier band
- `qgi-v191-median-salience-*`      — median salience drift
- `qgi-v191-country-risks-bytes-*`  — payload size drift (ALARM-ONLY, still formatted for visibility)
- `qgi-caught-exception-*`          — #409 silent-failure catches; parses (Lambda, Location)
- Fallback — any unknown alarm name gets a generic-but-readable template

## Environment variables

- `SENDER_EMAIL`    — SES-verified sender identity (e.g. `alerts@qgintelligence.com`).
- `RECIPIENT_EMAIL` — single recipient (SES sandbox requires this is also verified).
- `SES_REGION`      — optional; defaults to Lambda runtime region.

## SES sandbox caveat

AWS accounts start in SES sandbox mode: both sender AND recipient identities
must be pre-verified. Verify via:
    aws sesv2 create-email-identity --email-identity alerts@qgintelligence.com
    aws sesv2 create-email-identity --email-identity qgintelligence@gmail.com
Amin then clicks the confirmation link SES emails to each.

To exit sandbox (no recipient restriction), file a production-access
request in the SES console — not required while there's a single
recipient.
"""

import json
import logging
import os
import re

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SENDER = os.environ.get("SENDER_EMAIL", "alerts@qgintelligence.com")
RECIPIENT = os.environ.get("RECIPIENT_EMAIL", "qgintelligence@gmail.com")
SES_REGION = os.environ.get("SES_REGION") or os.environ.get("AWS_REGION", "eu-central-1")

ses = boto3.client("ses", region_name=SES_REGION)


# ---------------------------------------------------------------------------
# Formatter helpers
# ---------------------------------------------------------------------------


def _triage_footer(alarm):
    """Standard footer: CloudWatch console deep link + reasonReason."""
    name = alarm.get("AlarmName", "?")
    region = alarm.get("Region", SES_REGION).replace(" ", "").lower()
    # CloudWatch region names sometimes differ from API ("EU (Frankfurt)" vs "eu-central-1").
    # The alarm payload uses the API region in `alarm.Region` only in older SNS formats;
    # fall back to env region if unparseable.
    api_region = region if re.match(r"^[a-z]{2}-[a-z]+-\d$", region) else SES_REGION

    console_url = (
        f"https://{api_region}.console.aws.amazon.com/cloudwatch/home?region={api_region}#alarmsV2:alarm/{name}"
    )
    reason = alarm.get("NewStateReason") or alarm.get("StateReason") or "(no reason)"
    return f"\n---\nReason: {reason}\nConsole: {console_url}\n"


def format_high_country_count(alarm):
    name = alarm["AlarmName"]
    is_high = name.endswith("-high")
    direction = "above 60" if is_high else "below 15"
    cause = "score inflation or threshold drift" if is_high else "scoring collapse or upstream data loss"
    subject = f"[QGI] HIGH_COUNTRY_COUNT {direction} — check scoring"
    body = (
        f"QGI V1.9.1 HIGH_COUNTRY_COUNT drifted {direction}.\n"
        f"Target band: [25, 45] countries. Guardrail: [15, 60].\n\n"
        f"State: {alarm.get('OldStateValue', '?')} -> {alarm.get('NewStateValue', '?')}\n"
        f"When:  {alarm.get('StateChangeTime', '?')}\n\n"
        f"Likely cause: {cause}.\n\n"
        f"Triage:\n"
        f"1. Compare current country-risks.json against the last-known-good.\n"
        f"2. Check last pipeline run in Step Functions.\n"
        f"3. If HIGH count is extreme (<5 or >90), treat as potential data corruption.\n"
    )
    return subject, body + _triage_footer(alarm)


def format_median_salience(alarm):
    name = alarm["AlarmName"]
    is_high = name.endswith("-high")
    direction = "above 1.5" if is_high else "below 0.2"
    cause = "score inflation / upstream-signal break" if is_high else "score compression / scoring bug"
    subject = f"[QGI] MEDIAN_SALIENCE_SCORE {direction} — 2 runs"
    body = (
        f"QGI V1.9.1 MEDIAN_SALIENCE_SCORE {direction} for two consecutive runs.\n\n"
        f"State: {alarm.get('OldStateValue', '?')} -> {alarm.get('NewStateValue', '?')}\n"
        f"When:  {alarm.get('StateChangeTime', '?')}\n\n"
        f"Likely cause: {cause}.\n"
    )
    return subject, body + _triage_footer(alarm)


def format_country_risks_bytes(alarm):
    name = alarm["AlarmName"]
    is_high = name.endswith("-high")
    direction = "above 2 MB" if is_high else "below 200 KB"
    cause = "runaway payload / serialization regression" if is_high else "schema break / empty payload"
    subject = f"[QGI] COUNTRY_RISKS_BYTES {direction} [ALARM-ONLY]"
    body = (
        f"country-risks.json size drifted {direction}.\n\n"
        f"Likely cause: {cause}.\n\n"
        f"Not paged — ALARM-only per #381. State visible in CloudWatch console.\n"
    )
    return subject, body + _triage_footer(alarm)


def format_caught_exception(alarm):
    """#409 silent-failure alarms. Dimensions tell us which Lambda + Location."""
    dims = {d["name"]: d["value"] for d in alarm.get("Trigger", {}).get("Dimensions", [])}
    lambda_name = dims.get("Lambda", "(unknown)")
    location = dims.get("Location", "(unknown)")
    region = SES_REGION

    # CloudWatch Logs Insights URL (region-templated). URL-encoding omitted
    # to keep this readable; Logs Insights tolerates the raw form below.
    log_group = f"/aws/lambda/{lambda_name}"
    insights_url = (
        f"https://{region}.console.aws.amazon.com/cloudwatch/home"
        f"?region={region}#logsV2:logs-insights"
        f"$3FqueryDetail$3D~(end~0~start~-3600~timeType~'RELATIVE~unit~'seconds"
        f"~editorString~'fields*20*40timestamp*2c*20*40message"
        f"*0a*7c*20filter*20*40message*20like*20*2fEXCEPTION*2f"
        f"*0a*7c*20sort*20*40timestamp*20desc"
        f"*0a*7c*20limit*2050~isLiveTail~false~source~'{log_group})"
    )

    subject = f"[QGI] Silent exception in {lambda_name}"
    body = (
        f"A QGI pipeline Lambda caught-and-continued an exception (#409 silent-failure prevention).\n\n"
        f"Lambda:    {lambda_name}\n"
        f"Location:  {location}\n"
        f"State:     {alarm.get('OldStateValue', '?')} -> {alarm.get('NewStateValue', '?')}\n"
        f"When:      {alarm.get('StateChangeTime', '?')}\n\n"
        f"Triage:\n"
        f"1. CloudWatch Logs Insights (link below) scoped to {log_group}\n"
        f"2. Filter by [EXCEPTION] for the last hour\n"
        f"3. The exception message identifies the specific failure mode\n\n"
        f"Context:\n"
        f"Class introduced 2026-04-22 after finalize Lambda silently stopped regenerating\n"
        f"country-risks.json for 2 days. Single-event alarm: one catch anywhere pages immediately.\n"
        f"\n---\nLogs Insights: {insights_url}\n"
    )
    return subject, body


def format_fallback(alarm):
    name = alarm.get("AlarmName", "Unknown")
    subject = f"[QGI] {name}: {alarm.get('NewStateValue', '?')}"
    body = (
        f"QGI CloudWatch alarm fired but no specific formatter matched the name.\n\n"
        f"Alarm: {name}\n"
        f"State: {alarm.get('OldStateValue', '?')} -> {alarm.get('NewStateValue', '?')}\n"
        f"When:  {alarm.get('StateChangeTime', '?')}\n"
        f"Reason: {alarm.get('NewStateReason') or alarm.get('StateReason', '(n/a)')}\n\n"
        f"Add a handler for this alarm family in qgi-sns-alarm-formatter/lambda_function.py.\n"
    )
    return subject, body + _triage_footer(alarm)


# ---------------------------------------------------------------------------
# Dispatcher — match alarm name prefix to a formatter.
# ---------------------------------------------------------------------------

FORMATTERS = [
    (re.compile(r"^qgi-v191-high-country-count-"), format_high_country_count),
    (re.compile(r"^qgi-v191-median-salience-"), format_median_salience),
    (re.compile(r"^qgi-v191-country-risks-bytes-"), format_country_risks_bytes),
    (re.compile(r"^qgi-caught-exception-"), format_caught_exception),
]


def format_alarm(alarm):
    """Select a formatter by alarm name. Returns (subject, body)."""
    name = alarm.get("AlarmName", "")
    for pattern, formatter in FORMATTERS:
        if pattern.match(name):
            return formatter(alarm)
    return format_fallback(alarm)


def lambda_handler(event, context):
    """Entry point. SNS delivers CloudWatch alarm records."""
    records = event.get("Records", [])
    logger.info(f"Received {len(records)} SNS record(s)")

    sent = 0
    failed = 0
    for record in records:
        sns_msg = record.get("Sns", {}).get("Message", "{}")
        try:
            alarm = json.loads(sns_msg)
        except json.JSONDecodeError:
            logger.warning(
                f"SNS message not valid JSON; forwarding as-is under fallback. First 200 chars: {sns_msg[:200]!r}"
            )
            alarm = {"AlarmName": "(malformed-sns-payload)", "StateReason": sns_msg}

        subject, body = format_alarm(alarm)

        try:
            ses.send_email(
                Source=SENDER,
                Destination={"ToAddresses": [RECIPIENT]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
                },
            )
            sent += 1
            logger.info(f"Sent formatted alarm: {alarm.get('AlarmName')} -> {RECIPIENT}")
        except Exception:  # noqa: BLE001 — let Lambda fail so SNS retries
            failed += 1
            logger.exception(f"SES send_email failed for alarm {alarm.get('AlarmName')}; re-raising for SNS retry")
            raise

    return {"statusCode": 200, "sent": sent, "failed": failed}
