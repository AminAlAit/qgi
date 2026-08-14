"""diff_walk_summaries.py — §2.5 BIT-IDENTITY canary diff harness.

Pre-FLEET-PERF canary vs post-FLEET-PERF re-canary must produce IDENTICAL
selection / windows / coverage / AUC / verdict. If any compared field diverges,
FLEET-PERF #129 violates the methodology contract and waves are BLOCKED.

Usage:
    python scripts/diff_walk_summaries.py \\
        --baseline path/to/f-ml-1-poc-summary.json \\
        --candidate s3://qgi-data-lake-771606957899/ml-results/technology_breakthrough/canary-techbreak-20260528-NNNNNN/f-ml-1-poc-summary.json \\
        [--out diff-result.json]

Exit codes:
    0  BIT_IDENTICAL_PASS — every compared field matches exactly
    1  BIT_IDENTICAL_FAIL — one or more fields diverge (see stdout / --out)

boto3 is used for s3:// URIs; no boto3 for plain local paths. No pandas,
no numpy. Pure stdlib + boto3 (optional, pulled in only when needed).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# S3 / local loader
# ---------------------------------------------------------------------------


def _load_json(uri: str) -> dict[str, Any]:
    """Load a JSON summary from a local path or an s3:// URI."""
    if uri.startswith("s3://"):
        return _load_s3_json(uri)
    return json.loads(Path(uri).read_text(encoding="utf-8"))


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    """Return (bucket, key) from an s3://bucket/key URI."""
    without_scheme = uri[len("s3://"):]
    slash = without_scheme.index("/")
    return without_scheme[:slash], without_scheme[slash + 1:]


def _load_s3_json(uri: str) -> dict[str, Any]:
    """F2 per QA PR review: catch the common boto3 ClientError cases (NoSuchKey,
    NoSuchBucket, 403 AccessDenied) and re-raise as a clear SystemExit instead of a raw
    botocore traceback in CI logs. The CALLER (gate) still gets exit code != 0 — this
    only improves the error message; nothing converts a load failure into a false PASS."""
    import boto3  # type: ignore[import]
    from botocore.exceptions import ClientError  # type: ignore[import]

    bucket, key = _parse_s3_uri(uri)
    s3 = boto3.client("s3")
    try:
        resp = s3.get_object(Bucket=bucket, Key=key)
        return json.loads(resp["Body"].read().decode("utf-8"))
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "Unknown")
        raise SystemExit(
            f"FAILED to load {uri}: S3 {code} — "
            f"{exc.response.get('Error', {}).get('Message', str(exc))}"
        ) from exc


# ---------------------------------------------------------------------------
# Field extraction helpers (map flat paths into potentially nested summaries)
# ---------------------------------------------------------------------------

_SENTINEL = object()  # used to distinguish "key absent" from None


def _deep_get(obj: Any, path: str) -> Any:
    """Traverse a dotted field path, e.g. 'global_loco.ci95_lo'.

    Returns _SENTINEL if any key along the path is absent.
    """
    parts = path.split(".")
    cur = obj
    for part in parts:
        if not isinstance(cur, dict) or part not in cur:
            return _SENTINEL
        cur = cur[part]
    return cur


# ---------------------------------------------------------------------------
# Per-field comparison
# ---------------------------------------------------------------------------


def _compare_scalar(field: str, bval: Any, cval: Any) -> dict[str, Any]:
    """Compare two scalar values and return a result row."""
    both_missing = bval is _SENTINEL and cval is _SENTINEL
    if both_missing:
        return {
            "field": field,
            "status": "BOTH_ABSENT",
            "baseline": None,
            "candidate": None,
            "note": "Field absent in both summaries — skipped.",
        }
    if bval is _SENTINEL:
        return {
            "field": field,
            "status": "FAIL",
            "baseline": None,
            "candidate": cval,
            "note": "Field absent in baseline but present in candidate.",
        }
    if cval is _SENTINEL:
        return {
            "field": field,
            "status": "FAIL",
            "baseline": bval,
            "candidate": None,
            "note": "Field absent in candidate but present in baseline.",
        }
    match = bval == cval
    return {
        "field": field,
        "status": "PASS" if match else "FAIL",
        "baseline": bval,
        "candidate": cval,
    }


def _compare_list_field(field: str, bval: Any, cval: Any) -> dict[str, Any]:
    """Compare a list-valued field (e.g. selected_indicators)."""
    # Let _compare_scalar handle absent/present asymmetry first
    row = _compare_scalar(field, bval, cval)
    if row["status"] in ("BOTH_ABSENT", "FAIL"):
        return row
    # Both present — list equality is order-sensitive per spec
    match = (bval == cval)
    return {
        "field": field,
        "status": "PASS" if match else "FAIL",
        "baseline": bval,
        "candidate": cval,
    }


def _compare_history(baseline: dict, candidate: dict) -> list[dict[str, Any]]:
    """Compare the history list per-step (step, candidate, window, auc,
    lift_over_previous).  Returns one result row per mismatch encountered
    across all steps, plus one summary row."""
    bh = _deep_get(baseline, "greedy_outer_loop.history")
    ch = _deep_get(candidate, "greedy_outer_loop.history")
    rows: list[dict[str, Any]] = []

    if bh is _SENTINEL and ch is _SENTINEL:
        rows.append({
            "field": "greedy_outer_loop.history",
            "status": "BOTH_ABSENT",
            "baseline": None,
            "candidate": None,
        })
        return rows

    if bh is _SENTINEL or ch is _SENTINEL:
        rows.append({
            "field": "greedy_outer_loop.history",
            "status": "FAIL",
            "baseline": bh if bh is not _SENTINEL else None,
            "candidate": ch if ch is not _SENTINEL else None,
            "note": "history absent in one summary",
        })
        return rows

    if len(bh) != len(ch):
        rows.append({
            "field": "greedy_outer_loop.history.length",
            "status": "FAIL",
            "baseline": len(bh),
            "candidate": len(ch),
            "note": f"history step counts differ: {len(bh)} vs {len(ch)}",
        })
        # Still compare what we can
    # F1 per QA PR review: selected_after is the running selection state at each step;
    # a divergence here would betray a greedy-reduce-order regression even if the final
    # selected_indicators list happens to coincide (a tie-break edge could shuffle history
    # without changing the terminal state — that's still a §2.5 violation worth flagging).
    for idx, (bs, cs) in enumerate(zip(bh, ch)):
        for key in ("candidate", "window", "auc", "lift_over_previous", "selected_after"):
            field_path = f"greedy_outer_loop.history[{idx}].{key}"
            bv = bs.get(key, _SENTINEL)
            cv = cs.get(key, _SENTINEL)
            # Use object identity for absent check (dicts won't have _SENTINEL)
            if bv == _SENTINEL:
                bv = _SENTINEL
            if cv == _SENTINEL:
                cv = _SENTINEL
            rows.append(_compare_scalar(field_path, bv, cv))
    # If candidate has MORE steps than baseline, flag them as extra
    for idx in range(len(bh), len(ch)):
        rows.append({
            "field": f"greedy_outer_loop.history[{idx}]",
            "status": "FAIL",
            "baseline": None,
            "candidate": ch[idx],
            "note": "extra step in candidate not present in baseline",
        })
    return rows


def _compare_per_cohort(baseline: dict, candidate: dict) -> list[dict[str, Any]]:
    """Compare per_cohort.*.loco_auc for each cohort present in either summary."""
    rows: list[dict[str, Any]] = []
    bpc = _deep_get(baseline, "per_cohort")
    cpc = _deep_get(candidate, "per_cohort")
    if bpc is _SENTINEL and cpc is _SENTINEL:
        return rows
    if bpc is _SENTINEL or cpc is _SENTINEL:
        rows.append({
            "field": "per_cohort",
            "status": "FAIL",
            "baseline": bpc if bpc is not _SENTINEL else None,
            "candidate": cpc if cpc is not _SENTINEL else None,
            "note": "per_cohort absent in one summary",
        })
        return rows
    all_cohorts = sorted(set(list(bpc.keys()) + list(cpc.keys())))
    for cohort in all_cohorts:
        field_path = f"per_cohort.{cohort}.loco_auc"
        bv = bpc.get(cohort, {}).get("loco_auc", _SENTINEL) if isinstance(bpc.get(cohort), dict) else _SENTINEL
        cv = cpc.get(cohort, {}).get("loco_auc", _SENTINEL) if isinstance(cpc.get(cohort), dict) else _SENTINEL
        rows.append(_compare_scalar(field_path, bv, cv))
    return rows


# ---------------------------------------------------------------------------
# Canonical field list per §2.5 contract
# ---------------------------------------------------------------------------

# Scalar fields compared via dotted deep-get.  The paths are checked against
# the §10 emit produced by run_f_ml_1_poc._main().
SCALAR_FIELDS = [
    "verdict",
    # Walk-path divergence flag (QA PR review BLOCKER-1): a §2.5 violation can also
    # manifest as the new walk taking the early-abort branch when the old one didn't (or
    # vice versa). selected_indicators + AUC are only meaningful in-context of which path
    # the greedy loop took; this flag is the path discriminator.
    "greedy_outer_loop.early_abort_floor_unreachable",
    # chosen_window lives at greedy_outer_loop.chosen_window in the summary
    "greedy_outer_loop.chosen_window",
    # final_global_auc comes from greedy_outer_loop.final_global_auc
    "greedy_outer_loop.final_global_auc",
    # global_loco block (BCa bootstrap CI). ci80 bounds added per FU-F3: same bootstrap +
    # seed; a divergence there without ci95 divergence is unlikely but a real emit field.
    "global_loco.auc",
    "global_loco.ci80_lo",
    "global_loco.ci80_hi",
    "global_loco.ci95_lo",
    "global_loco.ci95_hi",
    # coverage block (sample-truncation audit)
    "coverage_audit.n_pos_survive",
    "coverage_audit.n_countries_survive",
    "coverage_audit.pos_coverage",
    "coverage_audit.neg_coverage",
    # Top-level §2.5 invariants added per QA PR review FU-F3. Each is a direct emit
    # field whose value reflects driver behaviour and would betray a perf-fix regression
    # not visible in AUC alone:
    #   - architecture: XGBoost vs LR/MLP fallback (must NOT change)
    #   - borderline_lock: a flip from false→true on the same data means a gate-eval drift
    #   - n_positives / n_negatives: sample-build inputs; flips signal a different cohort
    #   - temporal_confound_auc: era-stratified diagnostic; signals stratification drift
    "architecture",
    "borderline_lock",
    "n_positives",
    "n_negatives",
    "temporal_confound_auc",
    # panel_fingerprint is nested inside greedy config; it's also available
    # via compute_naive_baselines; run_f_ml_1_poc doesn't embed it at root
    # but does embed the config_signature via the greedy checkpoint envelope.
    # The summary JSON (f-ml-1-poc-summary.json) does NOT have a root-level
    # panel_fingerprint field — emit confirmed by reading _main() lines 1791-1866.
    # We check univariate_screen.top_n_indicators as a proxy for screen parity.
]

LIST_FIELDS = [
    # Order-sensitive per §2.5
    "greedy_outer_loop.selected_indicators",
    "univariate_screen.top_n_indicators",
]


# ---------------------------------------------------------------------------
# Master comparison
# ---------------------------------------------------------------------------


def compare_summaries(baseline: dict, candidate: dict) -> dict[str, Any]:
    """Compare two f-ml-1-poc-summary dicts.  Returns a result dict with
    `verdict` (BIT_IDENTICAL_PASS | BIT_IDENTICAL_FAIL) and `rows` (per-field
    detail list)."""
    rows: list[dict[str, Any]] = []

    # Scalar fields
    for field in SCALAR_FIELDS:
        bv = _deep_get(baseline, field)
        cv = _deep_get(candidate, field)
        rows.append(_compare_scalar(field, bv, cv))

    # List fields (order-sensitive)
    for field in LIST_FIELDS:
        bv = _deep_get(baseline, field)
        cv = _deep_get(candidate, field)
        rows.append(_compare_list_field(field, bv, cv))

    # History (per-step rows)
    rows.extend(_compare_history(baseline, candidate))

    # Per-cohort loco_auc
    rows.extend(_compare_per_cohort(baseline, candidate))

    # Classify
    fail_rows = [r for r in rows if r["status"] == "FAIL"]
    overall = "BIT_IDENTICAL_FAIL" if fail_rows else "BIT_IDENTICAL_PASS"
    return {
        "verdict": overall,
        "pass_count": len([r for r in rows if r["status"] == "PASS"]),
        "fail_count": len(fail_rows),
        "both_absent_count": len([r for r in rows if r["status"] == "BOTH_ABSENT"]),
        "divergences": fail_rows,
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Markdown table renderer
# ---------------------------------------------------------------------------


def _md_row(cells: list[str]) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |"


def render_markdown(result: dict[str, Any]) -> str:
    verdict = result["verdict"]
    lines = [
        f"## §2.5 BIT-IDENTITY canary diff — {verdict}",
        "",
        f"Pass: {result['pass_count']} | "
        f"Fail: {result['fail_count']} | "
        f"Both-absent: {result['both_absent_count']}",
        "",
        _md_row(["Field", "Status", "Baseline", "Candidate"]),
        _md_row(["---", "---", "---", "---"]),
    ]
    for row in result["rows"]:
        status = row["status"]
        emoji = {"PASS": "PASS", "FAIL": "**FAIL**", "BOTH_ABSENT": "_absent_"}.get(status, status)
        bv = _truncate(row.get("baseline"))
        cv = _truncate(row.get("candidate"))
        lines.append(_md_row([row["field"], emoji, bv, cv]))
    lines += [""]
    if result["fail_count"] == 0:
        # BLOCKER-2 per QA PR review: PASS-with-BOTH_ABSENT must surface the absent
        # fields so the operator must acknowledge them. A silent PASS would let waves
        # fire when the candidate stopped emitting required keys (driver regression
        # masking itself as field-absence-symmetry).
        absent = [r["field"] for r in result["rows"] if r["status"] == "BOTH_ABSENT"]
        msg = ("> PASS: all compared fields are bit-identical. "
               "Wave fan-out is cleared for FLEET-PERF #129.")
        if absent:
            msg += (f"\n>\n> NOTE: {len(absent)} field(s) were absent in BOTH summaries "
                    f"and skipped — verify this is acceptable: {absent}")
        lines.append(msg)
    else:
        lines.append(
            f"> **FAIL: {result['fail_count']} field(s) diverge. "
            "FLEET-PERF #129 is BLOCKED until the re-canary matches the baseline.**"
        )
    return "\n".join(lines)


def _truncate(val: Any, limit: int = 80) -> str:
    if val is None:
        return "—"
    s = str(val)
    return s if len(s) <= limit else s[:limit - 3] + "..."


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "§2.5 BIT-IDENTITY canary diff: compare two f-ml-1-poc-summary.json "
            "files (local paths or s3:// URIs). Exit 0 = PASS, 1 = FAIL."
        )
    )
    p.add_argument(
        "--baseline",
        required=True,
        help="Path or s3:// URI of the pre-FLEET-PERF canary summary JSON.",
    )
    p.add_argument(
        "--candidate",
        required=True,
        help="Path or s3:// URI of the post-FLEET-PERF re-canary summary JSON.",
    )
    p.add_argument(
        "--out",
        default=None,
        help="Optional path for machine-readable JSON output {verdict, divergences}.",
    )
    return p


def _main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    baseline = _load_json(args.baseline)
    candidate = _load_json(args.candidate)

    result = compare_summaries(baseline, candidate)

    print(render_markdown(result))

    if args.out:
        out_path = Path(args.out)
        out_path.write_text(
            json.dumps(
                {"verdict": result["verdict"], "divergences": result["divergences"]},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"\nMachine output → {out_path}")

    return 0 if result["verdict"] == "BIT_IDENTICAL_PASS" else 1


if __name__ == "__main__":
    sys.exit(_main())
