"""qgi-recipe-fleet-frontend-sync — fires a workflow_dispatch on qgi-frontend
that pulls the bake-output S3 prefix into a fresh `data/te-fleet-run-{N}/` dir,
appends the new vintage's rows to the cross-vintage `country-rank-history.json`,
and opens a PR.

Context:
  qgi-aws-tf#973 (lane 2 of the AWS-native pipeline build). Mirrors the
  existing `qgi-frontend-bake-trigger` Lambda pattern (Lambda fires
  workflow_dispatch; workflow does the heavy lifting). Architectural pick
  decided in this session: Lambda → PR (auditability) rather than direct
  S3-to-Vercel webhook.

Trigger:
  SFN Task state — Step Functions invokes this Lambda after the
  `Bake Frontend Corpus` Batch step succeeds.

Input event (from SFN):
    {
      "vintage_s3_prefix": "frontend-data/te-fleet-run-2-<sfn-exec-name>/",
      "execution_name":    "<sfn-exec-name>",
      "vintage":           "fleet-run-2-2026-08-15"   // optional
    }

Output:
    {
      "dispatched": true,
      "status":     204,
      "inputs":     { ... },
      "workflow_run_id_hint": null    // GitHub doesn't return the run-id;
                                      // workflow surfaces it in its own logs
    }

Auth:
  Reads a fine-grained GitHub PAT from AWS Secrets Manager. Reuses the
  existing `qgi-github-frontend-dispatch-pat` secret (same PAT can dispatch
  any workflow on qgi-frontend with `actions:write`).

Observability:
  Logs the input event, the dispatch payload, and the HTTP response code.
  Raises RuntimeError on non-204 GitHub response so CloudWatch's
  `qgi-caught-exception-*` family surfaces failures via the SNS alarm
  formatter.

Environment:
  GITHUB_OWNER             — default "AminAlAit"
  GITHUB_REPO              — default "qgi-frontend"
  GITHUB_WORKFLOW_FILE     — default "sync-te-fleet-vintage.yml"
  GITHUB_REF               — default "main"
  GITHUB_PAT_SECRET_NAME   — default "qgi-github-frontend-dispatch-pat"
  S3_BUCKET                — default "qgi-data-lake-771606957899"
"""

from __future__ import annotations

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
GITHUB_WORKFLOW_FILE = os.environ.get("GITHUB_WORKFLOW_FILE", "sync-te-fleet-vintage.yml")
GITHUB_REF = os.environ.get("GITHUB_REF", "main")
GITHUB_PAT_SECRET_NAME = os.environ.get("GITHUB_PAT_SECRET_NAME", "qgi-github-frontend-dispatch-pat")
AWS_ACCOUNT_ID = os.environ.get("AWS_ACCOUNT_ID", "771606957899")
S3_BUCKET = os.environ.get("S3_BUCKET", f"qgi-data-lake-{AWS_ACCOUNT_ID}")

GITHUB_API_TIMEOUT = 10  # seconds


def _get_pat(secretsmanager_client=None) -> str:
    """Fetch the GitHub PAT from Secrets Manager. Identical contract to the
    `qgi-frontend-bake-trigger` Lambda — same secret, same shape."""
    client = secretsmanager_client or boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=GITHUB_PAT_SECRET_NAME)
    pat = resp.get("SecretString")
    if not pat:
        raise RuntimeError(f"Secret {GITHUB_PAT_SECRET_NAME} has no SecretString (binary secrets not supported).")
    return pat.strip()


def _dispatch_workflow(pat: str, inputs: dict, urlopen=None) -> int:
    """POST to GitHub's workflow_dispatch endpoint. Returns the HTTP status
    code. Raises RuntimeError on non-204."""
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
            "User-Agent": "qgi-recipe-fleet-frontend-sync",
        },
    )
    opener = urlopen or urllib.request.urlopen
    try:
        with opener(req, timeout=GITHUB_API_TIMEOUT) as resp:
            status = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"workflow_dispatch failed: HTTP {exc.code} — {body}") from exc

    if status != 204:
        raise RuntimeError(f"workflow_dispatch returned HTTP {status}; expected 204.")
    return status


def _validate_event(event: dict) -> tuple[str, str, str | None]:
    """Pull `vintage_s3_prefix` + `execution_name` from the event. Fails loud
    on missing or empty values — SFN should always supply both."""
    vintage_s3_prefix = (event or {}).get("vintage_s3_prefix", "").strip()
    execution_name = (event or {}).get("execution_name", "").strip()
    vintage = (event or {}).get("vintage")  # optional

    if not vintage_s3_prefix:
        raise ValueError("Event is missing required field: vintage_s3_prefix")
    if not execution_name:
        raise ValueError("Event is missing required field: execution_name")
    # Defensive: ensure the prefix ends with "/" so the workflow doesn't have
    # to disambiguate `te-fleet-run-2/MANIFEST.json` vs `te-fleet-run-2-x/`.
    if not vintage_s3_prefix.endswith("/"):
        vintage_s3_prefix = vintage_s3_prefix + "/"
    return vintage_s3_prefix, execution_name, vintage


def lambda_handler(event, context):
    """Entry point.

    Flow:
      1. Validate the SFN event (vintage_s3_prefix + execution_name required).
      2. Fetch the GitHub PAT from Secrets Manager.
      3. POST workflow_dispatch on qgi-frontend with the S3 prefix + exec name
         as inputs. The workflow handles: checkout main; aws s3 sync to a new
         data/te-fleet-run-{N}/ dir; append rows to the cross-vintage
         country-rank-history.json; commit; push; open PR.
    """
    logger.info("Received event: %s", json.dumps(event)[:2000])

    vintage_s3_prefix, execution_name, vintage = _validate_event(event)

    pat = _get_pat()
    inputs = {
        "s3_bucket": S3_BUCKET,
        "vintage_s3_prefix": vintage_s3_prefix,
        "execution_name": execution_name,
        "vintage": vintage or execution_name,
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
    return {
        "dispatched": True,
        "status": status,
        "inputs": inputs,
        "workflow_run_id_hint": None,
    }
