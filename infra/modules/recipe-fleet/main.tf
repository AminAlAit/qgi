# ---------------------------------------------------------------------------
# Recipe-fleet module — F-ML-1 multi-recipe walk infrastructure.
#
# Design doc: docs/specs/internal/ops/ml-track/aws-recipe-fleet-design.md
# Build checklist: design doc §7.
#
# Architecture (from §1):
#   SFN Choice(mode) →
#     canary → single Batch job → waitForTaskToken approval gate (MANDATORY)
#     fan-out → Map over runnable recipes, MaxConcurrency=2 (serialized §2a)
#   → post-pass Lambda (stub; CI deploys real code)
#
# Cost decisions (§2a, founder-ratified 2026-05-24):
#   - 2-vCPU Graviton instances: c7g.large / c7g.medium / m7g.large
#   - SPOT_LOWEST_PRICE allocation strategy
#   - MaxConcurrency=2 in Map state (serialized; saves nothing on cost but
#     reduces Spot reclaim blast radius per §2a)
#   - Pre-filter sparse recipes via recipe-manifest.json before Map state
#
# IAM: job role has s3 read on parquet data + s3 put on results/checkpoints.
#      NO Athena permission (hard cost-safety requirement from design §3).
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Default VPC — reuse same data sources as modules/batch/main.tf
# ---------------------------------------------------------------------------
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "defaultForAz"
    values = ["true"]
  }
}

data "aws_security_group" "default" {
  name   = "default"
  vpc_id = data.aws_vpc.default.id
}

# ---------------------------------------------------------------------------
# ECR repository — recipe-fleet container image.
#
# Each environment owns its own ECR repo (same pattern as
# qgi-pipeline-a-indicator-fetcher in modules/batch/main.tf; management-
# account cross-account pull is parked, see #152 for prior art).
# Pushed by qgi-pipeline CI/CD via github-actions-qgi-ecr-push role.
# ---------------------------------------------------------------------------
resource "aws_ecr_repository" "recipe_fleet" {
  name                 = "qgi-recipe-fleet"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# IAM — Batch job role (task role for the recipe-fleet container).
#
# Permissions: s3 get on parquet data prefix + s3 put on results/checkpoints.
# EXPLICITLY NO ATHENA — hard cost-safety requirement (design §3, §6).
# CloudWatch Logs write for awslogs driver.
#
# Inline in this module (not delegated to modules/iam) because the recipe-
# fleet's permission set is deliberately narrower than the general batch_job
# role in modules/iam/main.tf (which has full S3 + ECR + logs). Keeping it
# here makes the "no Athena" constraint self-documenting and auditable.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "recipe_fleet_job" {
  name = "qgi-recipe-fleet-job-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "recipe_fleet_job" {
  name = "qgi-recipe-fleet-job-policy"
  role = aws_iam_role.recipe_fleet_job.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # S3 — read indicator parquet panels (synced once per job).
      # Scoped to the data prefix only; no access to other bucket prefixes.
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:HeadObject"]
        Resource = "arn:aws:s3:::${var.data_lake_bucket_name}/${var.parquet_data_prefix}*"
      },
      # S3 — ListBucket for the parquet prefix so sync tools work.
      # Condition limits the list to the data prefix.
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = "arn:aws:s3:::${var.data_lake_bucket_name}"
        Condition = {
          StringLike = {
            "s3:prefix" = ["${var.parquet_data_prefix}*"]
          }
        }
      },
      # S3 — write ml-results + checkpoints. Put/Get own artifacts.
      {
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:GetObject", "s3:HeadObject", "s3:DeleteObject"]
        Resource = [
          "arn:aws:s3:::${var.data_lake_bucket_name}/${var.ml_results_prefix}*",
          "arn:aws:s3:::${var.data_lake_bucket_name}/${var.ml_checkpoints_prefix}*",
        ]
      },
      # S3 — ListBucket for results + checkpoints prefixes.
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = "arn:aws:s3:::${var.data_lake_bucket_name}"
        Condition = {
          StringLike = {
            "s3:prefix" = [
              "${var.ml_results_prefix}*",
              "${var.ml_checkpoints_prefix}*",
            ]
          }
        }
      },
      # S3 — read recipe-manifest.json so the entrypoint can self-filter.
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:HeadObject"]
        Resource = "arn:aws:s3:::${var.data_lake_bucket_name}/${var.recipe_manifest_s3_key}"
      },
      # S3 — read reference artifacts the chain needs as INPUTS (the cohort
      # sidecar cohort-assignments.json the entrypoint downloads at startup; the
      # walk + LOCK gate + track_record require it). Caught by the 2026-05-24
      # canary: the entrypoint's cohort download 403'd without this grant.
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:HeadObject"]
        Resource = "arn:aws:s3:::${var.data_lake_bucket_name}/reference/*"
      },
      # CloudWatch Logs — Batch job logs via awslogs driver.
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:${var.aws_account_id}:log-group:/aws/batch/qgi-recipe-fleet:*"
      },
      # NOTE: NO Athena, NO Glue, NO DynamoDB.
      # The walk operates entirely on local parquet + S3 blobs.
      # Any Athena permission here would violate the hard cost-safety rule
      # (design §3, §6) and must NOT be added without a new design-doc amendment.
    ]
  })
}

# ---------------------------------------------------------------------------
# Batch compute environment — right-sized small Graviton Spot (design §2a).
#
# Instance pool spans c7g.large(2)→c7g.4xlarge(16) so the #962 per-recipe job sizes
# (small 4 / medium 8 / fat 16 vCPU) each place on a best-fit instance; m7g.large is a
# 2-vCPU capacity fallback. c7g.medium (1 vCPU) is EXCLUDED — no job is 1-vCPU. The earlier
# 2-vCPU-only pool was superseded by the FLEET-4 #964-ratified sizing (2026-05-27).
#
# SPOT_PRICE_CAPACITY_OPTIMIZED: the price-aware Batch strategy (AWS Batch has
# no "lowest_price" option — that's an EC2-Fleet term; valid Batch values are
# BEST_FIT / BEST_FIT_PROGRESSIVE / SPOT_CAPACITY_OPTIMIZED /
# SPOT_PRICE_CAPACITY_OPTIMIZED). This picks pools that are both low-price and
# low-interruption — the right realization of the §2a "cheapest Spot" intent,
# and strictly better than the scdi env's SPOT_CAPACITY_OPTIMIZED (which
# ignores price). The walk is single-threaded so a reclaim costs one resumed
# greedy step (minutes) anyway.
# ---------------------------------------------------------------------------
resource "aws_batch_compute_environment" "recipe_fleet_spot" {
  compute_environment_name = "qgi-recipe-fleet-spot"
  type                     = "MANAGED"
  state                    = "ENABLED"

  compute_resources {
    type                = "SPOT"
    allocation_strategy = "SPOT_PRICE_CAPACITY_OPTIMIZED"
    # FLEET-4/#962: SFN Map sets each job's VCPU from the manifest (small 4→c7g.xlarge /
    # medium 8→c7g.2xlarge / fat 16→c7g.4xlarge). c7g.large(2) covers only the job-def
    # DEFAULT (never submitted by a sized job); m7g.large is a 2-vCPU capacity fallback.
    # Batch (SPOT_PRICE_CAPACITY_OPTIMIZED) best-fits each job's vCPU to the cheapest pool.
    instance_type = ["c7g.large", "c7g.xlarge", "c7g.2xlarge", "c7g.4xlarge", "m7g.large"]

    min_vcpus = 0
    # FLEET-9 / Condition F STRUCTURAL COST CAP (the real $100 enforcement): this ceiling
    # bounds the worst-case burn — no Spot-retry storm can outrun it. INVARIANT any raise
    # MUST preserve (PR #33 review: the retry_strategy attempts=2 DOUBLES the bound —
    # a job can run attempts × attempt_duration of billed vCPU; and the SFN 40h ceiling does
    # NOT terminate already-running Batch jobs, so it is not a billing bound):
    #   max_vcpus × attempts × attempt_duration_h × ~$0.05  ≤  $100
    # CHEAPEST-RESTING-STATE (2026-06-02): the 2026-06-01 speed-crank (48->128, paired with
    # MaxConcurrency 5->20 + the 18h->6h timeout cut) was for a planned run-3 re-walk that is
    # NO LONGER happening — run-2's walk data is salvageable, so the only remaining job is a
    # single re-bake. This reverts PAST the FLEET-4 intermediate (the pre-crank baseline was
    # 48, not 16) all the way back to the original sweet spot, because the founder wants the
    # cheapest possible RESTING state, not the throughput-tuned fan-out config. 16 is the
    # exact vCPU of one fat recipe (c7g.4xlarge), so a fat job is never stuck in RUNNABLE; with
    # MaxConcurrency=2 below, fat jobs serialize (one at a time) — the cheapest, smallest-blast-
    # radius shape. This is the founder-ratified quarterly sweet spot (max_vcpus=16 +
    # MaxConcurrency=2 -> ~15-18h / ~$25 for ~44 recipes). FLEET-9 holds with huge margin:
    # 16 × 2 attempts × 8 h × $0.05 = $12.80 worst-case. $0.05/vCPU-hr is a deliberately high
    # (≈3×) Spot upper bound; the $100 DAILY budget (modules/storage fleet_daily_100) monitors
    # on top.
    max_vcpus     = 16
    desired_vcpus = 0 # scale-to-zero — nothing runs between fan-outs

    instance_role = var.ecs_instance_profile_arn

    subnets            = data.aws_subnets.default.ids
    security_group_ids = [data.aws_security_group.default.id]

    ec2_configuration {
      image_type = "ECS_AL2"
    }

    tags = var.tags
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Batch job queue
# ---------------------------------------------------------------------------
resource "aws_batch_job_queue" "recipe_fleet" {
  name     = "qgi-recipe-fleet-queue"
  state    = "ENABLED"
  priority = 100

  compute_environment_order {
    order               = 1
    compute_environment = aws_batch_compute_environment.recipe_fleet_spot.arn
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# CloudWatch log group — must exist before first job (awslogs driver).
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "recipe_fleet" {
  name              = "/aws/batch/qgi-recipe-fleet"
  retention_in_days = 30
  tags              = var.tags
}

# ---------------------------------------------------------------------------
# Batch job definition — recipe-fleet walker (EC2 Spot, arm64).
#
# vcpus=2 / memory=4096: matches the XGBoost walk profile. The walk is
# single-threaded (§2a) so additional vCPUs are wasted. 4 GB comfortably
# holds the parquet panels (tens of MB) + XGBoost model + SHAP.
#
# Each job carries a RECIPE_IDS env var (comma-separated list of recipe_ids
# to run sequentially in that job). The entrypoint processes them in order,
# skipping any with an existing greedy-result.json in S3 (resume-aware).
# ---------------------------------------------------------------------------
# IMAGE PERMA-FIX (2026-06-01): resolve the chosen tag to its immutable digest at
# apply time, so both JobDefs reference qgi-recipe-fleet@sha256:<digest> — never the
# mutable ':latest'. Prevents the run-2 stale-image incident from recurring.
data "aws_ecr_image" "recipe_fleet" {
  repository_name = "qgi-recipe-fleet"
  image_tag       = var.recipe_fleet_image_tag
}

locals {
  recipe_fleet_image = "${var.aws_account_id}.dkr.ecr.${var.region}.amazonaws.com/qgi-recipe-fleet@${data.aws_ecr_image.recipe_fleet.image_digest}"
}

resource "aws_batch_job_definition" "recipe_fleet_walker" {
  name = "qgi-recipe-fleet-walker-job"
  type = "container"

  platform_capabilities = ["EC2"]

  retry_strategy {
    # A Spot reclaim restarts the job; the S3 checkpoint guard means
    # already-completed recipes in the batch are skipped on restart.
    # #931: reduced 3 -> 2. One reclaim retry is enough; a SECOND failure is almost
    # certainly a data/code issue, not a transient reclaim. attempts is the multiplier in
    # the FLEET-9 structural cost cap (max_vcpus × attempts × attempt_duration_h × rate):
    # at 2 × 8 h it is the runaway-cost bound, since the SFN 40h ceiling does NOT kill a
    # running Batch job (see compute env max_vcpus note).
    attempts = 2
  }

  timeout {
    # SAFETY net + per-attempt wall-time bound (NOT a normal-path cost lever — a 3h job costs
    # 3h regardless of this ceiling; it only caps a HUNG job before the attempts=2 retry).
    # The slowest real job (1 fat recipe at 16 vCPU — elections was 21.8h SERIAL on a laptop ->
    # ~2-3h at 16 vCPU; or a ~5-recipe small batch run sequentially) finishes in <3h. 8h is a
    # comfortable ~2.7x safety buffer over that (founder's "tiny extra buffer for safety",
    # 2026-06-02) while staying far below a runaway burn. FLEET-9 cap holds with huge margin:
    # max_vcpus=16 × 2 attempts × 8 h × $0.05 = $12.80.
    attempt_duration_seconds = 28800
  }

  container_properties = jsonencode({
    image   = local.recipe_fleet_image
    command = ["python", "/app/recipe_fleet_entrypoint.py"]

    # Task role: the narrow recipe-fleet job role (no Athena).
    # Execution role: shared Fargate execution role for image-pull + logs.
    jobRoleArn       = aws_iam_role.recipe_fleet_job.arn
    executionRoleArn = var.fargate_execution_role_arn

    resourceRequirements = [
      { type = "VCPU", value = "2" },
      { type = "MEMORY", value = "4096" },
    ]

    # NB: runtimePlatform is Fargate-ONLY — AWS Batch rejects it on EC2-backed
    # job definitions ("runtimePlatform is only applicable for Fargate", apply
    # 2026-05-24). For EC2 Batch the arm64-ness comes from the Graviton instance
    # pool (c7g/m7g) + the arm64 ECS AMI that image_type=ECS_AL2 auto-selects for
    # Graviton; no runtimePlatform block is set (matches the scdi-finder EC2 job).

    environment = [
      # These are default/fallback values. The SFN Map overrides
      # RECIPE_IDS per-job via containerOverrides.
      { name = "S3_BUCKET", value = var.data_lake_bucket_name },
      { name = "PARQUET_DATA_PREFIX", value = var.parquet_data_prefix },
      { name = "ML_RESULTS_PREFIX", value = var.ml_results_prefix },
      { name = "ML_CHECKPOINTS_PREFIX", value = var.ml_checkpoints_prefix },
      { name = "RECIPE_MANIFEST_S3_KEY", value = var.recipe_manifest_s3_key },
      # RECIPE_IDS: comma-separated list of recipe_ids for this job.
      # Overridden per-job by the SFN Map state's Parameters.containerOverrides.
      { name = "RECIPE_IDS", value = "" },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/aws/batch/qgi-recipe-fleet"
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "recipe-fleet"
      }
    }
  })

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Lambda — post-pass (stub).
#
# Placeholder following the modules/pipeline/main.tf pattern (#153):
# raises RuntimeError on invocation so any accidental invocation of the
# undeployed stub is immediately visible in CloudWatch + SFN history.
# Real code is deployed by qgi-pipeline CI/CD.
#
# Responsibilities (when real code ships):
#   - Read all per-recipe result JSONs from s3://…/ml-results/
#   - Compute cross-recipe compound risk
#   - Tiered Recipe-Tracker rollup
#   - Per-country profiles + rankings
#   - Emit frontend country-risks.json
#   - Majles mechanical pre-digest (deterministic tier + gate pass/fail)
# ---------------------------------------------------------------------------
data "archive_file" "recipe_fleet_post_pass_placeholder" {
  type        = "zip"
  output_path = "${path.module}/post_pass_placeholder.zip"
  source {
    content  = <<-EOT
      """Placeholder for qgi-recipe-fleet-post-pass Lambda.
      Real code has not been deployed by CI/CD yet.
      See modules/recipe-fleet/main.tf for rationale (#153 pattern).
      Fix: trigger deploy-lambdas.yml in qgi-pipeline.
      """
      import os

      def lambda_handler(event, context):
          fn = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "<unknown>")
          raise RuntimeError(
              f"PLACEHOLDER STUB STILL LIVE for Lambda '{fn}'. "
              f"Terraform created this function but CI/CD has not yet deployed "
              f"the real code. Trigger: `gh workflow run deploy-lambdas.yml "
              f"--repo AminAlAit/qgi-pipeline -f deploy_all=true` or push "
              f"any commit touching lambdas/recipe-fleet-post-pass/. #153."
          )
    EOT
    filename = "lambda_function.py"
  }
}

resource "aws_cloudwatch_log_group" "recipe_fleet_post_pass" {
  name              = "/aws/lambda/qgi-recipe-fleet-post-pass"
  retention_in_days = 30
  tags              = var.tags
}

resource "aws_lambda_function" "recipe_fleet_post_pass" {
  function_name    = "qgi-recipe-fleet-post-pass"
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.13"
  architectures    = ["arm64"]
  timeout          = 300
  memory_size      = 512
  filename         = data.archive_file.recipe_fleet_post_pass_placeholder.output_path
  source_code_hash = data.archive_file.recipe_fleet_post_pass_placeholder.output_base64sha256
  role             = var.lambda_execution_role_arn

  environment {
    variables = {
      S3_BUCKET           = var.data_lake_bucket_name
      ML_RESULTS_PREFIX   = var.ml_results_prefix
      RECIPE_MANIFEST_KEY = var.recipe_manifest_s3_key
    }
  }

  # CI/CD deploys real code; ignore placeholder filename/hash after first apply.
  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Lambda — vintage-rollup (stub; lane 4 of pipeline build, qgi-aws-tf#972).
#
# Real code lives at qgi-pipeline/lambdas/recipe-fleet-vintage-rollup/
# (already merged at qgi-pipeline#45). Same #153 placeholder pattern as the
# post-pass Lambda: TF creates the function shell; CI/CD deploys the real
# code; lifecycle.ignore_changes lets the deployed code survive subsequent
# applies.
#
# Reads every walk-summary the platform has produced (current vintage at
# ml-results/{recipe}/f-ml-1-poc-summary.json + prior vintages under
# ml-results/_archive/*), builds the cross-vintage rollup, writes:
#   s3://{bucket}/dashboard/admin/te-vintage-rollup.json
# ---------------------------------------------------------------------------
data "archive_file" "recipe_fleet_vintage_rollup_placeholder" {
  type        = "zip"
  output_path = "${path.module}/vintage_rollup_placeholder.zip"
  source {
    content  = <<-EOT
      """Placeholder for qgi-recipe-fleet-vintage-rollup Lambda.
      Real code has not been deployed by CI/CD yet.
      Same #153 pattern as the post-pass Lambda.
      """
      import os

      def lambda_handler(event, context):
          fn = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "<unknown>")
          raise RuntimeError(
              f"PLACEHOLDER STUB STILL LIVE for Lambda '{fn}'. "
              f"Terraform created this function but CI/CD has not yet deployed "
              f"the real code. Trigger: `gh workflow run deploy-lambdas.yml "
              f"--repo AminAlAit/qgi-pipeline -f deploy_all=true` or push "
              f"any commit touching lambdas/recipe-fleet-vintage-rollup/."
          )
    EOT
    filename = "lambda_function.py"
  }
}

resource "aws_cloudwatch_log_group" "recipe_fleet_vintage_rollup" {
  name              = "/aws/lambda/qgi-recipe-fleet-vintage-rollup"
  retention_in_days = 30
  tags              = var.tags
}

resource "aws_lambda_function" "recipe_fleet_vintage_rollup" {
  function_name    = "qgi-recipe-fleet-vintage-rollup"
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.13"
  architectures    = ["arm64"]
  timeout          = 300
  memory_size      = 512
  filename         = data.archive_file.recipe_fleet_vintage_rollup_placeholder.output_path
  source_code_hash = data.archive_file.recipe_fleet_vintage_rollup_placeholder.output_base64sha256
  role             = var.lambda_execution_role_arn

  environment {
    variables = {
      S3_BUCKET         = var.data_lake_bucket_name
      ML_RESULTS_PREFIX = var.ml_results_prefix
    }
  }

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Lambda — frontend-sync (stub; lane 2 of pipeline build, qgi-aws-tf#973).
#
# Real code lives at qgi-pipeline/lambdas/recipe-fleet-frontend-sync/ (merged
# at qgi-pipeline#52). Pure workflow_dispatch dispatcher: fires the
# sync-te-fleet-vintage.yml workflow in AminAlAit/qgi-frontend (merged at
# qgi-frontend#163) once a bake vintage lands in S3.
#
# Reads the GitHub PAT from Secrets Manager
# (qgi-github-frontend-dispatch-pat, already provisioned for the bake-
# country-risks trigger Lambda). No new secret needed.
# ---------------------------------------------------------------------------
data "archive_file" "recipe_fleet_frontend_sync_placeholder" {
  type        = "zip"
  output_path = "${path.module}/frontend_sync_placeholder.zip"
  source {
    content  = <<-EOT
      """Placeholder for qgi-recipe-fleet-frontend-sync Lambda.
      Real code has not been deployed by CI/CD yet.
      Same #153 pattern as sibling stubs.
      """
      import os

      def lambda_handler(event, context):
          fn = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "<unknown>")
          raise RuntimeError(
              f"PLACEHOLDER STUB STILL LIVE for Lambda '{fn}'. "
              f"Terraform created this function but CI/CD has not yet deployed "
              f"the real code. Trigger: `gh workflow run deploy-lambdas.yml "
              f"--repo AminAlAit/qgi-pipeline -f deploy_all=true` or push "
              f"any commit touching lambdas/recipe-fleet-frontend-sync/."
          )
    EOT
    filename = "lambda_function.py"
  }
}

resource "aws_cloudwatch_log_group" "recipe_fleet_frontend_sync" {
  name              = "/aws/lambda/qgi-recipe-fleet-frontend-sync"
  retention_in_days = 30
  tags              = var.tags
}

# QA PR #36 F2 (BLOCK fix): the shared lambda_execution_role has NO
# secretsmanager:GetSecretValue. The frontend-sync Lambda needs to read the
# GitHub PAT to dispatch workflows. Following the existing pattern
# (modules/pipeline/bake_trigger.tf:43-73) we give this Lambda a dedicated
# tight-scoped role with CloudWatch Logs + one Secrets Manager read.
data "aws_secretsmanager_secret" "github_frontend_dispatch_pat" {
  # Created in modules/pipeline/bake_trigger.tf for the existing
  # qgi-frontend-bake-trigger Lambda. Same PAT works for any workflow
  # dispatch on qgi-frontend (actions:write scope).
  name = "qgi-github-frontend-dispatch-pat"
}

resource "aws_iam_role" "recipe_fleet_frontend_sync" {
  name = "qgi-recipe-fleet-frontend-sync-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy" "recipe_fleet_frontend_sync" {
  role = aws_iam_role.recipe_fleet_frontend_sync.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:${var.aws_account_id}:log-group:/aws/lambda/qgi-recipe-fleet-frontend-sync*"
      },
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = data.aws_secretsmanager_secret.github_frontend_dispatch_pat.arn
      },
    ]
  })
}

resource "aws_lambda_function" "recipe_fleet_frontend_sync" {
  function_name    = "qgi-recipe-fleet-frontend-sync"
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.13"
  architectures    = ["arm64"]
  timeout          = 30 # one-shot HTTP POST; no work to do
  memory_size      = 256
  filename         = data.archive_file.recipe_fleet_frontend_sync_placeholder.output_path
  source_code_hash = data.archive_file.recipe_fleet_frontend_sync_placeholder.output_base64sha256
  role             = aws_iam_role.recipe_fleet_frontend_sync.arn

  environment {
    variables = {
      GITHUB_OWNER           = "AminAlAit"
      GITHUB_REPO            = "qgi-frontend"
      GITHUB_WORKFLOW_FILE   = "sync-te-fleet-vintage.yml"
      GITHUB_REF             = "main"
      GITHUB_PAT_SECRET_NAME = "qgi-github-frontend-dispatch-pat"
      S3_BUCKET              = var.data_lake_bucket_name
    }
  }

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Batch JobDefinition — bake-te-fleet-run (lane 5 of pipeline build, qgi-aws-tf#973).
#
# Reuses the same pinned-digest image as the walker (local.recipe_fleet_image —
# qgi-recipe-fleet@sha256:..., never :latest), but with a different command: invoke
# `bake_te_fleet_run_1.py` in AWS mode (BAKE_MODE=aws). The script reads
# walk artifacts from S3, applies all bucket-A enrichments, writes the
# corpus to S3 under frontend-data/te-fleet-run-{N}/.
#
# Script path: the Dockerfile (qgi-pipeline/batch/recipe-fleet/Dockerfile)
# does `COPY --from=qgi-ml scripts/ /app/scripts/` so the bake script lives
# at `/app/scripts/bake_te_fleet_run_1.py` (QA PR #36 F1 fix).
#
# Reference files (countries / recipe-tracker / indicator-catalog) are NOT
# vendored in the image. The bake script accepts s3:// URIs for these args
# (qgi-ml feat/bake-s3-reference-paths-973) and downloads them at startup.
# One-time founder prereq before apply: aws s3 cp the 3 reference files to
# s3://{bucket}/reference/.
#
# 2 vCPU / 4 GB is right-sized — the bake is single-threaded, I/O-bound
# (S3 fetch ~150 files), runs ~1 min.
# ---------------------------------------------------------------------------
resource "aws_batch_job_definition" "bake_te_fleet_run" {
  name = "qgi-bake-te-fleet-run-job"
  type = "container"

  platform_capabilities = ["EC2"]

  retry_strategy {
    attempts = 2 # one Spot reclaim retry; never more (#153 pattern)
  }

  timeout {
    attempt_duration_seconds = 1800 # 30 min — bake is fast (~1 min); 30x headroom
  }

  container_properties = jsonencode({
    image = local.recipe_fleet_image
    command = [
      "python", "/app/scripts/bake_te_fleet_run_1.py",
      "--bucket", var.data_lake_bucket_name,
      "--countries", "s3://${var.data_lake_bucket_name}/reference/countries.json",
      "--recipe-tracker", "s3://${var.data_lake_bucket_name}/reference/recipe-tracker.json",
      "--indicator-catalog", "s3://${var.data_lake_bucket_name}/reference/indicator-catalog-detailed.md",
      # Panel-dependent fields (§C.1 population / §A.2 trajectory_window / §1.4 raw
      # values / §D analog trajectories) need the indicator panels. The bake job runs
      # the script DIRECTLY (not the walk entrypoint that syncs panels) and the image
      # bakes in no panels, so pass the parquet-completed/ prefix as an s3:// URI; the
      # script syncs it locally at startup (image has no s3fs). Without this they null.
      "--panel-root", "s3://${var.data_lake_bucket_name}/pipeline-A-indicator-extractor/output/parquet-completed/",
      # §B.3 precedents corpus (grouped by category==recipe_id) + the per-recipe
      # positives.csv root (vendored in the image at /app/data/shape_inputs_v2) used to
      # tag each precedent's in_training_set flag.
      "--verified-events", "s3://${var.data_lake_bucket_name}/reference/verified-events.json",
      "--shape-inputs-root", "/app/data/shape_inputs_v2",
      # Read the SAME prefix the walk wrote (var.ml_results_prefix). Without this the bake
      # defaults to ml-results/ and bakes the WRONG vintage's data (2026-06-01 finding).
      "--ml-results-prefix", var.ml_results_prefix,
    ]

    # Reuse the walker's job role: same S3 read on parquet panels (used for
    # raw indicator values via --panel-root) + same S3 write scope on
    # ml-results. The bake additionally writes under frontend-data/, which
    # the walker role does NOT include. Add an inline statement below to
    # the walker role policy — see the matching role-policy update later.
    jobRoleArn       = aws_iam_role.recipe_fleet_job.arn
    executionRoleArn = var.fargate_execution_role_arn

    resourceRequirements = [
      { type = "VCPU", value = "2" },
      { type = "MEMORY", value = "4096" },
    ]

    environment = [
      { name = "BAKE_MODE", value = "aws" },
      { name = "S3_BUCKET", value = var.data_lake_bucket_name },
      # OUTPUT_S3_PREFIX is set per-execution by the SFN ContainerOverrides
      # using $$.Execution.Name; restated as a placeholder so the JobDef
      # still works for ad-hoc test invocations.
      { name = "OUTPUT_S3_PREFIX", value = "" },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/aws/batch/qgi-recipe-fleet"
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "bake"
      }
    }
  })

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Extend the recipe-fleet job role: the bake job also writes under
# frontend-data/te-fleet-run-* (S3 PUT). The walker's existing policy
# allows put under ml-results + ml-checkpoints; the bake needs one
# additional prefix.
# ---------------------------------------------------------------------------
resource "aws_iam_role_policy" "recipe_fleet_bake_extra" {
  name = "qgi-recipe-fleet-bake-output-policy"
  role = aws_iam_role.recipe_fleet_job.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # PutObject for the bake outputs. QA F3 (NIT): dropped
      # PutObjectAcl — the bucket is single-account; ACLs not used.
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${var.data_lake_bucket_arn}/frontend-data/te-fleet-run-*"
      },
      # ListBucket on the bucket with prefix condition so the refuse-overwrite
      # guard (_refuse_overwrite_if_baked) can probe for an existing MANIFEST.
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = var.data_lake_bucket_arn
        Condition = {
          StringLike = {
            "s3:prefix" = ["frontend-data/te-fleet-run-*"]
          }
        }
      },
      # GetObject on the reference/ prefix so the bake can download the 3
      # reference files (countries.json, recipe-tracker.json, indicator-
      # catalog-detailed.md) at startup. Founder syncs these once with
      # `aws s3 cp` per the JobDef command comment.
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${var.data_lake_bucket_arn}/reference/*"
      },
    ]
  })
}

# ---------------------------------------------------------------------------
# SQS — durable carrier for the canary approval task-token (design §4).
#
# The "Await Founder Approval" SFN state sends the waitForTaskToken into this
# queue; the founder reads the token from the message and calls
# `aws stepfunctions send-task-success --task-token <token>`. A dedicated
# queue (not a shared pipeline queue) keeps the approval flow isolated and
# auditable. 14-day retention so a token survives a long approval wait.
# ---------------------------------------------------------------------------
resource "aws_sqs_queue" "recipe_fleet_approval" {
  name                       = "qgi-recipe-fleet-approval"
  message_retention_seconds  = 1209600 # 14 days — token must outlive approval wait
  visibility_timeout_seconds = 43200   # 12 h — this is a human-approval queue; a read
  # must not re-expose the token mid-review (review 2026-05-24). Not a processing queue.
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Step Functions — recipe fleet orchestrator.
#
# Flow:
#   0. Read Manifest (Pass — reads recipe_manifest_s3_key, pre-filter)
#   1. Choice: mode == "canary" → Canary Job
#              else            → Fleet Fan-out
#
# Canary path (MANDATORY — design §4):
#   Canary Job (single Batch job, 1 recipe)
#   → Await Founder Approval (waitForTaskToken — STRUCTURALLY blocks fan-out)
#   → Fleet Fan-out (Map over runnable recipes)
#   → Post-pass Lambda
#
# Fan-out path (direct, for subsequent runs where canary already approved):
#   Fleet Fan-out (Map over runnable recipes)
#   → Post-pass Lambda
#
# The waitForTaskToken token is passed as an env-var override to the canary
# Batch job. The entrypoint writes it to S3; the founder (or an automated
# approval script) calls `aws stepfunctions send-task-success --task-token`.
# This is STRUCTURAL: the Map state cannot start until the token is sent.
#
# SFN input schema (FLEET-4b — caller passes the manifest's SIZED runnable_jobs):
#   {
#     "mode": "canary" | "full",
#     "canary_recipe_id": "government_formation",    // canary mode only (use a FAT recipe)
#     "canary_vcpu": 16,                             // canary mode only — REQUIRED; vcpu for
#                                                    //   the canary (omitting it fails the
#                                                    //   States.Format intrinsic at runtime)
#     "runnable_jobs": [                             // from manifest.runnable_jobs (#962)
#       {"recipe_ids": "recipe_a,recipe_b", "vcpu": 8, "tier": "medium"},
#       {"recipe_ids": "recipe_c", "vcpu": 16, "tier": "fat"}
#     ]
#   }
#
# The SFN IAM role (var.stepfunctions_role_arn from modules/iam) already has
# Lambda:InvokeFunction on qgi-*, S3 read/write, and CloudWatch Logs.
# It needs Batch:SubmitJob for the recipe-fleet queue — see GUESS section
# in the module's outputs.tf comment block.
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "recipe_fleet_sfn" {
  name              = "/aws/states/qgi-recipe-fleet"
  retention_in_days = 30
  tags              = var.tags
}

resource "aws_sfn_state_machine" "recipe_fleet" {
  name     = "qgi-recipe-fleet"
  role_arn = var.stepfunctions_role_arn

  # TimeoutSeconds: 40 h covers the worst-case serialized fleet
  # (~23 runnable recipes × ~5h median + elections at 22h). A timeout here
  # is a safety net; individual Batch jobs have their own 36 h per-attempt
  # limit. SFN executions are free after the first 4000 state transitions.
  definition = jsonencode({
    Comment        = "QGI recipe-fleet orchestrator — canary gate + serialized Map fan-out (design §1/§4)"
    TimeoutSeconds = 144000
    StartAt        = "Route by Mode"
    States = {

      # -----------------------------------------------------------------
      # Mode routing: canary (1 recipe + approval gate) vs full fan-out.
      # -----------------------------------------------------------------
      "Route by Mode" = {
        Type = "Choice"
        Choices = [{
          Variable     = "$.mode"
          StringEquals = "canary"
          Next         = "Run Canary Job"
        }]
        Default = "Fleet Fan-out"
      }

      # -----------------------------------------------------------------
      # CANARY PATH
      # Run a single Batch job for one recipe; pass the waitForTaskToken
      # as an env-var override so the job can record it in S3.
      # The Batch integration resource + .sync suffix waits for job
      # completion, then proceeds to the approval gate.
      # -----------------------------------------------------------------
      "Run Canary Job" = {
        Type     = "Task"
        Resource = "arn:aws:states:::batch:submitJob.sync"
        Parameters = {
          JobName       = "qgi-recipe-fleet-canary"
          JobQueue      = aws_batch_job_queue.recipe_fleet.arn
          JobDefinition = aws_batch_job_definition.recipe_fleet_walker.arn
          ContainerOverrides = {
            Environment = [
              { Name = "RECIPE_IDS", "Value.$" = "$.canary_recipe_id" },
              { Name = "RUN_MODE", Value = "canary" },
              # FLEET-4b: size the canary like a real fan-out job so it MEASURES the
              # parallelized cost/time honestly. The consult requires a FAT canary; at the
              # default 2 vCPU a fat recipe would run ~21h serial (useless + itself costly).
              # Caller passes $.canary_vcpu (e.g. 16 for a fat canary).
              { Name = "N_JOBS", "Value.$" = "States.Format('{}', $.canary_vcpu)" },
            ]
            ResourceRequirements = [
              { Type = "VCPU", "Value.$" = "States.Format('{}', $.canary_vcpu)" },
              { Type = "MEMORY", Value = "4096" },
            ]
          }
        }
        ResultPath = "$.canary_result"
        Retry = [{
          ErrorEquals     = ["Batch.BatchException", "States.TaskFailed"]
          IntervalSeconds = 60
          MaxAttempts     = 2
          BackoffRate     = 2
        }]
        Next = "Await Founder Approval"
      }

      # -----------------------------------------------------------------
      # APPROVAL GATE — MANDATORY (design §4).
      #
      # waitForTaskToken: SFN pauses here indefinitely until the founder
      # (or an automated script) calls:
      #   aws stepfunctions send-task-success \
      #     --task-token <token> \
      #     --task-output '{"approved": true}'
      #
      # The token is written to S3 by the canary entrypoint at key:
      #   ml-results/canary-task-token-{execution_name}.txt
      #
      # This gate is STRUCTURAL — the fan-out Map CANNOT start until
      # this state receives the token. It is not a checklist item.
      #
      # No HeartbeatSeconds key is set, so SFN never expects heartbeats
      # and the execution can wait days for founder approval without
      # timing out. The execution-level TimeoutSeconds (40 h) still
      # applies. Add HeartbeatSeconds + a heartbeat-sending Lambda if
      # automated approval is wired later (Slack-button etc.).
      # QA PR #36 round-2 NIT-B: was incorrectly described as
      # "HeartbeatSeconds = 0" — 0 is not a valid SFN ASL value;
      # OMITTING the field is what disables the heartbeat.
      # -----------------------------------------------------------------
      "Await Founder Approval" = {
        Type     = "Task"
        Resource = "arn:aws:states:::sqs:sendMessage.waitForTaskToken"
        # SQS is a convenient durable carrier for the token — it's
        # already available on the account (qgi-pipeline SQS queues).
        # However, we use a dedicated approval SQS here to avoid queue
        # pollution.  If founder prefers SNS+email or Slack, swap the
        # Resource to the appropriate integration and update the send
        # parameters.  The waitForTaskToken mechanic is unchanged.
        #
        # TODO (before first use): create the approval SQS queue and
        # wire its URL into this state, OR replace with an SNS/Lambda
        # approval flow. For now this is wired to a placeholder ARN that
        # will fail at plan time — see GUESS notes in outputs.tf.
        # SQS sendMessage.waitForTaskToken:
        # - QueueUrl must be the HTTPS URL form, not an ARN.
        # - MessageBody is a string; pass the task token directly so the
        #   founder (or an approval script) can read it from the SQS message
        #   and call `aws stepfunctions send-task-success --task-token <token>`.
        Parameters = {
          QueueUrl        = aws_sqs_queue.recipe_fleet_approval.url
          "MessageBody.$" = "$$.Task.Token"
        }
        ResultPath = "$.approval"
        # qgi-aws-tf#971 — Mode Router fix. Canary executions previously fell
        # through into "Fleet Fan-out" which then crashed on the missing
        # `runnable_jobs` field. Route based on $.mode so canary executions end
        # cleanly while full-mode executions still proceed to fan-out.
        Next = "Mode Router"
      }

      # -----------------------------------------------------------------
      # MODE ROUTER (#971 fix) — gate canary executions out of the fan-out.
      #
      # A canary execution only runs ONE recipe + approval; it must NOT
      # enter Fleet Fan-out (which requires $.runnable_jobs). Founder approval
      # of a canary marks the canary good; full fleet runs are dispatched as
      # SEPARATE SFN executions with mode="full".
      # -----------------------------------------------------------------
      "Mode Router" = {
        Type = "Choice"
        Choices = [{
          Variable     = "$.mode"
          StringEquals = "canary"
          Next         = "Canary End"
        }]
        Default = "Fleet Fan-out"
      }

      "Canary End" = {
        Type = "Pass"
        End  = true
      }

      # -----------------------------------------------------------------
      # FAN-OUT — Map over runnable_recipes array.
      #
      # MaxConcurrency=2: design §2a "serialize". Two concurrent jobs
      # keeps the Spot pool from fragmenting while still overlapping
      # I/O-bound S3 sync phases. Set to 1 for maximum serialization.
      #
      # Each item in runnable_recipes is a list of ~5 recipe_ids (pre-
      # batched by build_recipe_manifest.py into "job batches" so each
      # Map iteration = one Batch job covering multiple recipes).
      #
      # FLEET-4b: ItemsPath is "$.runnable_jobs" — the SIZED form from the manifest
      # (build_recipe_manifest #962). Each item = {recipe_ids, vcpu, tier, ...}; the caller
      # passes the manifest's runnable_jobs as the execution input (pre-filtered to N_pos>=60).
      # MaxConcurrency (see the note on the Map state below): actual concurrency is also
      # hard-bounded by the compute env max_vcpus=16 (sum of the jobs' vCPUs), so it never
      # exceeds the cost cap.
      # -----------------------------------------------------------------
      "Fleet Fan-out" = {
        Type      = "Map"
        ItemsPath = "$.runnable_jobs"
        # CHEAPEST-RESTING-STATE (2026-06-02): reverted the 2026-06-01 speed-crank (5 -> 20)
        # back to the design §2a / quarterly-sweet-spot value of 2. The run-3 re-walk that
        # motivated the crank is NOT happening (run-2 is salvageable), so the cheapest, slowest,
        # smallest-blast-radius shape is wanted: 2 jobs at a time serialize the fleet and pair
        # with max_vcpus=16 (one fat job at a time). Real concurrency is also hard-bounded by
        # compute-env max_vcpus=16 (sum of the jobs' vCPUs), so this never exceeds the cost cap.
        MaxConcurrency = 2
        ItemProcessor = {
          ProcessorConfig = {
            Mode = "INLINE"
          }
          StartAt = "Submit Batch Job"
          States = {
            "Submit Batch Job" = {
              Type     = "Task"
              Resource = "arn:aws:states:::batch:submitJob.sync"
              Parameters = {
                # #131 (FLEET-INFRA): $$.Map.Item.Index does NOT resolve inside
                # this inline Map's ItemProcessor at runtime — submitJob fails
                # with "JsonPath argument for $.Map.Item.Index could not be
                # found". Surfaced by the 2026-05-31 fan-out smoke test (the
                # canary path uses a static JobName so never exercised this).
                # Switch to $$.Execution.Name — the proven pattern used by the
                # canary + bake states + the design doc. Batch permits duplicate
                # JobNames across the Map's parallel items; jobIds stay unique.
                "JobName.$"   = "States.Format('qgi-recipe-fleet-{}', $$.Execution.Name)"
                JobQueue      = aws_batch_job_queue.recipe_fleet.arn
                JobDefinition = aws_batch_job_definition.recipe_fleet_walker.arn
                ContainerOverrides = {
                  Environment = [
                    {
                      Name      = "RECIPE_IDS"
                      "Value.$" = "$.recipe_ids" # comma-separated batch for this sized job
                    },
                    {
                      Name = "N_JOBS"
                      # #962: the per-job vCPU = the parallel walk's --n-jobs (#961).
                      "Value.$" = "States.Format('{}', $.vcpu)"
                    }
                  ]
                  # #962: size the Batch container to this job's tier. Both VCPU and MEMORY
                  # are restated (override REPLACES the job-def resourceRequirements by type;
                  # restating both avoids any merge-vs-replace ambiguity). MEMORY stays 4096:
                  # the walk needs little RAM (panels are tens of MB) and 4 GB fits every tier
                  # instance (c7g.xlarge 8 GB → c7g.4xlarge 32 GB) with ECS-agent headroom.
                  ResourceRequirements = [
                    {
                      Type      = "VCPU"
                      "Value.$" = "States.Format('{}', $.vcpu)"
                    },
                    {
                      Type  = "MEMORY"
                      Value = "4096"
                    }
                  ]
                }
              }
              ResultPath = "$.job_result"
              Retry = [{
                ErrorEquals     = ["Batch.BatchException", "States.TaskFailed"]
                IntervalSeconds = 120
                MaxAttempts     = 3
                BackoffRate     = 2
              }]
              End = true
            }
          }
        }
        ResultPath = "$.fleet_results"
        Next       = "Vintage Rollup"
      }

      # -----------------------------------------------------------------
      # VINTAGE ROLLUP Lambda (qgi-aws-tf#972, lane 4).
      #
      # First step of the post-Map chain. Scans the recipe-fleet S3 layout
      # for every walk-summary the platform has produced (current vintage
      # at ml-results/{recipe}/f-ml-1-poc-summary.json + prior vintages
      # under ml-results/_archive/), denormalizes via vintage_rollup_core,
      # writes dashboard/admin/te-vintage-rollup.json. The Admin Dashboard
      # (qgi-aws-tf#151) reads this for the quarterly-trend section.
      # -----------------------------------------------------------------
      "Vintage Rollup" = {
        Type     = "Task"
        Resource = aws_lambda_function.recipe_fleet_vintage_rollup.arn
        Parameters = {
          "current_vintage_id.$" = "$$.Execution.Name"
          "s3_bucket"            = var.data_lake_bucket_name
          "ml_results_prefix"    = var.ml_results_prefix
        }
        ResultPath = "$.vintage_rollup_result"
        Retry = [{
          ErrorEquals     = ["Lambda.TooManyRequestsException", "Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"]
          IntervalSeconds = 30
          MaxAttempts     = 3
          BackoffRate     = 2
        }]
        Next = "Post-pass Lambda"
      }

      # -----------------------------------------------------------------
      # POST-PASS Lambda — cross-recipe aggregation + tier classification.
      # Reads vintage-rollup output + raw walk summaries; emits the
      # post-pass tier classifications used by the bake step.
      # -----------------------------------------------------------------
      "Post-pass Lambda" = {
        Type     = "Task"
        Resource = aws_lambda_function.recipe_fleet_post_pass.arn
        Parameters = {
          "execution_name.$"  = "$$.Execution.Name"
          "s3_bucket"         = var.data_lake_bucket_name
          "ml_results_prefix" = var.ml_results_prefix
        }
        ResultPath = "$.post_pass_result"
        Retry = [{
          ErrorEquals     = ["Lambda.TooManyRequestsException", "Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"]
          IntervalSeconds = 30
          MaxAttempts     = 5
          BackoffRate     = 2
        }]
        Next = "Bake Frontend Corpus"
      }

      # -----------------------------------------------------------------
      # BAKE FRONTEND CORPUS (qgi-aws-tf#973, lane 5).
      #
      # Batch job — invokes bake_te_fleet_run_1.py with BAKE_MODE=aws.
      # Writes the vintage corpus (cards-v3, scores, country-index,
      # rank-history, analogs, activity feed, MANIFEST) directly to S3
      # under frontend-data/te-fleet-run-{execution_name}/. The bake script
      # refuses-to-overwrite if a MANIFEST.json already exists at that
      # prefix (run-separation rule, feedback_run_separation_versioning.md).
      # -----------------------------------------------------------------
      "Bake Frontend Corpus" = {
        Type     = "Task"
        Resource = "arn:aws:states:::batch:submitJob.sync"
        Parameters = {
          "JobName.$"   = "States.Format('qgi-bake-te-fleet-run-{}', $$.Execution.Name)"
          JobQueue      = aws_batch_job_queue.recipe_fleet.arn
          JobDefinition = aws_batch_job_definition.bake_te_fleet_run.arn
          ContainerOverrides = {
            Environment = [
              { Name = "BAKE_MODE", Value = "aws" },
              { Name = "S3_BUCKET", Value = var.data_lake_bucket_name },
              {
                Name      = "OUTPUT_S3_PREFIX"
                "Value.$" = "States.Format('frontend-data/te-fleet-run-{}/', $$.Execution.Name)"
              },
            ]
          }
        }
        ResultPath = "$.bake_result"
        Retry = [{
          ErrorEquals     = ["Batch.BatchException", "States.TaskFailed"]
          IntervalSeconds = 60
          MaxAttempts     = 1
          BackoffRate     = 2
        }]
        Next = "Frontend Sync"
      }

      # -----------------------------------------------------------------
      # FRONTEND SYNC Lambda (qgi-aws-tf#973, lane 2).
      #
      # Fires `workflow_dispatch` on qgi-frontend's sync-te-fleet-vintage.yml
      # workflow. The workflow does the S3 sync + cross-vintage rank-history
      # append + PR creation. Audit-trail mechanism: PR, not webhook,
      # per the architectural pick locked in this session's handoff memo.
      # -----------------------------------------------------------------
      "Frontend Sync" = {
        Type     = "Task"
        Resource = aws_lambda_function.recipe_fleet_frontend_sync.arn
        Parameters = {
          "vintage_s3_prefix.$" = "States.Format('frontend-data/te-fleet-run-{}/', $$.Execution.Name)"
          "execution_name.$"    = "$$.Execution.Name"
        }
        ResultPath = "$.frontend_sync_result"
        Retry = [{
          ErrorEquals     = ["Lambda.TooManyRequestsException", "Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"]
          IntervalSeconds = 30
          MaxAttempts     = 3
          BackoffRate     = 2
        }]
        End = true
      }
    }
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.recipe_fleet_sfn.arn}:*"
    include_execution_data = false
    level                  = "ERROR"
  }

  tags = var.tags
}
