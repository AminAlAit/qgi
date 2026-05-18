variable "environment" {
  type = string
}

variable "aws_account_id" {
  type = string
}

variable "region" {
  type    = string
  default = "eu-central-1"
}

variable "data_lake_bucket_name" {
  type        = string
  description = "Name of the qgi-data-lake S3 bucket"
}

variable "data_lake_bucket_arn" {
  type        = string
  description = "ARN of the qgi-data-lake S3 bucket"
}

variable "ecs_instance_profile_arn" {
  type        = string
  description = "ECS instance profile ARN reused from the iam module (same as scdi_spot compute env)"
}

variable "fargate_execution_role_arn" {
  type        = string
  description = "Execution role ARN — used by ECS agent on EC2 instances to pull images + ship logs. Reused from iam module."
}

variable "stepfunctions_role_arn" {
  type        = string
  description = "IAM role ARN for Step Functions execution. Reused from iam module."
}

variable "lambda_execution_role_arn" {
  type        = string
  description = "Lambda execution role ARN for the post-pass Lambda. Reused from iam module."
}

# ---------------------------------------------------------------------------
# S3 prefix configuration — all relative to data_lake_bucket_name.
# Trailing-slash convention matches how other modules use S3 prefixes.
# ---------------------------------------------------------------------------

variable "parquet_data_prefix" {
  type        = string
  default     = "pipeline-A-indicator-extractor/output/parquet-completed/"
  description = "S3 prefix (no bucket) for the completed indicator parquet panels synced into each Batch job."
}

variable "ml_results_prefix" {
  type        = string
  default     = "ml-results/"
  description = "S3 prefix under which per-recipe result JSONs are written."
}

variable "ml_checkpoints_prefix" {
  type        = string
  default     = "ml-checkpoints/"
  description = "S3 prefix for per-recipe checkpoint blobs. Namespaced per-recipe: {prefix}{recipe_id}/."
}

variable "recipe_manifest_s3_key" {
  type        = string
  default     = "ml-results/recipe-manifest.json"
  description = "S3 key for the recipe-manifest.json (runnable/thin/skip tiers) read by the SFN pre-filter Pass state."
}

# IMAGE PERMA-FIX: pin the walk + bake JobDefs to an immutable DIGEST resolved from
# this tag at apply time, never the mutable ':latest' tag. The 2026-06-01 incident —
# run-2 walked on a stale ':latest' that lacked the #136/#137/#141 walk/score code —
# is impossible once the JobDef references qgi-recipe-fleet@sha256:<digest>. Set this to
# a SPECIFIC build tag per deploy (NOT 'latest'); a TF apply then bakes that exact
# digest into both JobDefs. Update = push a new tag, bump this, re-apply.
variable "recipe_fleet_image_tag" {
  type        = string
  default     = ""
  description = "ECR tag of qgi-recipe-fleet to pin (resolved to an immutable digest). Set per deploy to a specific build tag, never 'latest', so every job runs a provable image."
  # QA #40 BLOCKER: a 'latest' (or empty) default would silently re-introduce the
  # stale-image incident on any env that forgets to override it. Force every env to pin.
  validation {
    condition     = var.recipe_fleet_image_tag != "" && var.recipe_fleet_image_tag != "latest"
    error_message = "recipe_fleet_image_tag must be an explicit immutable build tag (e.g. bake-panels-527004d), never '' or 'latest' — that defeats the digest perma-fix."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}
