variable "environment" {
  type        = string
  description = "Environment name (staging, qa, prod)"
}

variable "aws_account_id" {
  type        = string
  description = "AWS account ID for this environment"
}

variable "region" {
  type    = string
  default = "eu-central-1"
}

variable "management_account_id" {
  type        = string
  description = "Management AWS account ID (for cross-account S3 sync)"
  default     = "783811616921"
}

variable "tags" {
  type    = map(string)
  default = {}
}

# ---------------------------------------------------------------------------
# enable_cascade: gates the entire Cascade/SCDI/ML1 stack.
#   true  (default) = full staging behaviour — ZERO plan diff on staging.
#   false           = Cascade/SCDI resources not created (QA env).
# ---------------------------------------------------------------------------
variable "enable_cascade" {
  type        = bool
  default     = true
  description = "When false, all Cascade/SCDI/ML1 SQS queues and Glue tables are skipped. Default true preserves existing staging behaviour."
}

variable "enable_user_settings" {
  type        = bool
  default     = false
  description = "When true, create the qgi-user-settings DynamoDB table (frontend auth/profile store). Default false so qa/prod don't create it until the frontend ships there; staging sets it true."
}
