# ---------------------------------------------------------------------------
# GitHub Actions OIDC Roles
#
# Eliminates static IAM keys from GitHub Actions workflows. All roles use
# the existing OIDC provider (token.actions.githubusercontent.com) which
# was bootstrapped separately.
#
# Covered repos:
#   - AminAlAit/cloud-resume-web  → S3 + CloudFront deploy
#   - AminAlAit/qgi               → ECR push + Lambda deploy
# ---------------------------------------------------------------------------


locals {
  oidc_provider_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com"
  oidc_provider_url = "token.actions.githubusercontent.com"
}

data "aws_caller_identity" "current" {}




# ---------------------------------------------------------------------------
# cloud-resume-web — S3 + CloudFront deploy role
# Replaces: aminalait-github-actions-deploy IAM user
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "cloud_resume_web_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "${local.oidc_provider_url}:sub"
      values   = ["repo:AminAlAit/cloud-resume-web:*"]
    }
  }
}

resource "aws_iam_role" "cloud_resume_web_deploy" {
  name               = "github-actions-cloud-resume-web-deploy"
  assume_role_policy = data.aws_iam_policy_document.cloud_resume_web_assume.json
  description        = "OIDC role for AminAlAit/cloud-resume-web GitHub Actions - S3 + CloudFront deploy"

  tags = {
    Project = "aminalait-website"
  }
}

data "aws_iam_policy_document" "cloud_resume_web_deploy" {
  statement {
    sid    = "S3Deploy"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
      "s3:GetObject",
    ]
    resources = [
      "arn:aws:s3:::aminalait.com",
      "arn:aws:s3:::aminalait.com/*",
    ]
  }

  statement {
    sid     = "CloudFrontInvalidate"
    effect  = "Allow"
    actions = ["cloudfront:CreateInvalidation"]
    resources = [
      "arn:aws:cloudfront::${data.aws_caller_identity.current.account_id}:distribution/E1MXUQ8TWPFAEQ",
    ]
  }
}

resource "aws_iam_role_policy" "cloud_resume_web_deploy" {
  name   = "cloud-resume-web-deploy-policy"
  role   = aws_iam_role.cloud_resume_web_deploy.id
  policy = data.aws_iam_policy_document.cloud_resume_web_deploy.json
}

# ---------------------------------------------------------------------------
# qgi-pipeline — ECR push role (closes #58)
# Replaces: github-actions-ecr-pusher IAM user (AdminAccess removed — closes #24)
# Reuses existing least-privilege policy GitHubActionsECR-QGI-pB-SCDI-Finder-PushAccess
# Trust updated from AminAlAit/qgi → AminAlAit/qgi-pipeline (scdi-finder migrated in #55)
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "qgi_ecr_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "${local.oidc_provider_url}:sub"
      values   = ["repo:AminAlAit/qgi:*"]
    }
  }
}

resource "aws_iam_role" "qgi_ecr_push" {
  name               = "github-actions-qgi-ecr-push"
  assume_role_policy = data.aws_iam_policy_document.qgi_ecr_assume.json
  description        = "OIDC role for AminAlAit/qgi GitHub Actions - ECR push (scdi-finder, indicator-fetcher, dscdi-finder)"

  tags = {
    Project = "qgi"
  }
}

resource "aws_iam_role_policy_attachment" "qgi_ecr_push" {
  role       = aws_iam_role.qgi_ecr_push.name
  policy_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/GitHubActionsECR-QGI-pB-SCDI-Finder-PushAccess"
}

# ---------------------------------------------------------------------------
# ECRPushIndicatorFetcher — DELETED 2026-05-11 (#635 closure)
#
# This inline policy was added under #152 Path A to authorize the GHA
# OIDC role `github-actions-qgi-ecr-push` to push the indicator-fetcher
# image to a management-account mirror of the staging ECR repo. Path A
# was effectively parked: the runtime path settled on staging-account
# ECR (qgi-infra/modules/iam/main.tf `github_actions_ecr_push` role),
# which now covers the indicator-fetcher repo with the same 8-action
# push subset including ecr:BatchGetImage + ecr:DescribeImages (PR #23,
# merged 2026-05-11).
#
# Live AWS state at deletion: the policy was NEVER actually attached to
# the role (verified via `aws iam list-role-policies --role-name
# github-actions-qgi-ecr-push` → only `ECRPushDSCDIFinder` present), so
# this deletion is source-only — no AWS-side resource to detach.
#
# See the matching deletion in ecr_policy.tf for the full rationale.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# qgi-pipeline — ECR push for dscdi-finder (Phase 5 v0.0b Stage F preflight)
# Separate inline policy following the indicator-fetcher pattern, so we can
# ship this TF-managed without touching the hand-managed
# GitHubActionsECR-QGI-pB-SCDI-Finder-PushAccess policy (which stays scoped
# to scdi-finder only).
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "qgi_ecr_push_dscdi_finder" {
  statement {
    sid    = "ECRAuth"
    effect = "Allow"
    actions = [
      "ecr:GetAuthorizationToken",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "ECRPushDSCDIFinder"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:DescribeImages",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [
      aws_ecr_repository.dscdi_finder.arn,
    ]
  }
}

resource "aws_iam_role_policy" "qgi_ecr_push_dscdi_finder" {
  name   = "ECRPushDSCDIFinder"
  role   = aws_iam_role.qgi_ecr_push.id
  policy = data.aws_iam_policy_document.qgi_ecr_push_dscdi_finder.json
}

# ---------------------------------------------------------------------------
# qgi-pipeline — Lambda deploy role (closes #60)
# Used by deploy-lambdas.yml in AminAlAit/qgi-pipeline to update function code.
# Scoped to qgi-* functions only; no config/env/permission changes allowed.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "qgi_lambda_deploy_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "${local.oidc_provider_url}:sub"
      values   = ["repo:AminAlAit/qgi:*"]
    }
  }
}

resource "aws_iam_role" "qgi_lambda_deploy" {
  name               = "github-actions-qgi-lambda-deploy"
  assume_role_policy = data.aws_iam_policy_document.qgi_lambda_deploy_assume.json
  description        = "OIDC role for AminAlAit/qgi GitHub Actions - Lambda function code updates"

  tags = {
    Project = "qgi"
  }
}

data "aws_iam_policy_document" "qgi_lambda_deploy" {
  statement {
    sid    = "LambdaUpdateFunctionCode"
    effect = "Allow"
    actions = [
      "lambda:UpdateFunctionCode",
      "lambda:GetFunction",
    ]
    resources = [
      "arn:aws:lambda:eu-central-1:${data.aws_caller_identity.current.account_id}:function:qgi-*",
    ]
  }
}

resource "aws_iam_role_policy" "qgi_lambda_deploy" {
  name   = "lambda-update-function-code"
  role   = aws_iam_role.qgi_lambda_deploy.id
  policy = data.aws_iam_policy_document.qgi_lambda_deploy.json
}

# ---------------------------------------------------------------------------
# qgi — Key rotation role
# Used by the key rotation workflow to refresh terraform-deployer keys
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "key_rotator_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "${local.oidc_provider_url}:sub"
      values   = ["repo:AminAlAit/qgi:*"]
    }
  }
}

resource "aws_iam_role" "key_rotator" {
  name               = "github-actions-key-rotator"
  assume_role_policy = data.aws_iam_policy_document.key_rotator_assume.json
  description        = "OIDC role for AminAlAit/qgi - rotates terraform-deployer IAM keys"
}

data "aws_iam_policy_document" "key_rotator" {
  statement {
    sid    = "RotateDeployerKeys"
    effect = "Allow"
    actions = [
      "iam:CreateAccessKey",
      "iam:DeleteAccessKey",
      "iam:ListAccessKeys",
    ]
    resources = [
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:user/terraform-deployer",
    ]
  }
}

resource "aws_iam_role_policy" "key_rotator" {
  name   = "key-rotation-policy"
  role   = aws_iam_role.key_rotator.id
  policy = data.aws_iam_policy_document.key_rotator.json
}

