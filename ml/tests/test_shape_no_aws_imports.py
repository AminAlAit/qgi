"""Guard rail: the shape-feature R&D path must NOT import boto3/botocore.

Per qgi-aws-tf#810 (cost-incident-2026-05-16 post-mortem + R&D quest binding):
the QGI-R&D | 002 shape-feature build is laptop-local. Any future drift toward
"helpful" AWS uploads would violate the QGI-R&D | 001 cost rule ($50 cumulative
cap, per-run founder approval) and the `feedback_no_pipeline_runs_without_approval.md`
standing rule.

The 2026-05-16/17 incident ($139.08 spike from a manual `recipes_only` SFN
execution) demonstrated the failure mode: even with cost guards on the
`QGI-Lambda-Workgroup`, an unbounded AWS-touching workflow can run for 17.5h
overnight. The shape-feature work must NOT acquire that capability through
careless dependency drift.

This test fails the suite the moment anyone imports `boto3` or `botocore` in
either the shape-prototype fit utilities or the fitter script. Catching it at
test time is far cheaper than catching it on AWS Cost Explorer the next morning.

Failure recovery: if a legitimate AWS need arises (e.g., Stage 8 deploy in
ML-Opus #648), file a ticket and remove this test only after the path is
properly gated through a `qgi-qgi-agent-readonly` IAM role + preflight check.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
for _p in (SRC_ROOT, SCRIPTS_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


_BANNED_MODULES = ("boto3", "botocore")


def _ensure_module_not_in_sys_modules(name: str) -> None:
    """Re-load the target module and assert that the banned modules are absent."""
    # Drop the target from cache so the import re-executes its top-level statements.
    sys.modules.pop(name, None)
    # Drop any cached banned modules so an import elsewhere in the test suite
    # does not produce a false negative for this module's import surface.
    for banned in _BANNED_MODULES:
        sys.modules.pop(banned, None)

    importlib.import_module(name)

    for banned in _BANNED_MODULES:
        assert banned not in sys.modules, (
            f"{name!r} import path pulls in {banned!r}. The shape-feature R&D path "
            f"must remain AWS-free per qgi-aws-tf#810 + the cost-incident-2026-05-16 "
            f"post-mortem. If a legitimate AWS need arose, file a ticket + scope a "
            f"qgi-qgi-agent-readonly IAM role first, then revisit this guard."
        )


def test_shape_prototype_fit_utils_does_not_import_boto3() -> None:
    """src/shape_prototype_fit_utils.py must not transitively import boto3/botocore."""
    _ensure_module_not_in_sys_modules("shape_prototype_fit_utils")


def test_fit_shape_prototype_does_not_import_boto3() -> None:
    """scripts/fit_shape_prototype.py must not transitively import boto3/botocore."""
    _ensure_module_not_in_sys_modules("fit_shape_prototype")
