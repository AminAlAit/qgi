variable "environment" {
  type = string
}

variable "aws_account_id" {
  type        = string
  description = "AWS account ID for this environment"
}

variable "management_account_id" {
  type        = string
  description = "Management account ID (hosts ECR)"
}

variable "region" {
  type    = string
  default = "eu-central-1"
}

variable "data_lake_bucket_arn" {
  type = string
}

variable "queue_arns" {
  type        = list(string)
  description = "ARNs of all SQS queues (main + DLQ)"
}

variable "indicator_table_arn" {
  type = string
}

variable "completion_table_arn" {
  type = string
}

# #148: DDB table holding indicator values for fast frontend reads
variable "indicator_values_table_arn" {
  type        = string
  description = "ARN of the qgi-indicator-values DynamoDB table (#148)"
}

# #FAR-1: Phase 1 Fargate Spot dispatch counter
variable "pipeline_a_counter_table_arn" {
  type        = string
  description = "ARN of the qgi-pipeline-a-counter DynamoDB table (#FAR-1)"
}

variable "sns_topic_arn" {
  type = string
}

variable "state_machine_arn" {
  type        = string
  description = "Step Functions state machine ARN for EventBridge scheduler role. Pass empty string during bootstrap."
  default     = ""
}

variable "fetch_state_machine_arn" {
  type        = string
  description = "#175: Fetch SF ARN for EventBridge scheduler role. Pass empty string during bootstrap."
  default     = ""
}

variable "cognito_user_pool_arn" {
  type        = string
  description = "Cognito user pool ARN. Grants the frontend reader cognito-idp:ListUsers for the account-linking check (auth). Empty string omits the grant."
  default     = ""
}

variable "user_settings_table_arn" {
  type        = string
  description = "qgi-user-settings DynamoDB table ARN. Grants the frontend reader read/write for per-user profile settings. Empty string omits the grant."
  default     = ""
}

variable "tags" {
  type    = map(string)
  default = {}
}
