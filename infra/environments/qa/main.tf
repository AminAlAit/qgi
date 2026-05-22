locals {
  tags = {
    Project     = "qgi"
    Environment = var.environment
    ManagedBy   = "terraform"
    Owner       = "amin.al-ait"
  }
}

# ===========================================================================
# QA environment — ML2/TE (Trajectory Engine) ONLY.
#
# QA is a production-like mirror of staging, but the Cascade/SCDI/ML1 path is
# NOT carried over (QGI runs on ML2/TE only). Every cascade-aware module is
# instantiated with `enable_cascade = false`, so the Phase B SCDI compute env,
# the Phase B/C Lambdas, the Main cascade SFN, the B/C SQS queues, the cascade
# Glue tables, and the cascade alarms are never created here.
#
# Differences vs environments/staging/main.tf:
#   - enable_cascade = false on storage / batch / pipeline / monitoring
#   - recipe_fleet uses QA-scoped S3 prefixes (run-separation rule)
#   - live_pulse ships with the hourly clock DISABLED (canary rollout)
#   - the gha-runner module is omitted: QA shares staging's self-hosted runner
#     (same qgi-frontend repo registration), so no second runner / no $/mo.
#
# CI is currently out of GitHub Actions minutes, so this env is applied by a
# reviewed manual `terraform apply` (cost-preflighted, strict-purist-reviewed).
# ===========================================================================

# ---------------------------------------------------------------------------
# Storage — S3, SQS (A only when cascade off), DynamoDB, Glue, Athena, SNS
# ---------------------------------------------------------------------------
module "storage" {
  source = "../../modules/storage"

  environment    = var.environment
  aws_account_id = var.aws_account_id
  region         = var.region
  enable_cascade = false

  tags = local.tags
}

# ---------------------------------------------------------------------------
# IAM — all roles and policies (no enable_cascade var; cascade grants are
# string-ARN policies that are harmless when the targets do not exist)
# ---------------------------------------------------------------------------
module "iam" {
  source = "../../modules/iam"

  environment           = var.environment
  aws_account_id        = var.aws_account_id
  management_account_id = var.management_account_id
  region                = var.region

  data_lake_bucket_arn         = module.storage.bucket_arn
  queue_arns                   = module.storage.all_queue_arns
  indicator_table_arn          = module.storage.indicator_table_arn
  completion_table_arn         = module.storage.completion_table_arn
  indicator_values_table_arn   = module.storage.indicator_values_table_arn
  pipeline_a_counter_table_arn = module.storage.pipeline_a_counter_table_arn
  sns_topic_arn                = module.storage.sns_topic_arn

  # state_machine_arn is "" on first apply (chicken-and-egg). With cascade off
  # the pipeline's Main cascade SFN does not exist, so this stays "" and the
  # EventBridge scheduler role uses its name-based fallback ARN.
  state_machine_arn       = try(module.pipeline.state_machine_arn, "")
  fetch_state_machine_arn = try(module.pipeline.fetch_state_machine_arn, "")

  tags = local.tags
}

# ---------------------------------------------------------------------------
# Batch — Phase A Fargate-Spot fetcher (+ V-Dem/FAO) only; the Phase B SCDI
# compute env / queue / job def are gated off by enable_cascade = false.
# ---------------------------------------------------------------------------
module "batch" {
  source = "../../modules/batch"

  environment           = var.environment
  aws_account_id        = var.aws_account_id
  management_account_id = var.management_account_id
  region                = var.region
  enable_cascade        = false

  batch_job_role_arn       = module.iam.batch_job_role_arn
  ecs_instance_profile_arn = module.iam.ecs_instance_profile_arn
  data_lake_bucket_name    = module.storage.bucket_name

  # #FAR-1: Fargate task roles for the Phase 1 indicator fetcher
  fargate_task_role_arn      = module.iam.fargate_indicator_fetcher_task_role_arn
  fargate_execution_role_arn = module.iam.fargate_execution_role_arn

  tags = local.tags
}

# ---------------------------------------------------------------------------
# Pipeline — Phase A Lambdas + V-Dem + TE chain + ops + live-pulse-adjacent.
# Phase B/C cascade Lambdas + the Main cascade SFN are gated off. The cascade-
# derived inputs below (batch SCDI queue, B/C SQS urls) resolve to "" when
# enable_cascade = false (the module outputs coalesce to "") — safe, since
# their only consumers are themselves gated off.
# ---------------------------------------------------------------------------
module "pipeline" {
  source = "../../modules/pipeline"

  environment           = var.environment
  aws_account_id        = var.aws_account_id
  management_account_id = var.management_account_id
  region                = var.region
  enable_cascade        = false

  data_lake_bucket_name = module.storage.bucket_name
  glue_database_name    = module.storage.glue_database_name
  athena_workgroup_name = module.storage.athena_workgroup_name
  sns_topic_arn         = module.storage.sns_topic_arn

  lambda_execution_role_arn      = module.iam.lambda_execution_role_arn
  stepfunctions_role_arn         = module.iam.stepfunctions_role_arn
  eventbridge_scheduler_role_arn = module.iam.eventbridge_scheduler_role_arn

  # SCDI (Phase B) batch — "" when cascade off (batch outputs coalesce to "").
  batch_job_queue_arn      = module.batch.job_queue_arn
  batch_job_definition_arn = module.batch.job_definition_arn

  queue_a_main_url = module.storage.queue_a_main_url
  queue_a_main_arn = module.storage.queue_a_main_arn
  queue_a_dlq_url  = module.storage.queue_a_dlq_url
  # B/C queues do not exist when cascade off — these outputs are "".
  queue_b_main_url = module.storage.queue_b_main_url
  queue_b_main_arn = module.storage.queue_b_main_arn
  queue_b_dlq_url  = module.storage.queue_b_dlq_url
  queue_c_main_url = module.storage.queue_c_main_url
  queue_c_main_arn = module.storage.queue_c_main_arn
  queue_c_dlq_url  = module.storage.queue_c_dlq_url
  queue_c_dlq_arn  = module.storage.queue_c_dlq_arn

  batch_invoke_mode           = "invoke"
  completion_table_name       = module.storage.completion_table_name
  indicator_values_table_name = module.storage.indicator_values_table_name

  # #FAR-1: Phase 1 Fargate Spot dispatch (always present — data feed for TE)
  fetcher_job_queue_arn      = module.batch.fetcher_job_queue_arn
  fetcher_job_definition_arn = module.batch.fetcher_job_definition_arn
  batch_job_definition_map = {
    WB      = module.batch.fetcher_job_definition_arn
    FAOSTAT = module.batch.fao_fetcher_job_definition_arn
  }
  pipeline_a_counter_table_name = module.storage.pipeline_a_counter_table_name

  # #494: V-Dem annual-refresh pipeline (data feed for TE — always present)
  vdem_batch_job_definition_arn = module.batch.qgi_vdem_ingest_job_definition_arn

  tags = local.tags
}

# ---------------------------------------------------------------------------
# Recipe-fleet — the Trajectory Engine (walk -> bake -> sync). QA-scoped S3
# prefixes per the run-separation rule (never share a vintage namespace with
# staging). Reads the github-dispatch secret created by module.pipeline, hence
# depends_on. The image tag must exist in THIS account's ECR before apply
# (prerequisite: push qgi-recipe-fleet:bake-panels-527004d to 928648269104).
# ---------------------------------------------------------------------------
module "recipe_fleet" {
  source = "../../modules/recipe-fleet"

  environment    = var.environment
  aws_account_id = var.aws_account_id
  region         = var.region

  data_lake_bucket_name = module.storage.bucket_name
  data_lake_bucket_arn  = module.storage.bucket_arn

  ml_results_prefix     = "ml-results-qa-run1/"
  ml_checkpoints_prefix = "ml-checkpoints-qa-run1/"

  recipe_fleet_image_tag = "bake-panels-527004d"

  ecs_instance_profile_arn   = module.iam.ecs_instance_profile_arn
  fargate_execution_role_arn = module.iam.fargate_execution_role_arn
  stepfunctions_role_arn     = module.iam.stepfunctions_role_arn
  lambda_execution_role_arn  = module.iam.lambda_execution_role_arn

  # The frontend-sync Lambda role reads the qgi-github-frontend-dispatch-pat
  # secret created by module.pipeline (bake_trigger.tf, ungated). Force
  # pipeline-first ordering so the plan-time data lookup resolves.
  depends_on = [module.pipeline]

  tags = local.tags
}

# ---------------------------------------------------------------------------
# Monitoring — CloudWatch alarms. The V1.9.1 scoring-drift + caught-exception
# cascade alarms are gated off (their Lambdas do not exist in QA).
# ---------------------------------------------------------------------------
module "monitoring" {
  source = "../../modules/monitoring"

  environment    = var.environment
  sns_topic_arn  = module.storage.sns_topic_arn
  enable_cascade = false

  tags = local.tags
}

# ---------------------------------------------------------------------------
# Live-pulse poller — hourly GDELT-GKG nowcast -> dashboard/hf-pulse-live.json.
# Kept (the TE frontend's live news layer reads it). Ships with the hourly
# clock DISABLED in QA: apply creates the infra without auto-firing; flip to
# "ENABLED" + re-apply only after the QA baseline is seeded and one manual
# invoke is validated (same canary runbook as staging).
# ---------------------------------------------------------------------------
module "live_pulse" {
  source = "../../modules/live-pulse"

  environment    = var.environment
  aws_account_id = var.aws_account_id
  region         = var.region

  data_lake_bucket_name = module.storage.bucket_name
  data_lake_bucket_arn  = module.storage.bucket_arn
  cost_alerts_topic_arn = module.storage.cost_alerts_topic_arn

  schedule_state = "DISABLED"

  tags = local.tags
}

# NOTE: the gha-runner module is intentionally omitted in QA. QA reuses
# staging's self-hosted runner (registered to the same AminAlAit/qgi-frontend
# repo), so no second EC2 runner is provisioned and there is no extra ~$/mo.
