"""Reusable ML modules used by qgi-ml/scripts/.

Convention shift from the historical scripts-only layout (per qgi-ml README.md):

- qgi-ml/scripts/      one-shot orchestrators (training / scoring / audits)
- qgi-ml/src/          reusable library code shared across scripts and tests
- qgi-ml/tests/        pytest tests; import scripts AND src via sys.path

Modules:
    ml_registry          model artifact + training-data + script fingerprint helpers
    feature_engineering  indicator-panel reads, first-difference, rolling Z-score, MICE

Pre-registered Stage 0 deliverable per docs/specs/internal/ops/ml-track/stage-0-pre-registration.md.
"""
