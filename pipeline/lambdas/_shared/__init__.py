"""Shared Python modules bundled into every Lambda by the deploy workflow.

This directory is the canonical home for code that needs to be identical
across multiple Lambdas — see `pattern_tier.py` (#558) for the first
consumer. The deploy workflow at `.github/workflows/deploy-lambdas.yml`
copies `_shared/*.py` into each Lambda's bundle before zipping, so each
Lambda runtime gets its own copy.

Lambdas import shared modules via `from _shared.<module> import ...`.
The `_shared` package directory is bundled at the root of each Lambda's
zip, so the import path resolves the same in production as in local
tests.

NOTE: do NOT put runtime dependencies (boto3, pandas, numpy) here. Each
shared module must be importable with stdlib only, otherwise the Lambda
bundle's `pip install -r requirements.txt` step would need to be aware
of `_shared`'s deps too. Keep this dir for pure logic + constants.
"""
