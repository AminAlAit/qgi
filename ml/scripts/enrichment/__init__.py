"""QGI indicator-enrichment pipeline (stages 0-5).

A reusable, provider-agnostic toolkit for growing the TE indicator pool
(109 -> 250 -> 500) with a deterministic cost-preflight at every step.

Stages:
  0  registry        - unified candidate registry + status lifecycle
  1  vet             - automated quality gate (history/coverage/variance/stationarity/leak/license)
  3  challenger_gate - which walked recipes a candidate set could actually change (THIS is the brain)
  4  manifest        - build the re-walk runnable_jobs + cost forecast
  5  publish         - vintage append + catalog update + ROI ledger

Stage 2 (ingest) is the per-provider Fargate fetchers in qgi-pipeline/batch/.
Design: docs/specs/internal/ops/ml-track/indicator-enrichment-cicd-design.md
"""
