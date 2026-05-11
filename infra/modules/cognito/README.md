# `modules/cognito` — QGI auth user pool

Cognito User Pool + confidential app client backing NextAuth (Auth.js v5) on
`qgi-frontend`. This is the infrastructure half of the **full sign-in/sign-up**
work that replaces the `SKIP_AUTH=true` dev posture.

Design = **"Option A"** from
[`qgi-frontend/docs/auth-implementation-plan-2026-07-10.md`](../../../qgi-frontend/docs/auth-implementation-plan-2026-07-10.md).
Founder-approved 2026-07-10; module written + strict-reviewed + applied to
**staging** 2026-07-10.

---

## Context

The frontend needs a real identity provider for native **email/password**
accounts. Google sign-in is handled entirely by NextAuth's own Google provider
(identity lives in the NextAuth JWT) and does **not** touch Cognito. So this
pool only has to serve server-side email/password auth:

- `InitiateAuth` (`USER_PASSWORD_AUTH`, over TLS, with `SECRET_HASH`)
- `SignUp` / `ConfirmSignUp` / `ResendConfirmationCode`
- `ForgotPassword` / `ConfirmForgotPassword`

No hosted UI, no OAuth flows, no user-pool domain — the frontend's server-side
Credentials provider calls the Cognito API directly.

## Proposal (what this module creates)

| Resource | Name | Key config |
|---|---|---|
| `aws_cognito_user_pool.main` | `qgi-user-pool` | sign-in by **email**; `auto_verified_attributes=["email"]`; password min **10** (upper/lower/number, no symbol); recovery = verified email; **MFA off**; email = `COGNITO_DEFAULT` sender |
| `aws_cognito_user_pool_client.frontend` | `qgi-frontend-client` | **confidential** (`generate_secret=true`); flows = `ALLOW_USER_PASSWORD_AUTH` + `ALLOW_REFRESH_TOKEN_AUTH`; `prevent_user_existence_errors=ENABLED`; token revocation on; access/id **60 min**, refresh **30 days**; IdPs = `COGNITO` only |
| `aws_cognito_user_group.pro` | `pro` | plan-gating group; matches `requireGroup("pro")` in `qgi-frontend/lib/auth.ts`. Empty until payments (Phase 3). |

No hosted-UI domain and no `schema` block are declared (email is auto-configured
by `username_attributes`; declaring standard attributes risks a
constraints-mismatch apply error).

## Affected resources — applied state (staging · account `771606957899` · `eu-central-1`)

| Output | Value |
|---|---|
| `cognito_user_pool_id` (`COGNITO_USER_POOL_ID`) | `eu-central-1_myM4cn5Lz` |
| `cognito_app_client_id` (`COGNITO_CLIENT_ID`) | `n0ecnlrmll79egf1jed24u9d6` |
| `cognito_issuer_url` (`COGNITO_ISSUER`) | `https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_myM4cn5Lz` |
| Client secret (`COGNITO_CLIENT_SECRET`) | **not** a plaintext TF output — read post-apply (below) |

Applied additively via `-target=module.cognito` (**3 add / 0 change / 0
destroy**). Strict QA plan-review returned GREEN before apply.

## Inputs / Outputs

**Inputs:** `environment`, `aws_account_id`, `region` (default `eu-central-1` —
must match the frontend's `AWS_REGION`, since the issuer URL derives from it),
`password_minimum_length` (default `10`), `tags`.

**Outputs:** `user_pool_id`, `user_pool_arn`, `app_client_id`, `issuer_url`.
The client secret is intentionally not emitted (repo secret convention — cf.
`modules/iam`, `vercel-oidc.tf`).

## Post-apply — wire the frontend

Read the client secret and set the five env vars in
`qgi-frontend/.env.local` (local) and later the Vercel project env (prod):

```bash
aws cognito-idp describe-user-pool-client \
  --user-pool-id eu-central-1_myM4cn5Lz \
  --client-id    n0ecnlrmll79egf1jed24u9d6 \
  --region       eu-central-1 \
  --query 'UserPoolClient.ClientSecret' --output text
```

```
COGNITO_USER_POOL_ID=eu-central-1_myM4cn5Lz
COGNITO_CLIENT_ID=n0ecnlrmll79egf1jed24u9d6
COGNITO_CLIENT_SECRET=<from the command above>
COGNITO_ISSUER=https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_myM4cn5Lz
AWS_REGION=eu-central-1
```

(Local testing also needs `AUTH_SECRET`, `AUTH_URL`, `GOOGLE_CLIENT_ID`,
`GOOGLE_CLIENT_SECRET`, and `SKIP_AUTH=false`.)

## Notes

- **Cost:** new pools default to the **Essentials** tier — **10k MAU/account
  free**, then ~$0.015/MAU. A cheaper feature-reduced `user_pool_tier = "LITE"`
  exists if ever needed. Effectively **$0** at dev/early scale.
- **Email deliverability:** the Cognito default sender is low-volume (~50/day)
  and fine for testing. Prod volume needs
  `email_sending_account = "DEVELOPER"` + an SES `source_arn` (Phase 2).
- **MFA** is off; can move to `OPTIONAL` (or required for `pro`) with payments.

### Follow-ups (not in this change)
1. **Prod pool** — apply the same module in `environments/prod` (`297797204453`);
   distinct pool ID; add Vercel prod env + prod Google redirect URIs.
2. **SES** for verification/reset email at volume before prod.
3. Optional **"Option B"**: federate Google *into* the pool (adds a domain +
   Google IdP + OAuth flows) if a single identity store is later wanted.

### Verification status (staging + localhost, 2026-07-11)
- `InitiateAuth USER_PASSWORD_AUTH` from the app server → tokens (1 h expiry). ✅
- Full frontend auth suite **10/10** (gate blocks signed-out; email/password
  sign-in → validated session → `/dashboard`; wrong-password error; sign-out
  clears session + re-blocks; Google OAuth reaches consent; sign-up duplicate +
  validation). ✅
- 34 unit tests on the Cognito wrapper + server actions. ✅
