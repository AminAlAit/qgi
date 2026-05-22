output "user_pool_id" {
  value       = aws_cognito_user_pool.main.id
  description = "Cognito User Pool ID. Set as COGNITO_USER_POOL_ID in qgi-frontend .env.local and Vercel."
}

output "user_pool_arn" {
  value       = aws_cognito_user_pool.main.arn
  description = "Cognito User Pool ARN (for IAM policy references)."
}

output "app_client_id" {
  value       = aws_cognito_user_pool_client.frontend.id
  description = "App client ID. Set as COGNITO_CLIENT_ID in qgi-frontend .env.local and Vercel."
}

output "issuer_url" {
  value       = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.main.id}"
  description = "OIDC issuer URL for NextAuth JWT verification. Set as COGNITO_ISSUER."
}

# The app client has a secret (generate_secret = true). Following the repo's
# secret convention (see modules/iam + vercel-oidc.tf: secrets are not emitted
# as plaintext outputs), read it POST-APPLY and paste it into env:
#
#   aws cognito-idp describe-user-pool-client \
#     --user-pool-id  <user_pool_id> \
#     --client-id     <app_client_id> \
#     --region        eu-central-1 \
#     --query 'UserPoolClient.ClientSecret' --output text
#
# -> set as COGNITO_CLIENT_SECRET in qgi-frontend .env.local and Vercel.
