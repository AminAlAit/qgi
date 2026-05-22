terraform {
  backend "s3" {
    bucket         = "qgi-infra-state-771606957899"
    key            = "staging/terraform.tfstate"
    region         = "eu-central-1"
    dynamodb_table = "qgi-infra-state-lock"
    encrypt        = true

    # #96: backend blocks CANNOT use variables, so assume_role is static.
    # The default works from the mgmt IAM user via OrganizationAccountAccessRole.
    # If you're already authenticated as staging directly (SSO, CI OIDC role
    # in staging, etc.), this block will fail with "not authorized to perform
    # sts:AssumeRole on resource" and you need ONE of:
    #
    #   (a) Override at init time (recommended):
    #       terraform init -reconfigure \
    #         -backend-config='assume_role={}'
    #
    #   (b) Comment out this assume_role block locally for the apply, then
    #       revert before committing (the legacy workaround).
    #
    # The provider-side assume_role is variable-driven (see providers.tf +
    # var.use_cross_account_assume_role) so it doesn't have this limitation.
    # assume_role temporarily disabled for SSO-direct apply
    # assume_role = {
    #   role_arn = "arn:aws:iam::771606957899:role/OrganizationAccountAccessRole"
    # }
  }
}
