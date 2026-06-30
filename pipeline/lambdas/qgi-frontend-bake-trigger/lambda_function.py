"""
Frontend bake trigger — fires a `workflow_dispatch` on `qgi-frontend` when
the pipeline publishes a new `dashboard/country-risks.json` to S3.

Context:
  #417 Option C. After the pipeline writes `dashboard/country-risks.json`,
  the frontend repo needs a fresh bake of `data/country-risks.json` so
  Vercel's next deploy picks it up. Pre-automation this was a manual
  copy-commit-push step; a forgotten copy caused /countries to 404 for
  2 days (#417). This Lambda closes the loop end-to-end: S3 PUT → Lambda
  → GitHub workflow_dispatch → Actions checkout + S3 pull + commit +
  push → Vercel auto-deploys.

Trigger:
  S3 event notification on `s3://qgi-data-lake-771606957899`, filter
  prefix `dashboard/`, suffix `country-risks.json`. Configured in
  qgi-infra.

Auth:
  Reads a fine-grained GitHub PAT from AWS Secrets Manager. Secret
  name: `qgi-github-frontend-dispatch-pat` (configurable via env).
  Required PAT scope: `actions:write` on `AminAlAit/qgi-frontend`.

Observability:
  Logs the S3 event, the workflow_dispatch HTTP response code, and the
  computed input payload. Raises on non-204 response so CloudWatch's
  `qgi-caught-exception-*` family surfaces failures via the #412 SNS
  alarm formatter.

Environment:
  GITHUB_OWNER             — default "AminAlAit"
  GITHUB_REPO              — default "qgi-frontend"
  GITHUB_WORKFLOW_FILE     — default "bake-country-risks.yml"
  GITHUB_REF               — default "main"
  GITHUB_PAT_SECRET_NAME   — default "qgi-github-frontend-dispatch-pat"
  S3_EXPECTED_KEY          — default "dashboard/country-risks.json"
                             (guard: any other key PUT is a no-op)
"""

import json
import logging
import os
import urllib.error
import urllib.request

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

GITHUB_OWNER = os.environ.get("GITHUB_OWNER", "AminAlAit")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "qgi-frontend")
GITHUB_WORKFLOW_FILE = os.environ.get("GITHUB_WORKFLOW_FILE", "bake-country-risks.yml")
GITHUB_REF = os.environ.get("GITHUB_REF", "main")
GITHUB_PAT_SECRET_NAME = os.environ.get("GITHUB_PAT_SECRET_NAME", "qgi-github-frontend-dispatch-pat")
S3_EXPECTED_KEY = os.environ.get("S3_EXPECTED_KEY", "dashboard/country-risks.json")

GITHUB_API_TIMEOUT = 10  # seconds


def _get_pat(secretsmanager_client=None):
    """Fetch the GitHub PAT from Secrets Manager.

    Secret is stored as a plain string (not JSON) for simplicity — rotate
    by updating the secret value in the AWS console.
    """
    client = secretsmanager_client or boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=GITHUB_PAT_SECRET_NAME)
    pat = resp.get("SecretString")
    if not pat:
        raise RuntimeError(
            f"Secret {GITHUB_PAT_SECRET_NAME} has no SecretString (binary secrets not supported by this Lambda)."
        )
    return pat.strip()


def _dispatch_workflow(pat, inputs, urlopen=None):
    """POST to GitHub's workflow_dispatch endpoint.

    Args:
        pat:     GitHub PAT (fine-grained or classic) with actions:write.
        inputs:  dict of workflow inputs (must match the workflow's `on.
                 workflow_dispatch.inputs` schema).
        urlopen: injectable urllib opener for testing. Defaults to
                 urllib.request.urlopen.

    Returns the HTTP status code.

    Raises RuntimeError on non-204 (GitHub returns 204 No Content on
    successful dispatch).
    """
    url = (
        f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/{GITHUB_WORKFLOW_FILE}/dispatches"
    )
    payload = json.dumps({"ref": GITHUB_REF, "inputs": inputs}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {pat}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "qgi-frontend-bake-trigger",
        },
    )
    opener = urlopen or urllib.request.urlopen
    try:
        with opener(req, timeout=GITHUB_API_TIMEOUT) as resp:
            status = resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"workflow_dispatch failed: HTTP {e.code} — {body}") from e

    if status != 204:
        raise RuntimeError(f"workflow_dispatch returned HTTP {status}; expected 204.")
    return status


def _parse_s3_event(event):
    """Extract (bucket, key, etag) from the first S3 record.

    Returns None if the event isn't an S3 PUT we recognize.
    """
    records = event.get("Records") or []
    if not records:
        return None
    record = records[0]
    s3_block = record.get("s3") or {}
    bucket = (s3_block.get("bucket") or {}).get("name")
    key = (s3_block.get("object") or {}).get("key")
    etag = (s3_block.get("object") or {}).get("eTag", "")
    if not bucket or not key:
        return None
    return (bucket, key, etag)


def lambda_handler(event, context):
    """Entry point.

    Flow:
      1. Parse the S3 event; drop anything that isn't the expected key.
      2. Fetch the GitHub PAT from Secrets Manager.
      3. POST workflow_dispatch with {bucket, key, etag} as inputs
         (the workflow uses these to log what it just baked).
    """
    logger.info("Received event: %s", json.dumps(event)[:2000])

    parsed = _parse_s3_event(event)
    if parsed is None:
        logger.warning("No S3 record in event; nothing to dispatch.")
        return {"dispatched": False, "reason": "no_s3_record"}

    bucket, key, etag = parsed
    if key != S3_EXPECTED_KEY:
        logger.info("Key %s is not the expected key %s; skip.", key, S3_EXPECTED_KEY)
        return {"dispatched": False, "reason": "wrong_key", "key": key}

    pat = _get_pat()
    inputs = {
        "bucket": bucket,
        "key": key,
        "etag": etag or "",
        "message": f"chore: bake country-risks.json ({etag[:8] if etag else 'no-etag'})",
    }
    logger.info(
        "Dispatching %s/%s on %s with inputs=%s",
        GITHUB_OWNER,
        GITHUB_REPO,
        GITHUB_REF,
        inputs,
    )
    status = _dispatch_workflow(pat, inputs)
    logger.info("workflow_dispatch OK (HTTP %s)", status)
    return {"dispatched": True, "status": status, "inputs": inputs}
