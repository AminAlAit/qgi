# ---------------------------------------------------------------------------
# QGI Cognito — user pool + app client backing NextAuth (Auth.js v5) on
# qgi-frontend.
#
# Architecture = "Option A" (auth-implementation-plan-2026-07-10.md):
#   - Email/password sign-in/up runs through the frontend's SERVER-SIDE
#     NextAuth Credentials provider, which calls Cognito directly
#     (InitiateAuth USER_PASSWORD_AUTH over TLS + SignUp/ConfirmSignUp/
#     ForgotPassword). So this pool needs NO hosted-UI domain and NO OAuth
#     flows — hence no aws_cognito_user_pool_domain here.
#   - Google sign-in is handled by NextAuth's OWN Google provider (not
#     Cognito). Federating Google INTO this pool is a later, optional step
#     ("Option B") that would add a domain + a google IdP + OAuth flows.
#
# Founder-approved 2026-07-10. Replaces the current SKIP_AUTH=true posture.
# Cost: ~$0 at dev scale. New Cognito pools default to the Essentials tier
# (10k MAU/account free, then $0.015/MAU); set user_pool_tier="LITE" for the
# legacy tiered pricing if desired. Verification/reset emails use the Cognito
# default sender (~50/day) until SES is wired for prod volume.
# ---------------------------------------------------------------------------

resource "aws_cognito_user_pool" "main" {
  # Repo convention: qgi-<thing>, no env in the name (accounts are isolated
  # per environment, so the staging and prod pools have distinct IDs anyway).
  name = "qgi-user-pool"

  # This pool holds live user credentials — the highest-value state in this
  # change. Guard it against accidental deletion (mirrors the deletion guard on
  # the qgi-user-settings table).
  deletion_protection = "ACTIVE"

  # Users sign in with their email address (no separate username).
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length                   = var.password_minimum_length
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = false
    temporary_password_validity_days = 7
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # Start with MFA off. Can move to OPTIONAL (or required for the pro group)
  # once payments/tiers land — see Phase 3 of the auth plan.
  mfa_configuration = "OFF"

  # Cognito's built-in low-volume email sender. For prod volume, switch to
  # email_sending_account = "DEVELOPER" with an SES source_arn (Phase 2).
  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }

  # email is a standard attribute auto-configured by username_attributes, so
  # no explicit `schema` block is declared (declaring standard attrs risks a
  # constraints-mismatch apply error).

  tags = var.tags
}

resource "aws_cognito_user_pool_client" "frontend" {
  name         = "qgi-frontend-client"
  user_pool_id = aws_cognito_user_pool.main.id

  # Confidential client: the secret stays server-side in the NextAuth
  # Credentials provider, which computes SECRET_HASH for every Cognito call.
  generate_secret = true

  # Direct server-side auth (email/password over TLS) + refresh. No SRP and
  # no hosted-UI OAuth flows (Google is handled by NextAuth, not Cognito).
  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  # Don't reveal whether an email is already registered.
  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 30
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  supported_identity_providers = ["COGNITO"]
}

# Plan/tier group — matches the existing requireGroup("pro") gate in
# qgi-frontend/lib/auth.ts. Stays empty until payments (Phase 3).
resource "aws_cognito_user_group" "pro" {
  name         = "pro"
  user_pool_id = aws_cognito_user_pool.main.id
  description  = "Paid tier. Grants access to the pro-gated API data routes."
}
