# ---------------------------------------------------------------------------
# Vercel -> AWS OIDC federation (live-pulse track, founder go 2026-06-12)
#
# Lets the production qgi-frontend (Vercel) read the live-pulse output from S3
# WITHOUT any stored AWS key: Vercel presents a short-lived OIDC token, AWS
# hands back ~1h credentials scoped to a read-only role. All-private (the S3
# object is never public) and $0 (free-tier reads). Matches the founder's
# existing OIDC pattern (GitHub Actions -> AWS).
#
# Vercel team slug + project (from the deployment URL
# vercel.com/aminalaits-projects/qgi-frontend). FOUNDER: confirm these against
# the Vercel project's OIDC settings page before relying on it — a wrong slug
# fails the AssumeRoleWithWebIdentity condition silently.
#   issuer  = https://oidc.vercel.com/aminalaits-projects   (Team issuer mode)
#   aud     = https://vercel.com/aminalaits-projects
#   sub     = owner:aminalaits-projects:project:qgi-frontend:environment:{production|preview}
# Docs: https://vercel.com/docs/oidc/aws
# ---------------------------------------------------------------------------

locals {
  vercel_oidc_issuer = "https://oidc.vercel.com/aminalaits-projects"
  vercel_oidc_aud    = "https://vercel.com/aminalaits-projects"
  vercel_oidc_host   = "oidc.vercel.com/aminalaits-projects" # condition-key prefix
}

# AWS no longer validates the thumbprint for issuers fronted by a public CA
# (oidc.vercel.com is), so the [0] leaf fingerprint below is accepted as a
# formality — it is not part of the token-trust path. The resource still
# requires the field, so fetch it from the live cert. One OIDC provider is
# allowed per issuer URL per account; no other module here touches this issuer.
data "tls_certificate" "vercel_oidc" {
  url = local.vercel_oidc_issuer
}

resource "aws_iam_openid_connect_provider" "vercel" {
  url             = local.vercel_oidc_issuer
  client_id_list  = [local.vercel_oidc_aud]
  thumbprint_list = [data.tls_certificate.vercel_oidc.certificates[0].sha1_fingerprint]
  tags            = local.tags
}

# Read-only role the frontend assumes via the Vercel OIDC token. Scoped to the
# two dashboard JSONs the site reads — nothing else in the data lake.
resource "aws_iam_role" "vercel_frontend_reader" {
  name = "qgi-vercel-frontend-reader"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.vercel.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      # Both aud AND sub required (AND semantics). StringEquals (not StringLike)
      # with exact subjects — no wildcards, so a future edit can't silently
      # broaden scope (e.g. environment:* would admit development).
      Condition = {
        StringEquals = {
          "${local.vercel_oidc_host}:aud" = local.vercel_oidc_aud
          # Production + preview deploys of THIS project only.
          "${local.vercel_oidc_host}:sub" = [
            "owner:aminalaits-projects:project:qgi-frontend:environment:production",
            "owner:aminalaits-projects:project:qgi-frontend:environment:preview",
          ]
        }
      }
    }]
  })
  tags = local.tags
}

resource "aws_iam_role_policy" "vercel_frontend_reader" {
  role = aws_iam_role.vercel_frontend_reader.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "ReadDashboardJson"
      Effect = "Allow"
      Action = ["s3:GetObject"]
      # The frontend reads only existing objects, so GetObject is enough (a
      # miss returns 403 -> the loader's absent fallback, which is fine). No
      # ListBucket needed -> the role cannot enumerate the bucket.
      Resource = [
        "${module.storage.bucket_arn}/dashboard/hf-pulse-live.json",
        # Live Pulse terminal (2026-06-14): intraday charts + the headline feed
        # are rebuilt frontend-side from these, read at runtime via this role.
        "${module.storage.bucket_arn}/dashboard/hf-pulse-buckets.json",
        "${module.storage.bucket_arn}/dashboard/hf-pulse-baseline.json",
        "${module.storage.bucket_arn}/dashboard/hf-pulse-articles.json",
        "${module.storage.bucket_arn}/dashboard/country-risks.json",
      ]
    }]
  })
}

# ---------------------------------------------------------------------------
# Vercel BUILD-time reader (S3 build-fetch slim-down, founder go 2026-06-15)
#
# Separate from the runtime reader (security review, "Daniel"): the build needs
# to pull the heavy te-fleet-run-* fleet vintages from S3 during `next build`
# (qgi-frontend scripts/fetch-build-data.mjs), but the RUNTIME functions must
# NOT be able to read the whole fleet — they stay pinned to the 5 dashboard/*
# keys above. So the build assumes THIS role (via AWS_BUILD_ROLE_ARN in Vercel),
# not the runtime one. Same Vercel OIDC provider + prod/preview sub.
#
# GetObject ONLY (no s3:ListBucket): the build reads exact keys from the
# committed data/build-manifest.json — it never enumerates the bucket — so it
# needs no list permission and cannot discover other objects. Scope mirrors the
# GitHub Actions fleet-sync role: frontend-data/te-fleet-run-*.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "vercel_build_reader" {
  name = "qgi-vercel-build-reader"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.vercel.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      # Identical AND-semantics condition as the runtime reader: exact aud +
      # exact prod/preview subs, StringEquals (no wildcards). Preview is a
      # deliberate inclusion — fetch-build-data.mjs runs during preview deploys.
      Condition = {
        StringEquals = {
          "${local.vercel_oidc_host}:aud" = local.vercel_oidc_aud
          "${local.vercel_oidc_host}:sub" = [
            "owner:aminalaits-projects:project:qgi-frontend:environment:production",
            "owner:aminalaits-projects:project:qgi-frontend:environment:preview",
          ]
        }
      }
    }]
  })
  tags = local.tags
}

resource "aws_iam_role_policy" "vercel_build_reader" {
  role = aws_iam_role.vercel_build_reader.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "ReadFleetVintages"
      Effect = "Allow"
      Action = ["s3:GetObject"]
      # Exact-key reads from the committed manifest -> no ListBucket, the build
      # cannot enumerate the bucket. Trailing /* keeps the grant to objects
      # INSIDE a vintage dir (a hypothetical flat frontend-data/te-fleet-run-*.json
      # never matches); covers the live vintage + any future te-fleet-run-N the
      # manifest is later bumped to.
      Resource = ["${module.storage.bucket_arn}/frontend-data/te-fleet-run-*/*"]
    }]
  })
}

output "vercel_frontend_reader_role_arn" {
  value       = aws_iam_role.vercel_frontend_reader.arn
  description = "Set this as AWS_ROLE_ARN in the Vercel qgi-frontend project (production env)."
}

output "vercel_build_reader_role_arn" {
  value       = aws_iam_role.vercel_build_reader.arn
  description = "Set this as AWS_BUILD_ROLE_ARN in the Vercel qgi-frontend project (production + preview)."
}
