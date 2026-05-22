# ---------------------------------------------------------------------------
# Cognito — user pool + app client for qgi-frontend auth (NextAuth, Option A:
# email/password direct via a server-side Credentials provider + Google via
# NextAuth's own provider). Founder-approved 2026-07-10.
#
# See modules/cognito and qgi-frontend/docs/auth-implementation-plan-2026-07-10.md.
#
# Post-apply (staging first, for local testing): paste the outputs below plus
# the client secret (read with the `aws cognito-idp describe-user-pool-client`
# command in modules/cognito/outputs.tf) into qgi-frontend/.env.local. Same
# values go into the Vercel project env at prod rollout (Phase 2).
# ---------------------------------------------------------------------------
module "cognito" {
  source = "../../modules/cognito"

  environment    = var.environment
  aws_account_id = var.aws_account_id
  region         = var.region

  tags = local.tags
}

output "cognito_user_pool_id" {
  value       = module.cognito.user_pool_id
  description = "COGNITO_USER_POOL_ID for qgi-frontend .env.local / Vercel."
}

output "cognito_app_client_id" {
  value       = module.cognito.app_client_id
  description = "COGNITO_CLIENT_ID for qgi-frontend .env.local / Vercel."
}

output "cognito_issuer_url" {
  value       = module.cognito.issuer_url
  description = "COGNITO_ISSUER for qgi-frontend .env.local / Vercel."
}
