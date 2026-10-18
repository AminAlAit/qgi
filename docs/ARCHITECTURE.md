# QGI System Architecture & Multi-Account Cloud Topology

## 1. Architectural Overview

Quantitative Geopolitical Intelligence (QGI) is architected as a decoupled, multi-account cloud data lakehouse and econometric trajectory platform:

1. **Serverless Medallion Ingestion (`pipeline/`):** AWS Step Functions state machines coordinate AWS Lambda extractors and AWS Batch workers across Bronze (raw immutable payloads), Silver (temporally aligned, unit-normalized country-year and monthly panels), and Gold (14B+ cross-correlation tensors, anomaly matrices, and calibrated risk JSONs) S3 tiers.
2. **Endogenous Trajectory Engine (`ml/`):** Vectorized PyArrow, DuckDB, LightGBM, and hierarchical Bayesian state-space evaluators compute out-of-sample conflict and institutional instability probabilities across 12 flagship endogenous models.
3. **Analytical Edge Terminal (`frontend/`):** Next.js 16 App Router terminal deployed on Vercel Edge with zero-trust OIDC build-time S3 artifact verification (`scripts/fetch-build-data.mjs`).
4. **Declarative Multi-Account IaC (`infra/`):** Modular Terraform configurations managing AWS Organizations, Service Control Policies (SCPs), IAM Identity Center, and GitHub Actions OIDC federation.

---

## 2. Decoupled AWS Multi-Account Topology

| Account Tier | AWS Account ID | Primary Responsibilities |
| :--- | :--- | :--- |
| **Management / Org Root** | `111111111111` | AWS Organizations root, Service Control Policies (`scps.tf`), IAM Identity Center, org-wide CloudTrail |
| **Staging** | `222222222222` | Active Medallion S3 Lakehouse (`qgi-data-lake-222222222222`), Step Functions, AWS Batch compute, Glue/Athena |
| **QA** | `333333333333` | Pre-promotion integration verification, schema contract validation, and synthetic regression testing |
| **Production** | `444444444444` | Declarative production target for high-availability serving and lakehouse storage |

> **Quarantine Invariant:** Legacy account `555555555555` is permanently quarantined and excluded from all Terraform backends, providers, and deployment pipelines.
