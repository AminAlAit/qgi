#!/bin/bash
# Bootstrap the Terraform state backend for the qgi-staging account.
# Run this ONCE before the first `terraform init` in environments/staging/.
#
# AUTHENTICATION PATHS (auto-detected by check at top of script):
#
# Path 1 — Cross-account assume-role (default, for management-account ops):
#   The aws CLI is authenticated as the management-account deployer
#   (terraform-deployer or equivalent). The script assumes
#   OrganizationAccountAccessRole in the staging account before creating
#   the state backend resources.
#
# Path 2 — Direct staging SSO (for founder-laptop ad-hoc bootstrap):
#   The aws CLI is ALREADY authenticated as a staging-account principal
#   (e.g. AWSReservedSSO_AdministratorAccess via the AWS SSO portal).
#   The assume-role step is skipped because the caller already has the
#   needed permissions in the target account.
#
# The script auto-detects which path applies by checking the current
# `aws sts get-caller-identity` account against the target staging account.
# This avoids the chicken-and-egg problem where
# OrganizationAccountAccessRole may not exist in a new staging account
# (it is provisioned by AWS Organizations only when the account is
# created via Organizations, not via standalone signup).
#
# Prerequisites:
#   - aws CLI authenticated via EITHER path above
#   - AWS_DEFAULT_REGION=eu-central-1 (set in devcontainer or shell)
#
# Usage:
#   bash environments/staging/bootstrap/bootstrap.sh

set -euo pipefail

STAGING_ACCOUNT_ID="771606957899"
REGION="eu-central-1"
BUCKET_NAME="qgi-infra-state-${STAGING_ACCOUNT_ID}"
TABLE_NAME="qgi-infra-state-lock"
ROLE_ARN="arn:aws:iam::${STAGING_ACCOUNT_ID}:role/OrganizationAccountAccessRole"

CURRENT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

if [ "$CURRENT_ACCOUNT" = "$STAGING_ACCOUNT_ID" ]; then
  echo "==> Authenticated directly as staging account ${STAGING_ACCOUNT_ID}; skipping assume-role."
  # Use the existing session as-is. AWS_* env vars (or aws CLI default
  # config) already point at the target account.
else
  echo "==> Current account is ${CURRENT_ACCOUNT}; assuming OrganizationAccountAccessRole in staging ${STAGING_ACCOUNT_ID}..."
  CREDS=$(aws sts assume-role \
    --role-arn "$ROLE_ARN" \
    --role-session-name "qgi-infra-bootstrap" \
    --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' \
    --output text)

  export AWS_ACCESS_KEY_ID=$(echo "$CREDS" | awk '{print $1}')
  export AWS_SECRET_ACCESS_KEY=$(echo "$CREDS" | awk '{print $2}')
  export AWS_SESSION_TOKEN=$(echo "$CREDS" | awk '{print $3}')
fi

echo "==> Creating S3 state bucket: ${BUCKET_NAME}"
if aws s3api head-bucket --bucket "$BUCKET_NAME" --region "$REGION" 2>/dev/null; then
  echo "    (already exists — skipping)"
else
  aws s3api create-bucket \
    --bucket "$BUCKET_NAME" \
    --region "$REGION" \
    --create-bucket-configuration LocationConstraint="$REGION"

  aws s3api put-bucket-versioning \
    --bucket "$BUCKET_NAME" \
    --versioning-configuration Status=Enabled

  aws s3api put-bucket-encryption \
    --bucket "$BUCKET_NAME" \
    --server-side-encryption-configuration '{
      "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
    }'

  aws s3api put-public-access-block \
    --bucket "$BUCKET_NAME" \
    --public-access-block-configuration \
      "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

  echo "    Created ${BUCKET_NAME}"
fi

echo "==> Creating DynamoDB lock table: ${TABLE_NAME}"
if aws dynamodb describe-table --table-name "$TABLE_NAME" --region "$REGION" 2>/dev/null; then
  echo "    (already exists — skipping)"
else
  aws dynamodb create-table \
    --table-name "$TABLE_NAME" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region "$REGION"

  aws dynamodb wait table-exists --table-name "$TABLE_NAME" --region "$REGION"
  echo "    Created ${TABLE_NAME}"
fi

# Only unset the assumed-role creds if we actually assumed a role.
# If the caller was already in the target account (Path 2 above), their
# original creds (e.g. SSO session) are still in env and must NOT be
# blanked — doing so would force the operator to re-authenticate.
if [ "$CURRENT_ACCOUNT" != "$STAGING_ACCOUNT_ID" ]; then
  unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
fi

echo ""
echo "Bootstrap complete. You can now run:"
echo "  cd environments/staging"
echo "  terraform init"
echo "  terraform plan"
