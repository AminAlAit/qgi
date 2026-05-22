# V-Dem ingest Batch JobDef + ECR + log group (#494 step 6).
#
# Annual-cadence Fargate Spot job that consumes the unzipped V-Dem CSV
# from S3 and writes per-indicator parquet partitions to the data
# lake. Sibling of `indicator_fetcher_fao` — same Fargate Spot
# pattern, ARM64, but bigger memory (V-Dem v16 CSV is ~388MB).
#
# Wiring:
#   - Container: pulls from `qgi-pipeline-a-vdem-ingest` ECR repo
#     (defined here; populated by qgi-pipeline's ecr-push.yml workflow)
#   - Compute env: shares the existing `fetcher_fargate_spot` env with
#     WB + FAO (already cost-disciplined: instance-type unrestricted
#     since Fargate is per-task billed; no m7g.16xlarge concern that
#     the EC2-backed scdi compute env had)
#   - Queue: shares the existing `fetcher` queue
#   - Triggered by: Step Functions `qgi-vdem-ingest-on-upload` defined
#     in modules/pipeline/vdem.tf (this file is just the
#     compute-resource side; orchestration is the pipeline module's
#     concern)

resource "aws_ecr_repository" "qgi_vdem_ingest" {
  name                 = "qgi-pipeline-a-vdem-ingest"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "qgi_vdem_ingest" {
  name              = "/aws/batch/qgi-vdem-ingest"
  retention_in_days = 14 # match the FAO sibling — short retention is cost-cheap
  tags              = var.tags
}

resource "aws_batch_job_definition" "qgi_vdem_ingest" {
  name = "qgi-vdem-ingest-job"
  type = "container"

  platform_capabilities = ["FARGATE"]

  retry_strategy {
    # V-Dem ingest is annual + idempotent (#505 covers the
    # ingest_vdem.py-side idempotency claim). Two attempts catches a
    # transient Fargate Spot reclaim mid-run; more is wasteful since
    # whatever caused attempt 2 to fail is unlikely to clear in a
    # third try and we'd rather alert via SNS than burn Fargate
    # minutes silently. Same posture as WB + FAO siblings.
    attempts = 2
  }

  timeout {
    # End-to-end: ~30s S3 download (388MB CSV) + ~2-3min pandas pivot
    # + ~30s parquet writes + ~30s MSCK REPAIR. Worst-case ~5 min;
    # 30 min budget leaves headroom for a slow Athena MSCK or a
    # network-hiccup retry path inside the script.
    attempt_duration_seconds = 1800
  }

  container_properties = jsonencode({
    image   = "${var.aws_account_id}.dkr.ecr.${var.region}.amazonaws.com/qgi-pipeline-a-vdem-ingest:latest"
    command = []

    jobRoleArn       = var.fargate_task_role_arn
    executionRoleArn = var.fargate_execution_role_arn

    resourceRequirements = [
      # V-Dem v16 CSV is 388 MB on disk. The orchestrator downloads
      # it to /tmp (Fargate gives 20 GB ephemeral by default — no
      # concern). The ingest_vdem.py subprocess loads only the 42
      # needed columns via pandas `usecols`, but pandas still has to
      # PARSE the full file in memory before it can apply the
      # column filter. Peak resident: ~700 MB during parse. 4 GB
      # gives ~5x headroom against future V-Dem releases that grow.
      # 2 vCPU keeps pandas BLAS snappy without paying for cores
      # we don't use.
      { type = "VCPU", value = "2" },
      { type = "MEMORY", value = "4096" },
    ]

    networkConfiguration = {
      assignPublicIp = "ENABLED" # required for Fargate to reach S3 + Athena
    }

    fargatePlatformConfiguration = {
      platformVersion = "LATEST"
    }

    runtimePlatform = {
      cpuArchitecture       = "ARM64" # Graviton — ~20% cheaper on Fargate Spot
      operatingSystemFamily = "LINUX"
    }

    environment = [
      # Defaults used only for manual `aws batch submit-job`. Step
      # Functions overrides these via containerOverrides per job:
      #   S3_BUCKET, VDEM_CSV_S3_KEY, AWS_REGION
      { name = "ATHENA_WORKGROUP", value = "QGI-Lambda-Workgroup" },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/aws/batch/qgi-vdem-ingest"
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "vdem-ingest"
      }
    }
  })

  tags = var.tags
}
