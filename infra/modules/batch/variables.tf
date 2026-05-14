variable "environment" {
  type = string
}

variable "aws_account_id" {
  type = string
}

variable "management_account_id" {
  type        = string
  description = "Management account ID — ECR registry lives here"
}

variable "region" {
  type    = string
  default = "eu-central-1"
}

variable "batch_job_role_arn" {
  type = string
}

variable "ecs_instance_profile_arn" {
  type = string
}

variable "data_lake_bucket_name" {
  type = string
}

# #FAR-1: Fargate task IAM roles for the Phase 1 indicator fetcher.
# Fargate tasks need TWO roles:
#  - executionRole: used by Fargate itself to pull the image from ECR
#    and write logs to CloudWatch (the "infra" role)
#  - taskRole: the IAM identity assumed by code running INSIDE the
#    container (the "application" role)
variable "fargate_task_role_arn" {
  type        = string
  description = "Task role ARN — IAM identity assumed by the fetcher script (#FAR-1)"
}

variable "fargate_execution_role_arn" {
  type        = string
  description = "Execution role ARN — Fargate uses this to pull images + write logs (#FAR-1)"
}

variable "tags" {
  type    = map(string)
  default = {}
}

# ---------------------------------------------------------------------------
# enable_cascade: gates the Phase B SCDI compute environment, job queue,
# scdi-finder job definition, and related log groups.
#   true  (default) = full staging behaviour — ZERO plan diff on staging.
#   false           = Cascade/SCDI Batch resources not created (QA env).
# ---------------------------------------------------------------------------
variable "enable_cascade" {
  type        = bool
  default     = true
  description = "When false, the Phase B SCDI Batch CE/queue/jobdef are skipped. Default true preserves existing staging behaviour."
}
