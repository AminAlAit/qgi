# monitoring module variables

variable "environment" {
  description = "Environment name (staging, qa, prod)."
  type        = string
}

variable "sns_topic_arn" {
  description = "SNS topic ARN to publish paging alarms to (HIGH_COUNTRY_COUNT and MEDIAN_SALIENCE_SCORE). COUNTRY_RISKS_BYTES alarms do NOT page."
  type        = string
}

variable "tags" {
  description = "Tags applied to every monitoring resource."
  type        = map(string)
  default     = {}
}

# #412 — SNS alarm formatter (qgi-sns-alarm-formatter Lambda)

variable "alarm_formatter_sender_email" {
  description = "SES-verified sender identity for formatted alarm emails. Must be verified in SES before the Lambda can send."
  type        = string
  default     = "alerts@qgintelligence.com"
}

variable "alarm_formatter_recipient_email" {
  description = "Recipient for formatted alarm emails. In SES sandbox mode, must also be verified."
  type        = string
  default     = "qgintelligence@gmail.com"
}

variable "lambda_execution_role_arn" {
  description = "IAM role ARN for Lambda execution (passed from pipeline module). If empty, the monitoring module creates its own role scoped to SES + Logs only."
  type        = string
  default     = ""
}

# ---------------------------------------------------------------------------
# enable_cascade: gates the CloudWatch alarms tied to Cascade Lambdas
# (qgi-v191-* scoring-drift alarms and qgi-caught-exception-finalize-* alarms).
# Alarms for Phase A / live-pulse / TE are NOT gated.
#   true  (default) = full staging behaviour — ZERO plan diff on staging.
#   false           = Cascade/SCDI monitoring resources not created (QA env).
# ---------------------------------------------------------------------------
variable "enable_cascade" {
  type        = bool
  default     = true
  description = "When false, V1.9.1 scoring-drift alarms and caught-exception-finalize alarms are skipped. Default true preserves existing staging behaviour."
}
