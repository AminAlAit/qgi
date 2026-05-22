variable "region" {
  type        = string
  default     = "eu-central-1"
  description = "Default AWS region"
}

variable "management_account_id" {
  type        = string
  default     = "111111111111"
  description = "Management Account ID (Org root, OIDC, state backend)"
}

variable "staging_account_id" {
  type        = string
  default     = "222222222222"
  description = "Staging Account ID"
}

variable "qa_account_id" {
  type        = string
  default     = "333333333333"
  description = "QA Account ID"
}

variable "prod_account_id" {
  type        = string
  default     = "444444444444"
  description = "Production Account ID"
}

variable "member_account_ids" {
  type        = list(string)
  default     = ["222222222222", "333333333333", "444444444444"]
  description = "Active member account IDs subject to Service Control Policies"
}
