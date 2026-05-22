# Enrichment stage 2 — new-provider indicator fetchers (Fargate Spot).
#
# One ECR repo + log group + Batch JobDef per new provider, built with for_each
# off a single map (cleaner than copy-pasting the FAO block 7x). All share the
# `fetcher_fargate_spot` compute env + `fetcher` queue (same as WB/FAOSTAT) and
# the canonical parquet-completed output contract. The dispatcher routes each
# provider's indicators to its JobDef via BATCH_JOB_DEFINITION_MAP (wired in
# environments/<env>/main.tf -> module.pipeline.batch_job_definition_map).
#
# Images are built + pushed separately (qgi-pipeline/batch/indicator-fetcher-<slug>/,
# build context = qgi-pipeline/batch/). JobDefs reference :latest like the WB/FAO
# JobDefs; a run uses whatever digest :latest points to at submit time.
#
# NOTE (IDMC): the IDMC fetcher reads IDMC_API_KEY from the environment. Per
# founder (2026-06-25) the key wiring is deferred — the JobDef exists but carries
# no key, so an IDMC task will fail gracefully (FAILED tracker row) until the key
# is supplied (e.g. an SSM SecureString via a `secrets` block + execution-role
# ssm:GetParameters). Keep IDMC out of an activated run until then.
locals {
  new_fetchers = {
    UNHCR   = { slug = "unhcr", vcpu = "1", memory = "2048" }
    UCDP    = { slug = "ucdp", vcpu = "1", memory = "2048" }
    ILOSTAT = { slug = "ilostat", vcpu = "1", memory = "2048" }
    OECD    = { slug = "oecd", vcpu = "1", memory = "2048" }
    IDMC    = { slug = "idmc", vcpu = "1", memory = "2048" }
    UNDP    = { slug = "undp", vcpu = "1", memory = "2048" }
    OWID    = { slug = "owid", vcpu = "1", memory = "2048" }
  }
}

resource "aws_ecr_repository" "new_fetcher" {
  for_each             = local.new_fetchers
  name                 = "qgi-pipeline-a-indicator-fetcher-${each.value.slug}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "new_fetcher" {
  for_each          = local.new_fetchers
  name              = "/aws/batch/qgi-indicator-fetcher-${each.value.slug}"
  retention_in_days = 14
  tags              = var.tags
}

resource "aws_batch_job_definition" "new_fetcher" {
  for_each = local.new_fetchers
  name     = "qgi-indicator-fetcher-${each.value.slug}-job"
  type     = "container"

  platform_capabilities = ["FARGATE"]

  retry_strategy {
    # Same reasoning as the WB/FAO JobDefs: API/timeout failures aren't transient,
    # so 2 attempts (mainly to absorb a Spot reclaim), not 10.
    attempts = 2
  }

  timeout {
    # Bulk SDMX/CSV pulls + pandas parse fit comfortably under 60 min (matches FAO).
    attempt_duration_seconds = 3600
  }

  container_properties = jsonencode({
    image   = "${var.aws_account_id}.dkr.ecr.${var.region}.amazonaws.com/qgi-pipeline-a-indicator-fetcher-${each.value.slug}:latest"
    command = []

    jobRoleArn       = var.fargate_task_role_arn
    executionRoleArn = var.fargate_execution_role_arn

    resourceRequirements = [
      { type = "VCPU", value = each.value.vcpu },
      { type = "MEMORY", value = each.value.memory },
    ]

    networkConfiguration = {
      assignPublicIp = "ENABLED" # required for Fargate to reach the provider API + S3
    }

    fargatePlatformConfiguration = {
      platformVersion = "LATEST"
    }

    runtimePlatform = {
      cpuArchitecture       = "ARM64"
      operatingSystemFamily = "LINUX"
    }

    environment = [
      # Defaults for a manual `aws batch submit-job`; the dispatcher overrides
      # INDICATOR_ID / INDICATORS_JSON per task via containerOverrides.
      { name = "JITTER_MIN_S", value = "60" },
      { name = "JITTER_MAX_S", value = "300" },
      { name = "MAX_FETCH_ATTEMPTS", value = "5" }, # matches the FAO bulk-fetcher default
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/aws/batch/qgi-indicator-fetcher-${each.value.slug}"
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "fetch-${each.value.slug}"
      }
    }
  })

  tags = var.tags
}

# provider (UPPER, matches the dispatcher's provider tag) -> JobDef ARN / ECR URL.
output "new_fetcher_job_definition_arns" {
  value = { for k, r in aws_batch_job_definition.new_fetcher : k => r.arn }
}

output "new_fetcher_ecr_repository_urls" {
  value = { for k, r in aws_ecr_repository.new_fetcher : k => r.repository_url }
}
