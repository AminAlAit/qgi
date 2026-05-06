# ---------------------------------------------------------------------------
# ECR — QGI pipeline container images (management account)
#
# One repo's policy lives here:
#   1. qgi-pipeline-b-scdi-finder — Phase 2 SCDI finder (EC2 Batch)
#
# The repo itself is hand-built (not imported into TF state); we only
# manage its repository policy. dscdi-finder lives in this file too —
# its TF-managed repo + policy are further down.
#
# (indicator-fetcher mgmt-mirror was deleted 2026-05-11 per #635 closure;
# Phase 1 fetchers now live per-environment in staging-account ECR
# managed by qgi-infra, see tombstone block below.)
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "scdi_finder_ecr" {
  # Cross-account pull access for QGI pipeline environments using
  # account-root principals (per AWS expert consult 2026-05-10 + #661
  # reconcile). The 3-account-root pattern was hand-built 2025-09; this
  # TF block now matches that live policy exactly so terraform plan
  # no-ops on this resource.
  #
  # Push access is intentionally NOT in this repo policy. The GHA OIDC
  # role `github-actions-qgi-ecr-push` is authorized to push to
  # scdi-finder via the IAM policy
  # `GitHubActionsECR-QGI-pB-SCDI-Finder-PushAccess` — the policy
  # *document* itself is hand-built in the AWS console (predates this
  # TF repo), but the policy-to-role *attachment* is TF-managed via
  # `aws_iam_role_policy_attachment.qgi_ecr_push` in iam_oidc_roles.tf.
  # Push grant lives at the IAM role-side (managed-policy attachment),
  # not at the repo-policy side. dscdi-finder (further down) uses a
  # different pattern — its push grant lives on the role's inline
  # `ECRPushDSCDIFinder` policy.
  #
  # Why account-root identifiers rather than specific role ARNs: any
  # principal in qa / staging / prod with `ecr:BatchGetImage` etc in
  # its own IAM policy can pull from this repo. Tightening to specific
  # role ARNs (the previous TF source) was both more brittle (every new
  # Fargate role would need an update) and never deployed (live policy
  # has used :root since 2025-09).
  statement {
    sid    = "AllowCrossAccountPull"
    effect = "Allow"
    principals {
      type = "AWS"
      identifiers = [
        "arn:aws:iam::${var.prod_account_id}:root",
        "arn:aws:iam::${var.staging_account_id}:root",
        "arn:aws:iam::${var.qa_account_id}:root",
      ]
    }
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
  }
}

resource "aws_ecr_repository_policy" "scdi_finder" {
  repository = "qgi-pipeline-b-scdi-finder"
  policy     = data.aws_iam_policy_document.scdi_finder_ecr.json
}

# ---------------------------------------------------------------------------
# qgi-pipeline-a-indicator-fetcher — DELETED 2026-05-11 (#635 closure)
#
# Originally added under #152 Path A (consolidate ECR push targets in the
# management account). Path A was effectively parked: by 2025-Q4 the
# qgi-pipeline ecr-push.yml workflow was pushing the indicator-fetcher
# image to BOTH the management mirror AND the staging-account ECR, and
# the live runtime path settled on the staging-account repo (managed by
# qgi-infra/modules/batch/main.tf and authorized by qgi-infra/modules/
# iam/main.tf's `github_actions_ecr_push` role). The management-account
# mirror never had consumers in production.
#
# Today (2026-05-11) the management-account ECR repo
# `qgi-pipeline-a-indicator-fetcher` does NOT exist in AWS — verified
# via `aws ecr describe-repositories --repository-names
# qgi-pipeline-a-indicator-fetcher` → RepositoryNotFoundException.
# The TF source described an intended state that AWS never reached.
#
# Deleting this block + the matching `ECRPushIndicatorFetcher` inline
# policy in iam_oidc_roles.tf eliminates ~92 lines of dead Path-A
# debris and removes the 3 phantom CREATE diffs from `terraform plan`.
# The promised permission from #635 is already satisfied by the
# staging-account push policy in qgi-infra (PR #23, merged 2026-05-11,
# includes ecr:BatchGetImage + ecr:DescribeImages).
#
# Architectural rationale (2026-05-11 architecture review): Phase 1
# fetchers are per-environment data jobs and SHOULD live in each
# environment's local ECR (qgi-infra owns those). Phase 2 B-stage
# Batch images (scdi-finder, dscdi-finder) are stateless compute that
# runs identically across all environments and CORRECTLY lives in
# management as a shared-services ECR with cross-account pull. The
# split is principled, not accidental.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# qgi-pipeline-b-dscdi-finder (Phase 5 v0.0b Stage F preflight) — TF-managed
#
# DSCDI = Detrended Similar-Country Dynamic Indicator. Companion to scdi-finder;
# additive scope per the 2026-05-04 founder amendment + 2026-05-05 unanimous
# 6-way mini-Majles CSD reconvene DECISION. Greenfield repo (TF-managed from
# the start; not hand-built like scdi-finder), so the resource policy follows
# the indicator-fetcher pattern (data + aws_ecr_repository_policy).
# ---------------------------------------------------------------------------

resource "aws_ecr_repository" "dscdi_finder" {
  name                 = "qgi-pipeline-b-dscdi-finder"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Project     = "qgi"
    Environment = "shared"
    ManagedBy   = "terraform"
    Owner       = "amin.al-ait"
  }
}

resource "aws_ecr_lifecycle_policy" "dscdi_finder" {
  repository = aws_ecr_repository.dscdi_finder.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = {
        type = "expire"
      }
    }]
  })
}

data "aws_iam_policy_document" "dscdi_finder_ecr" {
  # GitHub Actions push access — same role as scdi-finder + indicator-fetcher.
  # Repo policy authorizes; role-level inline policy
  # (qgi_ecr_push_dscdi_finder in iam_oidc_roles.tf) grants the push actions.
  statement {
    sid    = "GitHubActionsPush"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = [aws_iam_role.qgi_ecr_push.arn]
    }
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
  }

  # Cross-account pull access — staging only at this stage. QA + prod will
  # be added when the multi-environment Stage F rollout fires (post end-of-
  # cascade-mandate authorization).
  #
  # Account-root principal pattern (AWS principal-engineer best practice).
  # The earlier named-role list (qgi-ecs-instance-role + qgi-batch-job-role)
  # missed qgi-fargate-execution-role — the role Batch actually uses for
  # cross-account image pulls — and caused the 2026-05-10 Stage F smoke
  # failure (CannotPullImageManifestError, job a64f5dfa). See AWS expert
  # consult 2026-05-10 + scdi_finder_ecr above for the rationale and the
  # consumer-side IAM-simulator pre-flight check.
  statement {
    sid    = "CrossAccountECRPull"
    effect = "Allow"
    principals {
      type = "AWS"
      identifiers = [
        "arn:aws:iam::${var.staging_account_id}:root",
      ]
    }
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
  }
}

resource "aws_ecr_repository_policy" "dscdi_finder" {
  repository = aws_ecr_repository.dscdi_finder.name
  policy     = data.aws_iam_policy_document.dscdi_finder_ecr.json
}
