variable "region" {
  type        = string
  default     = "eu-central-1"
  description = "Default AWS region"
}

variable "management_account_id" {
  type        = string
  default     = "783811616921"
  description = "Management Account ID (Org root, OIDC, state backend)"
}

variable "staging_account_id" {
  type        = string
  default     = "771606957899"
  description = "Staging Account ID"
}

variable "qa_account_id" {
  type        = string
  default     = "928648269104"
  description = "QA Account ID"
}

variable "prod_account_id" {
  type        = string
  default     = "297797204453"
  description = "Production Account ID"
}

variable "member_account_ids" {
  type        = list(string)
  default     = ["771606957899", "928648269104", "297797204453"]
  description = "Active member account IDs subject to Service Control Policies"
}
