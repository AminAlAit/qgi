variable "environment" {
  type        = string
  description = "Deployment environment (staging | qa | prod)."
}

variable "aws_account_id" {
  type        = string
  description = "Target AWS account id (used to scope CloudWatch Logs ARNs)."
}

variable "region" {
  type        = string
  description = "AWS region."
}

variable "data_lake_bucket_name" {
  type        = string
  description = "Name of the data-lake S3 bucket the poller reads/writes (dashboard/ prefix)."
}

variable "data_lake_bucket_arn" {
  type        = string
  description = "ARN of the data-lake S3 bucket (used to scope the IAM object policy)."
}

variable "cost_alerts_topic_arn" {
  type        = string
  default     = ""
  description = "SNS topic ARN for the cost guard to page. Empty => budget created without a subscriber."
}

variable "schedule_state" {
  type        = string
  default     = "ENABLED"
  description = <<-EOT
    EventBridge Scheduler state. ENABLED is the approved end state for the
    live-pulse poller (founder ratified the Scheduler exception 2026-06-11:
    the org-wide DISABLED convention guards expensive pipeline fan-outs; this
    is a single bounded free Lambda, a different risk class). Set to DISABLED
    in tfvars to apply the infra first and turn the clock on in a later apply.
  EOT
  validation {
    condition     = contains(["ENABLED", "DISABLED"], var.schedule_state)
    error_message = "schedule_state must be ENABLED or DISABLED."
  }
}

variable "schedule_expression" {
  type        = string
  default     = "rate(1 hour)"
  description = "EventBridge Scheduler expression. Hourly by design (two-clocks model)."
}

variable "log_retention_days" {
  type        = number
  default     = 14
  description = "CloudWatch Logs retention for the poller."
}

variable "memory_size" {
  type        = number
  default     = 1024
  description = <<-EOT
    Lambda memory (MB). Files are streamed one at a time so memory is not the
    bottleneck; 1024 (vs 512) buys proportionally more vCPU, which cuts the
    cold-cache fetch/parse time. Still firmly in the free tier at hourly cadence.
  EOT
}

variable "timeout" {
  type        = number
  default     = 600
  description = <<-EOT
    Lambda timeout (s). Steady-state runs finish in seconds; 600 gives ample
    headroom for a COLD cache (up to MAX_FETCH sequential GKG fetches). Timeout
    is free unless used, so the headroom costs nothing.
  EOT
}

variable "tags" {
  type        = map(string)
  description = "Resource tags."
}
