variable "environment" {
  type    = string
  default = "staging"
}

variable "aws_account_id" {
  type        = string
  description = "qgi-staging account ID"
}

variable "management_account_id" {
  type        = string
  description = "Management account ID — hosts ECR registry"
  default     = "783811616921"
}

variable "region" {
  type    = string
  default = "eu-central-1"
}

# #96: toggle for cross-account role assumption in the AWS provider.
#
# Default (false) = direct caller credentials, suitable for:
#   - Staging SSO creds (portal → Copy credentials → paste into shell)
#   - CI OIDC roles that are already in the staging account
#   - Any shell already assumed into OrganizationAccountAccessRole
#
# Set to true when running from the management account (e.g. Amin's
# Codespace as the terraform-deployer IAM user). Terraform
# will then assume OrganizationAccountAccessRole in the target account.
#
# Usage:
#   terraform apply                                       # direct auth (default)
#   terraform apply -var='use_cross_account_assume_role=true'  # from mgmt
#
# Or set via env:
#   export TF_VAR_use_cross_account_assume_role=true
#
# This replaces the old hand-commented workflow (edit providers.tf,
# comment out the assume_role block, run, revert) with a clean flag.
variable "use_cross_account_assume_role" {
  type        = bool
  default     = false
  description = "If true, the AWS provider assumes OrganizationAccountAccessRole in var.aws_account_id. Default false for direct-auth flows. See #96."
}
