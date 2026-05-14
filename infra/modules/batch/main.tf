# ---------------------------------------------------------------------------
# Default VPC — Batch compute environment runs in the default VPC.
# For prod, consider a dedicated VPC with private subnets.
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
# Batch compute environment (Cascade/SCDI-exclusive — gated by enable_cascade)
# Right-sized: jobs need 2 vCPU / 4 GB.
# Spot with multiple Graviton instance types for best availability + price.
# m6g.large (~$0.034/hr), c7g.large (~$0.043/hr), m7g.large (~$0.045/hr)
# All verified available in eu-central-1 a/b/c.
# maxvCpus=512 for good concurrency. Spot is cheaper but slower to allocate.
# ---------------------------------------------------------------------------
# moved block: aws_batch_compute_environment.scdi_spot -> scdi_spot[0]
moved {
  from = aws_batch_compute_environment.scdi_spot
  to   = aws_batch_compute_environment.scdi_spot[0]
}

resource "aws_batch_compute_environment" "scdi_spot" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count                    = var.enable_cascade ? 1 : 0
  compute_environment_name = "qgi-pipeline-b-spot-environment"
  type                     = "MANAGED"
  state                    = "ENABLED"

  compute_resources {
    type                = "SPOT"
    allocation_strategy = "SPOT_CAPACITY_OPTIMIZED"
    instance_type       = ["m6g.large", "c7g.large", "m7g.large"]

    min_vcpus     = 0
    max_vcpus     = 512
    desired_vcpus = 0

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
# Batch job queue (Cascade/SCDI-exclusive — gated by enable_cascade)
# ---------------------------------------------------------------------------
# moved block: aws_batch_job_queue.scdi -> scdi[0]
moved {
  from = aws_batch_job_queue.scdi
  to   = aws_batch_job_queue.scdi[0]
}

resource "aws_batch_job_queue" "scdi" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count    = var.enable_cascade ? 1 : 0
  name     = "qgi-pipeline-b-high-priority-queue"
  state    = "ENABLED"
  priority = 100

  compute_environment_order {
    order               = 1
    compute_environment = aws_batch_compute_environment.scdi_spot[0].arn
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# CloudWatch log group for Batch job logs (Cascade/SCDI-exclusive — gated by enable_cascade)
# Must exist before the first job runs; awslogs driver will fail otherwise.
# ---------------------------------------------------------------------------
# moved block: aws_cloudwatch_log_group.scdi_finder -> scdi_finder[0]
moved {
  from = aws_cloudwatch_log_group.scdi_finder
  to   = aws_cloudwatch_log_group.scdi_finder[0]
}

resource "aws_cloudwatch_log_group" "scdi_finder" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count             = var.enable_cascade ? 1 : 0
  name              = "/aws/batch/qgi-scdi-finder"
  retention_in_days = 30
  tags              = var.tags
}

# Phase 5 v0.0b Stage D: log group for dscdi-finder Batch job (Cascade/SCDI-exclusive — gated by enable_cascade).
# moved block: aws_cloudwatch_log_group.dscdi_finder -> dscdi_finder[0]
moved {
  from = aws_cloudwatch_log_group.dscdi_finder
  to   = aws_cloudwatch_log_group.dscdi_finder[0]
}

resource "aws_cloudwatch_log_group" "dscdi_finder" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count             = var.enable_cascade ? 1 : 0
  name              = "/aws/batch/qgi-dscdi-finder"
  retention_in_days = 30
  tags              = var.tags
}

# ---------------------------------------------------------------------------
# Phase 1 indicator fetcher — Fargate Spot (#FAR-1)
#
# Replaces the legacy EC2+SSM single-instance fetcher with a fan-out to
# AWS Batch on Fargate Spot, one job per indicator. Each task sleeps a
# random 1-5 min before its WB API call so the requests naturally spread
# across time. Each Fargate Spot task gets its own public IP, so the WB
# rate limiter sees N independent clients instead of one source.
#
# Fargate Spot vs EC2 Spot:
# - No instance management, no boot time amortization
# - Smallest possible config: 0.25 vCPU + 512 MB RAM (~$0.0008 per task)
# - Each task gets its own micro-VM with its own ENI/IP
# - eu-central-1 quotas verified (sustained 20/sec, burst 100, 30 vCPU concurrent)
# ---------------------------------------------------------------------------

# Per-environment ECR repo for the WB indicator-fetcher image.
#
# #152 Path A (cross-account pull from the management-account ECR
# alongside scdi-finder) was attempted and parked. Staging owns its own
# copy of the WB fetcher image here; the job definition below
# references it via `${var.aws_account_id}.dkr.ecr.../qgi-pipeline-a-
# indicator-fetcher:latest`. If we ever resume #152, flip the JobDef's
# image URI to `${var.management_account_id}...` and `terraform rm`
# this resource only after the management ECR is primed and a WB
# fetcher run has succeeded pulling cross-account.
resource "aws_ecr_repository" "indicator_fetcher" {
  name                 = "qgi-pipeline-a-indicator-fetcher"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = var.tags
}

# Fargate Spot compute environment — no instances, no AMIs, no scaling.
# Just submits tasks and Fargate provisions micro-VMs on demand.
resource "aws_batch_compute_environment" "fetcher_fargate_spot" {
  compute_environment_name = "qgi-pipeline-a-fetcher-fargate-spot"
  type                     = "MANAGED"
  state                    = "ENABLED"

  compute_resources {
    type      = "FARGATE_SPOT"
    max_vcpus = 30 # service quota; bumpable via support ticket if needed for V1.6.0

    subnets            = data.aws_subnets.default.ids
    security_group_ids = [data.aws_security_group.default.id]
  }

  tags = var.tags
}

resource "aws_batch_job_queue" "fetcher" {
  name     = "qgi-pipeline-a-fetcher-queue"
  state    = "ENABLED"
  priority = 100

  compute_environment_order {
    order               = 1
    compute_environment = aws_batch_compute_environment.fetcher_fargate_spot.arn
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "indicator_fetcher" {
  name              = "/aws/batch/qgi-indicator-fetcher"
  retention_in_days = 14
  tags              = var.tags
}

# ---------------------------------------------------------------------------
# #241 Phase B — FAOSTAT indicator fetcher (Fargate Spot, bulk-download)
#
# Sibling of the WB per-indicator fetcher above. Pattern differs:
# - WB: one task per indicator, per-indicator API call.
# - FAOSTAT: one task per DOMAIN (FS, RL, RFB, TM, PP, Forestry, GT,
#   QCL), downloads the domain ZIP once and emits Parquet for every
#   indicator in that domain. Far more efficient than 15 tasks each
#   downloading the same ZIP.
#
# Shares the `fetcher_fargate_spot` compute environment + `fetcher`
# queue with the WB JobDef — FAOSTAT tasks look identical at the
# Fargate layer (small Graviton Spot task, 60-min timeout). Only the
# image + resourceRequirements differ. Dispatcher decides which
# JobDef to submit to based on the indicator's `provider` field
# (#240 Phase A BATCH_JOB_DEFINITION_MAP env var).
#
# Resource sizing vs WB: WB uses 0.25 vCPU + 512 MB (per-indicator
# API call, light). FAOSTAT downloads + parses 50-200 MB CSVs in
# pandas, so we allocate 1 vCPU + 2 GB. Still pennies per task on
# Fargate Spot Graviton.
# ---------------------------------------------------------------------------

resource "aws_ecr_repository" "indicator_fetcher_fao" {
  name                 = "qgi-pipeline-a-indicator-fetcher-fao"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "indicator_fetcher_fao" {
  name              = "/aws/batch/qgi-indicator-fetcher-fao"
  retention_in_days = 14
  tags              = var.tags
}

resource "aws_batch_job_definition" "indicator_fetcher_fao" {
  name = "qgi-indicator-fetcher-fao-job"
  type = "container"

  platform_capabilities = ["FARGATE"]

  retry_strategy {
    # Same reasoning as the WB JobDef (#243): timeouts aren't
    # transient; a failed FAOSTAT download typically means the CDN
    # is having a bad time and a 3rd attempt won't help. Hard-kill
    # path (SIGKILL / Spot reclaim) is caught by the EventBridge
    # failure-handler Lambda that writes FAILED tracker rows.
    attempts = 2
  }

  timeout {
    # FAOSTAT bulk ZIPs take 1-3 min to download + 1-5 min to parse
    # + a few seconds per indicator to write Parquet. 60 min is
    # comfortably above worst case; matches the WB JobDef's budget.
    attempt_duration_seconds = 3600
  }

  container_properties = jsonencode({
    image   = "${var.aws_account_id}.dkr.ecr.${var.region}.amazonaws.com/qgi-pipeline-a-indicator-fetcher-fao:latest"
    command = []

    jobRoleArn       = var.fargate_task_role_arn
    executionRoleArn = var.fargate_execution_role_arn

    resourceRequirements = [
      # FAOSTAT CSVs run 50-200 MB; pandas loads the whole file into
      # memory before filtering. 2 GB gives comfortable headroom
      # (largest domain observed is ~180 MB unzipped). 1 vCPU keeps
      # pandas' BLAS operations snappy.
      { type = "VCPU", value = "1" },
      { type = "MEMORY", value = "2048" },
    ]

    networkConfiguration = {
      assignPublicIp = "ENABLED" # required for Fargate to reach FAOSTAT CDN + S3
    }

    fargatePlatformConfiguration = {
      platformVersion = "LATEST"
    }

    runtimePlatform = {
      cpuArchitecture       = "ARM64" # ~20% cheaper on Fargate Spot
      operatingSystemFamily = "LINUX"
    }

    environment = [
      # Defaults used only if a manual `aws batch submit-job` is run.
      # In normal operation the dispatcher overrides these per-unit
      # via containerOverrides.
      { name = "JITTER_MIN_S", value = "60" },
      { name = "JITTER_MAX_S", value = "300" },
      { name = "MAX_FETCH_ATTEMPTS", value = "5" },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/aws/batch/qgi-indicator-fetcher-fao"
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "fetch-fao"
      }
    }
  })

  tags = var.tags
}

# Job definition: 0.25 vCPU + 512 MB.
#
# GH#243 perma fix (2026-04-16): heavy WB indicators (FI.RES.TOTL.MO,
# BM.TRF.PWKR.CD.DT, etc.) were timing out at 15 min. Bumped to a generous
# 60 min so even the slowest indicators have headroom. Retries dropped from
# 10 \u2192 2 because timeouts aren't transient \u2014 retrying just burns Fargate.
#
# Hard-kill failures (timeout, OOM, Spot reclaim) bypass the worker's
# graceful failure path. Closed via the EventBridge rule + failure-handler
# Lambda (see modules/pipeline/main.tf).
resource "aws_batch_job_definition" "indicator_fetcher" {
  name = "qgi-indicator-fetcher-job"
  type = "container"

  platform_capabilities = ["FARGATE"]

  retry_strategy {
    attempts = 2 # GH#243: was 10. Timeouts aren't transient.
  }

  timeout {
    attempt_duration_seconds = 3600 # GH#243: was 900 (15min). Now 60min.
  }

  container_properties = jsonencode({
    # Per-environment ECR repo (not cross-account from management).
    # #152 Path A was parked — using local staging ECR for now.
    image   = "${var.aws_account_id}.dkr.ecr.${var.region}.amazonaws.com/qgi-pipeline-a-indicator-fetcher:latest"
    command = []

    jobRoleArn       = var.fargate_task_role_arn
    executionRoleArn = var.fargate_execution_role_arn

    resourceRequirements = [
      { type = "VCPU", value = "0.25" },
      { type = "MEMORY", value = "512" },
    ]

    networkConfiguration = {
      assignPublicIp = "ENABLED" # required for Fargate to reach WB + S3 in default VPC
    }

    fargatePlatformConfiguration = {
      platformVersion = "LATEST"
    }

    # #FAR-1: arm64 — ~20% cheaper on Fargate Spot than x86, and keeps the
    # Phase 1 fetcher consistent with the rest of the Graviton stack.
    runtimePlatform = {
      cpuArchitecture       = "ARM64"
      operatingSystemFamily = "LINUX"
    }

    environment = [
      # Most env vars are overridden by the dispatcher per-job; defaults
      # here are used only if a manual `aws batch submit-job` is run for
      # debugging.
      { name = "JITTER_MIN_S", value = "60" },
      { name = "JITTER_MAX_S", value = "300" },
      { name = "MAX_FETCH_ATTEMPTS", value = "10" },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/aws/batch/qgi-indicator-fetcher"
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "fetch"
      }
    }
  })

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Batch job definition — scdi-finder (Cascade/SCDI-exclusive — gated by enable_cascade)
# Image lives in the management account ECR (shared registry).
# Cross-account pull requires an ECR resource policy in the management
# account — add to qgi-aws-tf Terraform (tracked in issue #8).
# ---------------------------------------------------------------------------
# moved block: aws_batch_job_definition.scdi_finder -> scdi_finder[0]
moved {
  from = aws_batch_job_definition.scdi_finder
  to   = aws_batch_job_definition.scdi_finder[0]
}

resource "aws_batch_job_definition" "scdi_finder" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count = var.enable_cascade ? 1 : 0
  name  = "scdi-finder-job"
  type  = "container"

  platform_capabilities = ["EC2"]

  container_properties = jsonencode({
    image   = "${var.management_account_id}.dkr.ecr.${var.region}.amazonaws.com/qgi-pipeline-b-scdi-finder:latest"
    command = []

    # T12 #305 HIGH fix (2026-04-19): executionRoleArn was erroneously set
    # to the task role (batch_job_role_arn). AWS Batch execution role and
    # task role serve different IAM trust principals — the execution role
    # is assumed by ECS (or Fargate) to pull the image + ship CloudWatch
    # logs, while the task role is assumed by the code INSIDE the
    # container. Conflating them gives the container the image-pull and
    # logging permissions as well, expanding its blast radius.
    #
    # The fargate_execution role already exists in the iam module with the
    # correct trust (ecs-tasks.amazonaws.com) + AmazonECSTaskExecutionRolePolicy.
    # Reused here for the scdi-finder Batch job (EC2-backed) — AWS uses
    # the same trust principal for Batch-on-EC2 and Batch-on-Fargate.
    jobRoleArn       = var.batch_job_role_arn
    executionRoleArn = var.fargate_execution_role_arn

    resourceRequirements = [
      { type = "VCPU", value = "2" },
      { type = "MEMORY", value = "4096" },
    ]

    environment = [
      { name = "S3_BUCKET", value = var.data_lake_bucket_name },
      { name = "S3_INPUT_PREFIX", value = "pipeline-A-indicator-extractor/output/parquet-completed/" },
      { name = "S3_OUTPUT_PREFIX", value = "pipeline-B-scdi-finder/scdis-compacted" },
      { name = "MIN_LENGTH", value = "3" },
      { name = "CORRELATION_THRESHOLD", value = "0.5" },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/aws/batch/qgi-scdi-finder"
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "scdi"
      }
    }
  })

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Batch job definition — dscdi-finder (Cascade/SCDI-exclusive — gated by enable_cascade)
# ---------------------------------------------------------------------------
# moved block: aws_batch_job_definition.dscdi_finder -> dscdi_finder[0]
moved {
  from = aws_batch_job_definition.dscdi_finder
  to   = aws_batch_job_definition.dscdi_finder[0]
}
# DSCDI = Detrended Similar-Country Dynamic Indicator. Per the Phase 5 v0.0b
# unanimous CSD reconvene DECISION 2026-05-05, this Batch job runs ALONGSIDE
# scdi-finder (additive, not replacement). It uses the same indicator-panel
# input but applies the two-pass DSCDI algorithm: per-class transformation
# (first-diff for I(1), log-diff for SP.POP.TOTL, pass-through for I(0)) +
# common-factor demeaning for Class A (severe-CSD global-arc) indicators.
#
# Image is BUILT BUT NOT YET PUBLISHED at Stage D — the dscdi-finder ECR
# repository will be populated when the Stage F authorization fires. The
# `:latest` tag below resolves at apply time; AWS Batch tolerates a
# missing image in the job definition (only fails at job submission).
#
# Job definition is registered at Stage D so the Step Functions or manual
# job-submission orchestration in Stage F has a target. No jobs are
# submitted at Stage D.
#
# The DSCDI module (qgi-pipeline/batch/dscdi-finder/src/dscdi_finder.py,
# merged via qgi-pipeline#22 on 2026-05-05) is the core methodology code.
# The eventual Batch container will wrap this module with env-var-driven
# main() + S3 input/output orchestration mirroring scdi-finder's pattern.
#
# Resource sizing matches scdi-finder (2 vCPU / 4 GB RAM) per per-indicator
# job convention. Adjustable when Stage F's actual workload is benchmarked.
#
# References:
#   - Stage C input spec: docs/specs/internal/ops/cascade-track/phase-5-v0.0b-stage-c-input-spec.md
#   - CSD reconvene DECISION: docs/specs/internal/majles/in-progress/2026-05-05_Ihsa_phase5-v0-0b-csd-reconvene_DECISION.md
resource "aws_batch_job_definition" "dscdi_finder" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count = var.enable_cascade ? 1 : 0
  name  = "dscdi-finder-job"
  type  = "container"

  platform_capabilities = ["EC2"]

  container_properties = jsonencode({
    image   = "${var.management_account_id}.dkr.ecr.${var.region}.amazonaws.com/qgi-pipeline-b-dscdi-finder:latest"
    command = []

    jobRoleArn       = var.batch_job_role_arn
    executionRoleArn = var.fargate_execution_role_arn

    resourceRequirements = [
      { type = "VCPU", value = "2" },
      { type = "MEMORY", value = "4096" },
    ]

    environment = [
      { name = "S3_BUCKET", value = var.data_lake_bucket_name },
      { name = "S3_INPUT_PREFIX", value = "pipeline-A-indicator-extractor/output/parquet-completed/" },
      { name = "S3_OUTPUT_PREFIX", value = "pipeline-B-dscdi-finder/dscdis" },
      # MANIFEST_S3_PREFIX (Stage F preflight 2026-05-06): per-indicator
      # diagnostic manifest written by the entrypoint as a single 1-row
      # Parquet at {prefix}{indicator_id}.parquet. The Glue table
      # `qgi_data.dscdi_indicator_manifest` (defined in modules/storage/main.tf)
      # is the Phase 6 EB framework's queryable substrate-quality surface.
      # Trailing slash on the value: the entrypoint joins `{prefix}{indicator_id}.parquet`
      # directly without re-adding a separator, matching the Glue table's
      # location attribute.
      { name = "MANIFEST_S3_PREFIX", value = "pipeline-B-dscdi-finder/manifest/" },
      # AUDIT_JSON_S3_KEY: the Stage A v2 audit JSON the writer reads to
      # determine per-indicator transformation + Class A/B/C assignment.
      # Path-as-string allows future audit revisions (e.g., post-CIPS
      # 2026-06-04) to be wired without redeploying the container.
      { name = "AUDIT_JSON_S3_KEY", value = "reference/indicator-stationarity-audit-v2.json" },
      { name = "MIN_LENGTH", value = "3" },
      # CORRELATION_THRESHOLD intentionally absent — DSCDI computes the full
      # pairwise Pearson matrix per the 6-way mini-Majles methodology DECISION
      # (no thresholding, no windowed segments). Earlier Stage D drafts copied
      # the SCDI threshold env var by mistake; removed 2026-05-06.
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/aws/batch/qgi-dscdi-finder"
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "dscdi"
      }
    }
  })

  tags = var.tags
}
