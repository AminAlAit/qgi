locals {
  tags = {
    Project     = "qgi"
    Environment = var.environment
    ManagedBy   = "terraform"
    Owner       = "amin.al-ait"
  }
}

# ---------------------------------------------------------------------------
# Storage — S3, SQS, DynamoDB, Glue, Athena
# ---------------------------------------------------------------------------
module "storage" {
  source = "../../modules/storage"

  environment    = var.environment
  aws_account_id = var.aws_account_id
  region         = var.region
  tags           = local.tags
}

# ---------------------------------------------------------------------------
# IAM — all roles and policies
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

  state_machine_arn = try(module.pipeline.state_machine_arn, "")

  tags = local.tags
}

# ---------------------------------------------------------------------------
# Batch — compute environment, job queue, job definition
# ---------------------------------------------------------------------------
module "batch" {
  source = "../../modules/batch"

  environment           = var.environment
  aws_account_id        = var.aws_account_id
  management_account_id = var.management_account_id
  region                = var.region

  batch_job_role_arn       = module.iam.batch_job_role_arn
  ecs_instance_profile_arn = module.iam.ecs_instance_profile_arn
  data_lake_bucket_name    = module.storage.bucket_name

  fargate_task_role_arn      = module.iam.fargate_indicator_fetcher_task_role_arn
  fargate_execution_role_arn = module.iam.fargate_execution_role_arn

  tags = local.tags
}

# ---------------------------------------------------------------------------
# Pipeline — all Lambdas, Step Functions, EventBridge Scheduler
# ---------------------------------------------------------------------------
module "pipeline" {
  source = "../../modules/pipeline"

  environment           = var.environment
  aws_account_id        = var.aws_account_id
  management_account_id = var.management_account_id
  region                = var.region

  data_lake_bucket_name = module.storage.bucket_name
  glue_database_name    = module.storage.glue_database_name
  athena_workgroup_name = module.storage.athena_workgroup_name
  sns_topic_arn         = module.storage.sns_topic_arn

  lambda_execution_role_arn      = module.iam.lambda_execution_role_arn
  stepfunctions_role_arn         = module.iam.stepfunctions_role_arn
  eventbridge_scheduler_role_arn = module.iam.eventbridge_scheduler_role_arn

  batch_job_queue_arn      = module.batch.job_queue_arn
  batch_job_definition_arn = module.batch.job_definition_arn

  queue_a_main_url = module.storage.queue_a_main_url
  queue_a_main_arn = module.storage.queue_a_main_arn
  queue_a_dlq_url  = module.storage.queue_a_dlq_url
  queue_b_main_url = module.storage.queue_b_main_url
  queue_b_main_arn = module.storage.queue_b_main_arn
  queue_b_dlq_url  = module.storage.queue_b_dlq_url
  queue_c_main_url = module.storage.queue_c_main_url
  queue_c_main_arn = module.storage.queue_c_main_arn
  queue_c_dlq_url  = module.storage.queue_c_dlq_url
  queue_c_dlq_arn  = module.storage.queue_c_dlq_arn

  batch_invoke_mode           = "invoke_5"
  dispatch_limit              = 2
  completion_table_name       = module.storage.completion_table_name
  indicator_values_table_name = module.storage.indicator_values_table_name

  # #FAR-1: Phase 1 Fargate Spot dispatch
  fetcher_job_queue_arn         = module.batch.fetcher_job_queue_arn
  fetcher_job_definition_arn    = module.batch.fetcher_job_definition_arn
  pipeline_a_counter_table_name = module.storage.pipeline_a_counter_table_name

  # V-Dem annual-refresh pipeline
  vdem_batch_job_definition_arn = module.batch.qgi_vdem_ingest_job_definition_arn

  tags = local.tags
}
