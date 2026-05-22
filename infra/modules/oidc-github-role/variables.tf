variable "role_name" {
  type        = string
  description = "Name of the IAM role for GitHub Actions OIDC"
}

variable "role_description" {
  type        = string
  default     = "GitHub Actions OIDC IAM role"
  description = "Description of the IAM role"
}

variable "github_repositories" {
  type        = list(string)
  default     = ["repo:AminAlAit/qgi:*"]
  description = "List of repository subjects permitted to assume the role"
}

variable "oidc_provider_arn" {
  type        = string
  default     = ""
  description = "ARN of the existing GitHub Actions OIDC provider. If empty, constructed from current account ID."
}

variable "managed_policy_arns" {
  type        = list(string)
  default     = []
  description = "List of IAM managed policy ARNs to attach to the role"
}

variable "inline_policies" {
  type        = map(string)
  default     = {}
  description = "Map of inline policy name to JSON policy document"
}

variable "max_session_duration" {
  type        = number
  default     = 3600
  description = "Maximum session duration in seconds (1 to 12 hours)"
}

variable "tags" {
  type        = map(string)
  default     = {}
  description = "Tags to attach to the role"
}
