variable "environment" {
  type    = string
  default = "prod"
}

variable "aws_account_id" {
  type        = string
  description = "qgi-prod account ID"
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

# #96: toggle for cross-account role assumption. See staging/variables.tf
# for the full rationale. Default false for direct-auth (prod SSO, CI OIDC
# roles in prod). Set true when running from mgmt IAM user.
variable "use_cross_account_assume_role" {
  type        = bool
  default     = false
  description = "If true, the AWS provider assumes OrganizationAccountAccessRole in var.aws_account_id. Default false for direct-auth flows. See #96."
}
