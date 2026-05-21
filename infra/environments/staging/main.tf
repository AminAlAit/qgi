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

  # Frontend auth/profile settings table lives in staging only for now.
  enable_user_settings = true
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
  user_settings_table_arn      = module.storage.user_settings_table_arn
  pipeline_a_counter_table_arn = module.storage.pipeline_a_counter_table_arn
  sns_topic_arn                = module.storage.sns_topic_arn

  # state_machine_arn is left empty on first apply (chicken-and-egg).
  # The EventBridge scheduler role gets a wildcard fallback ARN.
  # Re-apply after pipeline module runs to lock it down.
  state_machine_arn       = try(module.pipeline.state_machine_arn, "")
  fetch_state_machine_arn = try(module.pipeline.fetch_state_machine_arn, "")

  # Lets the frontend reader do the account-linking existence check
  # (cognito-idp:ListUsers) that blocks a duplicate Google identity when a
  # password account already owns the email. See modules/iam/vercel_frontend_reader.tf.
  cognito_user_pool_arn = module.cognito.user_pool_arn

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

  # #FAR-1: Fargate task roles for the Phase 1 indicator fetcher
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

  batch_invoke_mode           = "invoke"
  completion_table_name       = module.storage.completion_table_name
  indicator_values_table_name = module.storage.indicator_values_table_name

  # #FAR-1: Phase 1 Fargate Spot dispatch
  fetcher_job_queue_arn      = module.batch.fetcher_job_queue_arn
  fetcher_job_definition_arn = module.batch.fetcher_job_definition_arn
  # #241 Phase B: per-provider JobDef routing. The dispatcher looks up
  # each indicator's `provider` (WB / FAOSTAT / ...) in this map and
  # submits to the matching JobDef. Unknown providers fall back to
  # fetcher_job_definition_arn above. WB is redundantly listed so that
  # even if an indicator is explicitly tagged provider=WB in future data,
  # the map resolves — today's legacy rows without a provider tag also
  # land on WB per the dispatcher's `provider = ind.get("provider") or "WB"`
  # default.
  batch_job_definition_map = merge({
    WB      = module.batch.fetcher_job_definition_arn
    FAOSTAT = module.batch.fao_fetcher_job_definition_arn
    # Enrichment stage 2: new-provider fetchers (keys = dispatcher provider tags).
    # IDMC is wired but needs IDMC_API_KEY before an activated run (deferred).
  }, module.batch.new_fetcher_job_definition_arns)
  pipeline_a_counter_table_name = module.storage.pipeline_a_counter_table_name

  # #494 step 6: V-Dem annual-refresh pipeline. Reuses the shared
  # `fetcher` job queue (Fargate Spot) and adds its own Batch JobDef
  # (defined in module.batch.qgi_vdem_ingest_*). The pipeline module
  # creates the SF state machine + EventBridge trigger + SNS + Lambda
  # in modules/pipeline/vdem.tf.
  vdem_batch_job_definition_arn = module.batch.qgi_vdem_ingest_job_definition_arn
  # `fetcher_job_queue_arn` is already passed above for the WB/FAO
  # dispatcher; the V-Dem SF reuses the same value.

  tags = local.tags
}

# ---------------------------------------------------------------------------
# Recipe-fleet — F-ML-1 multi-recipe ML walk infrastructure
#
# Design doc: docs/specs/internal/ops/ml-track/aws-recipe-fleet-design.md
# Build authorized by founder "go" before `terraform apply`. DO NOT apply
# without cost preflight (qgi-aws-tf/scripts/cost-preflight.sh).
# ---------------------------------------------------------------------------
module "recipe_fleet" {
  source = "../../modules/recipe-fleet"

  environment    = var.environment
  aws_account_id = var.aws_account_id
  region         = var.region

  data_lake_bucket_name = module.storage.bucket_name
  data_lake_bucket_arn  = module.storage.bucket_arn

  # fleet-run-3 (2026-06-01): FRESH prefixes again. run-2's walk data (in ml-results-run2/)
  # was produced by a stale image lacking #136/#137/#141, so it's a write-off; run-3 re-walks
  # on the pinned image into a clean namespace. The resume guard skips any recipe with an
  # existing greedy-result.json, so a NEW prefix is required or all 44 would be skipped. The
  # cloud bake reads the same prefix (--ml-results-prefix var.ml_results_prefix).
  ml_results_prefix     = "ml-results-run3/"
  ml_checkpoints_prefix = "ml-checkpoints-run3/"

  # IMAGE PERMA-FIX (2026-06-01): pin to a SPECIFIC build tag (the module resolves it to an
  # immutable digest), never ':latest'. This is the build carrying the #136/#137/#141
  # walk/score code + the bake fixes — the canary (re-run step 5) must confirm its CLOUD
  # output has shap_value/trajectory_window before any full re-run trusts it.
  recipe_fleet_image_tag = "bake-panels-527004d"

  # Reuse roles already created by the iam module — no new instance profiles
  # or execution roles needed.
  ecs_instance_profile_arn   = module.iam.ecs_instance_profile_arn
  fargate_execution_role_arn = module.iam.fargate_execution_role_arn
  stepfunctions_role_arn     = module.iam.stepfunctions_role_arn
  lambda_execution_role_arn  = module.iam.lambda_execution_role_arn

  # QA PR #36 round-2 NIT-D: recipe-fleet's frontend-sync Lambda role
  # reads the `qgi-github-frontend-dispatch-pat` Secrets Manager secret via
  # `data.aws_secretsmanager_secret`. The secret is CREATED by module.pipeline
  # (bake_trigger.tf). On a net-new account (qa, prod first apply), the data
  # lookup would fail at plan time without this dependency. Staging already
  # has the secret; on qa/prod the dependency forces pipeline-first ordering.
  depends_on = [module.pipeline]

  tags = local.tags
}

# ---------------------------------------------------------------------------
# Monitoring — CloudWatch alarms for V1.9.1 scoring drift (#381)
# ---------------------------------------------------------------------------
module "monitoring" {
  source = "../../modules/monitoring"

  environment   = var.environment
  sns_topic_arn = module.storage.sns_topic_arn
  tags          = local.tags
}

# ---------------------------------------------------------------------------
# Live-pulse poller — hourly GDELT-GKG nowcast -> dashboard/hf-pulse-live.json
#
# Founder go 2026-06-11 ("I like it. Go."). The chosen private-and-free path:
# one bounded Lambda fired hourly by EventBridge Scheduler, in the account
# that owns the data-lake bucket, so the write is an in-account IAM-role call
# (no GitHub minutes, no second cloud, no always-on box, no keys).
#
# CANARY ROLLOUT (SRE + methodology panel 2026-06-12): ships with the hourly
# clock DISABLED so the first apply creates the infra WITHOUT auto-firing.
# Runbook: apply -> seed the baseline -> ONE manual `aws lambda invoke` ->
# validate hf-pulse-live.json (FIPS totals, z near 50, sparsity=null) -> only
# THEN flip schedule_state to "ENABLED" and re-apply + commit. The frontend
# staleness gate falls back to the monthly verdict until the clock is on.
# ---------------------------------------------------------------------------
module "live_pulse" {
  source = "../../modules/live-pulse"

  environment    = var.environment
  aws_account_id = var.aws_account_id
  region         = var.region

  data_lake_bucket_name = module.storage.bucket_name
  data_lake_bucket_arn  = module.storage.bucket_arn
  cost_alerts_topic_arn = module.storage.cost_alerts_topic_arn

  # Canary passed 2026-06-12 (status live, 65/72 cells, FIPS correct); clock on.
  schedule_state = "ENABLED"

  tags = local.tags
}

# ---------------------------------------------------------------------------
# GHA self-hosted runner — c7g.medium Spot Graviton (qgi-aws-tf#970)
#
# Replaces GHA-hosted minutes for the qgi-frontend repo so the
# `sync-te-fleet-vintage.yml` workflow (lane 2 of the pipeline build) can
# run. Founder declined GHA top-up (`feedback_aws_cost_rule_qgi_rnd_001.md`)
# — self-hosted is the alternative; ~$5/mo.
#
# PREREQUISITE before `terraform apply` (founder one-time setup):
#   Create the runner registration secret with a fine-grained PAT:
#     aws secretsmanager create-secret \
#       --name qgi-gha-runner-registration-frontend-pat \
#       --secret-string "<PAT with Administration: Read and Write on qgi-frontend>"
#
# Module README: ../../modules/gha-runner/README.md
# ---------------------------------------------------------------------------
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

module "gha_runner_frontend" {
  source = "../../modules/gha-runner"

  repo                   = "AminAlAit/qgi-frontend"
  runner_label           = "qgi-frontend" # MUST match runs-on label in workflow YAML
  runner_pat_secret_name = "qgi-gha-runner-registration-frontend-pat"

  vpc_id = data.aws_vpc.default.id
  # QA nit: AWS returns subnet ids in undefined order; `sort` makes the
  # plan deterministic so a re-plan doesn't bounce the runner across AZs.
  subnet_id = sort(data.aws_subnets.default.ids)[0]

  instance_type = "c7g.medium"

  # Switched OFF 2026-08-28. Measured over 14 days: 0.4% mean CPU, zero hours
  # above 20% - no build had run in a fortnight while it billed ~$17.30/month
  # (spot $12.97 + public IPv4 $2.87 + 20GB gp3 $1.46, all released on
  # termination since delete_on_termination = true).
  #
  # CI is still wanted for this repo, so this is a PAUSE, not a retirement.
  # Set back to 1 and apply to restore; nothing here has been deleted.
  desired_capacity = 0

  tags = local.tags
}
