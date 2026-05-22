variable "environment" {
  type = string
}

variable "aws_account_id" {
  type = string
}

variable "management_account_id" {
  type = string
}

variable "region" {
  type    = string
  default = "eu-central-1"
}

variable "data_lake_bucket_name" {
  type = string
}

variable "glue_database_name" {
  type = string
}

variable "athena_workgroup_name" {
  type = string
}

variable "sns_topic_arn" {
  type = string
}

variable "lambda_execution_role_arn" {
  type = string
}

variable "stepfunctions_role_arn" {
  type = string
}

variable "eventbridge_scheduler_role_arn" {
  type = string
}

# Cascade/SCDI-exclusive — default "" so QA env can omit when enable_cascade=false.
variable "batch_job_queue_arn" {
  type        = string
  default     = ""
  description = "Batch job queue ARN for ops-batch-checker (Phase B SCDI queue). Empty string when enable_cascade = false."
}

variable "batch_job_definition_arn" {
  type        = string
  default     = ""
  description = "Batch job definition ARN for the scdi-finder job. Empty string when enable_cascade = false."
}

# SQS queue URLs and ARNs
variable "queue_a_main_url" { type = string }
variable "queue_a_main_arn" { type = string }
variable "queue_a_dlq_url" { type = string }
# Cascade/SCDI-exclusive — default "" so QA env can omit when enable_cascade=false.
variable "queue_b_main_url" {
  type    = string
  default = ""
}
variable "queue_b_main_arn" {
  type    = string
  default = ""
}
variable "queue_b_dlq_url" {
  type    = string
  default = ""
}
# Cascade/SCDI-exclusive — default "" so QA env can omit when enable_cascade=false.
variable "queue_c_main_url" {
  type    = string
  default = ""
}
variable "queue_c_main_arn" {
  type    = string
  default = ""
}
variable "queue_c_dlq_url" {
  type    = string
  default = ""
}
variable "queue_c_dlq_arn" {
  type    = string
  default = ""
}

variable "completion_table_name" {
  type        = string
  description = "Name of qgi-completion-counters DynamoDB table"
}

# #148: indicator values DDB for fast frontend reads
variable "indicator_values_table_name" {
  type        = string
  description = "Name of the qgi-indicator-values DynamoDB table (#148). Read by lib/indicator-values.ts via BatchGetItem; written by pipeline-a-completer."
}

variable "dispatch_limit" {
  type        = number
  default     = 0
  description = "Cap the number of indicators dispatched in Phase 1. 0 = unlimited (production). Set to 2 for E2E tests."
}

variable "batch_invoke_mode" {
  type        = string
  default     = "invoke"
  description = "Mode passed to b-orchestrator: 'invoke' submits all jobs; 'invoke_5' caps at 5 (for staging tests)."
}

# #FAR-1: Phase 1 Fargate Spot dispatch
variable "fetcher_job_queue_arn" {
  type        = string
  description = "Batch job queue ARN for Fargate Spot indicator fetcher tasks"
}

variable "fetcher_job_definition_arn" {
  type        = string
  description = "Batch JobDef ARN for the WB Fargate Spot indicator fetcher. This is the DEFAULT JobDef the dispatcher uses when an indicator's provider is not in batch_job_definition_map."
}

# #241 Phase B: per-provider Batch JobDef map. The dispatcher reads this
# (JSON-encoded in its env var) and routes each indicator submission to
# the provider-specific JobDef. Unknown providers fall back to
# fetcher_job_definition_arn above. Map starts empty (legacy behaviour
# preserved) and is populated per-env via terraform.tfvars when a new
# provider's JobDef is ready.
variable "batch_job_definition_map" {
  type        = map(string)
  description = "Map of provider (e.g. 'WB', 'FAOSTAT') -> Batch JobDef ARN. Used by dispatcher for per-provider routing (#240 Phase A / #241 Phase B)."
  default     = {}
}

variable "pipeline_a_counter_table_name" {
  type        = string
  description = "Name of qgi-pipeline-a-counter DynamoDB table (#FAR-1)"
}

variable "indicator_table_name" {
  type        = string
  default     = "qgi-indicator-updates"
  description = "Name of qgi-indicator-updates tracker DDB table"
}

variable "phase1_deadman_seconds" {
  type        = number
  default     = 5400
  description = "Hard cap (seconds) for Phase 1 fan-out before deadman trips. Default 90 min."
}

variable "phase1_jitter_min_s" {
  type        = number
  default     = 60
  description = "Minimum random sleep (seconds) per fetcher task before WB API call"
}

variable "phase1_jitter_max_s" {
  type        = number
  default     = 300
  description = "Maximum random sleep (seconds) per fetcher task before WB API call"
}

variable "tags" {
  type    = map(string)
  default = {}
}

# ---------------------------------------------------------------------------
# #494 step 6: V-Dem annual-refresh pipeline inputs
# ---------------------------------------------------------------------------

variable "vdem_batch_job_definition_arn" {
  type        = string
  description = "ARN of the qgi-vdem-ingest Batch JobDefinition (#494). Defined in modules/batch/vdem.tf and threaded through the staging/qa/prod environments via module.batch.qgi_vdem_ingest_job_definition_arn output."
}

# Note: `fetcher_job_queue_arn` is declared earlier in this file (line ~90,
# from #FAR-1). #494 V-Dem reuses that same shared queue — no separate
# variable needed.

variable "ops_email_address" {
  type        = string
  default     = "qgintelligence@gmail.com"
  description = "SNS subscription email for V-Dem ingest pipeline notifications. Founder direction (2026-04-27): qgintelligence@gmail.com is the ops inbox; not aminalait.de@gmail.com (personal)."
}

# ---------------------------------------------------------------------------
# enable_cascade: gates all Cascade/SCDI/ML1 Lambdas, event source mappings,
# and the Main cascade Step Function.
#   true  (default) = full staging behaviour — ZERO plan diff on staging.
#   false           = Cascade/SCDI pipeline resources not created (QA env).
# ---------------------------------------------------------------------------
variable "enable_cascade" {
  type        = bool
  default     = true
  description = "When false, all Cascade/SCDI/ML1 Lambdas, SQS ESMs, and the Main cascade SFN are skipped. Default true preserves existing staging behaviour."
}

