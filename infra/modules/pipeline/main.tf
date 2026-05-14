# ---------------------------------------------------------------------------
# Lambda placeholder zip — used for initial Terraform apply only.
# Real code is deployed by qgi-pipeline CI/CD (deploy-lambdas.yml).
#
# lifecycle.ignore_changes on filename/source_code_hash means re-apply
# after CI/CD deploys real code will not revert it.
#
# IMPORTANT (#153): the placeholder MUST fail loudly on invocation. If a
# Lambda is recreated via TF (rename, immutable attribute change, etc.)
# and no commit subsequently touches its source dir, CI never re-deploys
# and the placeholder ships live. The previous placeholder returned
# {statusCode: 200, body: 'placeholder'}, looking like a successful
# response — Step Functions happily passed it downstream. The result was
# the 2026-04-08 pipeline-ops-batch-checker outage where every pipeline
# run silently broke for days because the checker returned a stub instead
# of {jobs_running: int}.
#
# This placeholder now raises a clear, descriptive RuntimeError on every
# invocation. Any pipeline run hitting a non-deployed Lambda will fail
# within seconds with a self-explanatory error in CloudWatch + the SF
# execution history. Recovery is one CI run away (commit+push or
# `gh workflow run deploy-lambdas.yml -f deploy_all=true`).
# ---------------------------------------------------------------------------
data "archive_file" "placeholder" {
  type        = "zip"
  output_path = "${path.module}/placeholder.zip"
  source {
    content  = <<-EOT
      """Placeholder for a TF-managed Lambda whose real code has not been
      deployed by CI/CD yet. See qgi-infra/modules/pipeline/main.tf for
      the rationale (#153). Fix: trigger deploy-lambdas.yml in qgi-pipeline.
      """
      import os

      def lambda_handler(event, context):
          fn = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "<unknown>")
          raise RuntimeError(
              f"PLACEHOLDER STUB STILL LIVE for Lambda '{fn}'. "
              f"Terraform created or recreated this function but CI/CD "
              f"(qgi-pipeline deploy-lambdas.yml) has not yet deployed "
              f"the real code. Trigger a deploy with: "
              f"`gh workflow run deploy-lambdas.yml --repo AminAlAit/qgi-pipeline "
              f"-f deploy_all=true` or push any commit touching "
              f"lambdas/{fn.removeprefix('qgi-')}/. See #153."
          )
    EOT
    filename = "lambda_function.py"
  }
}

locals {
  # AWS SDK for Pandas layer — provides pandas, pyarrow, numpy, scipy, etc.
  # Pinned to version 1. Check for updates periodically but test before bumping.
  # https://aws-sdk-pandas.readthedocs.io/en/stable/layers.html
  aws_sdk_pandas_layer = "arn:aws:lambda:${var.region}:336392948345:layer:AWSSDKPandas-Python313-Arm64:1"

  lambda_defaults = {
    runtime          = "python3.13"
    architectures    = ["arm64"]
    filename         = data.archive_file.placeholder.output_path
    source_code_hash = data.archive_file.placeholder.output_base64sha256
    role             = var.lambda_execution_role_arn
    layers           = [local.aws_sdk_pandas_layer]
  }
  s3_output_location = "s3://${var.data_lake_bucket_name}/query_results/"

  # Standard retry for all Lambda Task states — handles transient throttles and
  # service errors that are common on new accounts with low burst limits.
  lambda_retry = [{
    ErrorEquals     = ["Lambda.TooManyRequestsException", "Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"]
    IntervalSeconds = 30
    MaxAttempts     = 5
    BackoffRate     = 2
  }]
}

# ---------------------------------------------------------------------------
# Phase 0 — ops janitor (purges all queues before each run)
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "ops_janitor" {
  function_name    = "qgi-pipeline-ops-janitor"
  handler          = "lambda_function.lambda_handler"
  timeout          = 900
  memory_size      = 512
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role
  layers           = local.lambda_defaults.layers

  environment {
    variables = {
      # Cross-reference guard #3: include B/C queue urls only when enable_cascade=true.
      # compact() strips the empty strings that flow through when cascade is off.
      QUEUE_URLS = join(",", compact([
        var.queue_a_main_url, var.queue_a_dlq_url,
        var.enable_cascade ? var.queue_b_main_url : "",
        var.enable_cascade ? var.queue_b_dlq_url : "",
        var.enable_cascade ? var.queue_c_main_url : "",
        var.enable_cascade ? var.queue_c_dlq_url : "",
      ]))
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Phase 1 — sheet fetcher (reads xlsx from S3, writes indicators.json)
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "a_sheet_fetcher" {
  function_name    = "qgi-pipeline-a-sheet-fetcher"
  handler          = "lambda_function.lambda_handler"
  timeout          = 900
  memory_size      = 128
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role
  layers           = local.lambda_defaults.layers

  environment {
    variables = {
      INPUT_BUCKET      = var.data_lake_bucket_name
      INPUT_KEY         = "pipeline-A-indicator-extractor/indicators/Pipeline A Dispatcher World Bank Indicators.xlsx"
      OUTPUT_BUCKET     = var.data_lake_bucket_name
      OUTPUT_KEY        = "indicators/indicators.json"
      INDICATOR_MAP_KEY = "pipeline-A-indicator-extractor/input/indicator_map.csv"
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Phase 1 legacy SQS path (a_dispatcher, a_checker, a_indicator_extractor,
# a_worker, a_worker_sqs event source mapping) was deleted as part of
# #FAR-1. Replaced by the Fargate Spot dispatcher + checker below. Phase 1
# now reads indicators.json directly from S3 in the dispatcher and fans
# out one Fargate task per indicator — no SQS, no Lambda workers.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Phase 1 — Fargate Spot indicator fetcher (#FAR-1)
#
# Replaces the legacy EC2 + SSM Run Command approach (which hit the SSM
# 1-hour command timeout at 36/52 indicators) with a fan-out to AWS Batch
# on Fargate Spot. One Fargate task per indicator. Each task gets its own
# ENI/public IP, sleeps a random 1-5 min before its WB API call, then
# fetches/transforms/uploads.
#
# Coordination uses a DDB counter (qgi-pipeline-a-counter) keyed on run_id.
# The dispatcher seeds the counter to N at submission time (race-free vs
# starting at 0 + incrementing). Each fetcher task decrements on exit
# (success OR failure — the script always exits 0). The checker Lambda
# polls the counter from the Step Function loop.
# ---------------------------------------------------------------------------

# --- Dispatcher Lambda — replaces a_ec2_trigger ---
resource "aws_lambda_function" "a_batch_dispatcher" {
  function_name    = "qgi-pipeline-a-batch-dispatcher"
  handler          = "lambda_function.lambda_handler"
  timeout          = 300
  memory_size      = 256
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role

  environment {
    variables = {
      S3_BUCKET            = var.data_lake_bucket_name
      INDICATORS_KEY       = "pipeline-A-indicator-extractor/input/indicators.json"
      BATCH_JOB_QUEUE      = var.fetcher_job_queue_arn
      BATCH_JOB_DEFINITION = var.fetcher_job_definition_arn
      # #241 Phase B: per-provider JobDef routing. JSON-encoded. When
      # empty ({}), dispatcher falls back to BATCH_JOB_DEFINITION for
      # every indicator (legacy behaviour preserved).
      BATCH_JOB_DEFINITION_MAP = jsonencode(var.batch_job_definition_map)
      COUNTER_TABLE            = var.pipeline_a_counter_table_name
      TRACKER_TABLE            = var.indicator_table_name
      INDICATOR_VALUES_TABLE   = var.indicator_values_table_name
      ATHENA_DATABASE          = var.glue_database_name
      ATHENA_WORKGROUP         = var.athena_workgroup_name
      # #416 — ATHENA_OUTPUT_LOCATION removed; workgroup enforces its own
      # output location. Closes the last env-var leak left after #371.
      JITTER_MIN_S   = tostring(var.phase1_jitter_min_s)
      JITTER_MAX_S   = tostring(var.phase1_jitter_max_s)
      DISPATCH_LIMIT = tostring(var.dispatch_limit)
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# --- Checker Lambda — replaces a_checker for Phase 1 ---
resource "aws_lambda_function" "a_batch_checker" {
  function_name    = "qgi-pipeline-a-batch-checker"
  handler          = "lambda_function.lambda_handler"
  timeout          = 30
  memory_size      = 128
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role

  environment {
    variables = {
      COUNTER_TABLE = var.pipeline_a_counter_table_name
      # #178: scan-count checker reads tracker table instead of counter
      TRACKER_TABLE   = var.indicator_table_name
      DEADMAN_SECONDS = tostring(var.phase1_deadman_seconds)
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Phase 1 — Batch failure handler (GH#243 PERMA FIX)
#
# When a fetcher Fargate task is hard-killed (timeout, OOM, Spot reclaim),
# the worker's `except` block never runs and no FAILED tracker row is
# written. The checker's `tracker_count >= total` completion logic stalls
# forever (until the 90-min L5 deadman fires).
#
# This Lambda subscribes to Batch JobStateChange=FAILED events on the
# fetcher queue, parses INDICATOR_ID + RUN_ID from the dead container's
# environment, and writes a FAILED tracker row. Closes the deadlock.
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "a_batch_failure_handler" {
  function_name    = "qgi-pipeline-a-batch-failure-handler"
  handler          = "lambda_function.lambda_handler"
  timeout          = 30
  memory_size      = 256
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role

  description = "GH#243: writes FAILED tracker row on Batch hard-kill (timeout, OOM, Spot)"

  environment {
    variables = {
      TRACKER_TABLE = var.indicator_table_name
      COUNTER_TABLE = var.pipeline_a_counter_table_name
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

resource "aws_cloudwatch_event_rule" "a_batch_fetcher_failed" {
  name        = "qgi-pipeline-a-batch-fetcher-failed"
  description = "GH#243: routes Batch FAILED events from fetcher queue to failure-handler Lambda"

  event_pattern = jsonencode({
    source        = ["aws.batch"]
    "detail-type" = ["Batch Job State Change"]
    detail = {
      status   = ["FAILED"]
      jobQueue = [var.fetcher_job_queue_arn]
    }
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "a_batch_failure_handler" {
  rule = aws_cloudwatch_event_rule.a_batch_fetcher_failed.name
  arn  = aws_lambda_function.a_batch_failure_handler.arn
}

resource "aws_lambda_permission" "allow_eventbridge_failure_handler" {
  statement_id  = "AllowEventBridgeInvokeFailureHandler"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.a_batch_failure_handler.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.a_batch_fetcher_failed.arn
}

# ---------------------------------------------------------------------------
# Phase 1 — reporter (queries DynamoDB, sends SNS, returns updated_ids)
# Note: reporter also invokes b-orchestrator directly (known prod behaviour,
# kept for parity — means orchestrator is called twice when Step Functions
# also routes to Phase 2. Track fix in qgi-pipeline).
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "a_reporter" {
  function_name    = "qgi-pipeline-a-reporter"
  handler          = "lambda_function.lambda_handler"
  timeout          = 900
  memory_size      = 128
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role
  layers           = local.lambda_defaults.layers

  environment {
    variables = {
      SNS_TOPIC_ARN = var.sns_topic_arn
      # Cross-reference guard #4: b_orchestrator is gated. Use one()+coalesce — NOT a
      # ternary with [0]: Terraform does not reliably short-circuit conditional branches,
      # so aws_lambda_function.b_orchestrator[0] would error at plan when count = 0 (QA).
      # one(...[*].arn) -> arn when cascade on, null when off; coalesce makes that "".
      PIPELINE_B_ARN = try(aws_lambda_function.b_orchestrator[0].arn, "")
      # #FAR-1: tables read by the detailed email reporter
      TRACKER_TABLE = var.indicator_table_name
      COUNTER_TABLE = var.pipeline_a_counter_table_name
      # #175: write fetch manifest to S3 for the decoupled Main SF
      S3_BUCKET    = var.data_lake_bucket_name
      MANIFEST_KEY = "indicator-freshness/latest-fetch-manifest.json"
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Phase 1.5 — indicator completer (ETS self-prediction for missing recent years)
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "a_completer" {
  function_name    = "qgi-pipeline-a-completer"
  handler          = "lambda_function.lambda_handler"
  timeout          = 900
  memory_size      = 1024
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role
  layers           = local.lambda_defaults.layers

  environment {
    variables = {
      S3_BUCKET         = var.data_lake_bucket_name
      INPUT_PREFIX      = "pipeline-A-indicator-extractor/output/parquet"
      OUTPUT_PREFIX     = "pipeline-A-indicator-extractor/output/parquet-completed"
      INDICATOR_MAP_KEY = "pipeline-A-indicator-extractor/input/indicator_map.csv"
      ATHENA_DATABASE   = var.glue_database_name
      ATHENA_WORKGROUP  = var.athena_workgroup_name
      # #148: name of the DDB table to mirror indicator values into
      INDICATOR_VALUES_TABLE_NAME = var.indicator_values_table_name
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Phase 2 — Batch orchestrator (Cascade/SCDI-exclusive — gated by enable_cascade)
# ---------------------------------------------------------------------------
# moved block: aws_lambda_function.b_orchestrator -> b_orchestrator[0]
moved {
  from = aws_lambda_function.b_orchestrator
  to   = aws_lambda_function.b_orchestrator[0]
}

resource "aws_lambda_function" "b_orchestrator" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count            = var.enable_cascade ? 1 : 0
  function_name    = "qgi-pipeline-b-scdi-finder-batch-orchestrator"
  handler          = "lambda_function.lambda_handler"
  timeout          = 900
  memory_size      = 512
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role
  layers           = local.lambda_defaults.layers

  environment {
    variables = {
      S3_BUCKET            = var.data_lake_bucket_name
      S3_INPUT_PREFIX      = "pipeline-A-indicator-extractor/output/parquet-completed/"
      BATCH_JOB_QUEUE      = "qgi-pipeline-b-high-priority-queue"
      BATCH_JOB_DEFINITION = "scdi-finder-job"
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Phase 2 — batch checker (Cascade/SCDI-exclusive — gated by enable_cascade)
# ---------------------------------------------------------------------------
# moved block: aws_lambda_function.ops_batch_checker -> ops_batch_checker[0]
moved {
  from = aws_lambda_function.ops_batch_checker
  to   = aws_lambda_function.ops_batch_checker[0]
}

resource "aws_lambda_function" "ops_batch_checker" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count            = var.enable_cascade ? 1 : 0
  function_name    = "qgi-pipeline-ops-batch-checker"
  handler          = "lambda_function.lambda_handler"
  timeout          = 900
  memory_size      = 128
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role
  layers           = local.lambda_defaults.layers

  environment {
    variables = {
      JOB_QUEUE = var.batch_job_queue_arn
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Phase 2 — b dispatcher (Cascade/SCDI-exclusive — gated by enable_cascade)
# ---------------------------------------------------------------------------
# moved block: aws_lambda_function.b_dispatcher -> b_dispatcher[0]
moved {
  from = aws_lambda_function.b_dispatcher
  to   = aws_lambda_function.b_dispatcher[0]
}

resource "aws_lambda_function" "b_dispatcher" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count            = var.enable_cascade ? 1 : 0
  function_name    = "qgi-pipeline-b-dispatcher"
  handler          = "lambda_function.lambda_handler"
  timeout          = 900
  memory_size      = 128
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role
  layers           = local.lambda_defaults.layers

  environment {
    variables = {
      S3_BUCKET       = var.data_lake_bucket_name
      S3_INPUT_PREFIX = "pipeline-A-indicator-extractor/output/parquet-completed/"
      SQS_QUEUE_URL   = var.queue_b_main_url
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Phase 2 — scdi finder Lambda (Cascade/SCDI-exclusive — gated by enable_cascade)
# Not in Step Functions — triggered manually or via b-dispatcher.
# ---------------------------------------------------------------------------
# moved block: aws_lambda_function.b_scdi_finder -> b_scdi_finder[0]
moved {
  from = aws_lambda_function.b_scdi_finder
  to   = aws_lambda_function.b_scdi_finder[0]
}

resource "aws_lambda_function" "b_scdi_finder" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count            = var.enable_cascade ? 1 : 0
  function_name    = "qgi-pipeline-b-scdi-finder"
  handler          = "lambda_function.lambda_handler"
  timeout          = 900
  memory_size      = 128
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role
  layers           = local.lambda_defaults.layers

  environment {
    variables = {
      S3_BUCKET             = var.data_lake_bucket_name
      S3_INPUT_PREFIX       = "pipeline-A-indicator-extractor/output/parquet-completed/"
      S3_OUTPUT_PREFIX      = "pipeline-B-scdi-finder/scdis-compacted"
      MIN_LENGTH            = "3"
      CORRELATION_THRESHOLD = "0.5"
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Phase 4 — c dispatcher (Cascade/SCDI-exclusive — gated by enable_cascade)
# ---------------------------------------------------------------------------
# moved block: aws_lambda_function.c_dispatcher -> c_dispatcher[0]
moved {
  from = aws_lambda_function.c_dispatcher
  to   = aws_lambda_function.c_dispatcher[0]
}

resource "aws_lambda_function" "c_dispatcher" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count            = var.enable_cascade ? 1 : 0
  function_name    = "qgi-pipeline-c-dispatcher"
  handler          = "lambda_function.lambda_handler"
  timeout          = 900
  memory_size      = 128
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role
  layers           = local.lambda_defaults.layers

  environment {
    variables = {
      S3_BUCKET             = var.data_lake_bucket_name
      ATHENA_DATABASE       = var.glue_database_name
      COUNTRIES_NAMES_TABLE = "countries"
      SCDIS_TABLE           = "scdis"
      ATHENA_WORKGROUP      = var.athena_workgroup_name
      S3_OUTPUT_LOCATION    = local.s3_output_location
      SQS_QUEUE_URL         = var.queue_c_main_url
      COMPLETION_TABLE      = var.completion_table_name
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Phase 4 — c worker (Cascade/SCDI-exclusive — gated by enable_cascade)
# ---------------------------------------------------------------------------
# moved block: aws_lambda_function.c_worker -> c_worker[0]
moved {
  from = aws_lambda_function.c_worker
  to   = aws_lambda_function.c_worker[0]
}

resource "aws_lambda_function" "c_worker" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count            = var.enable_cascade ? 1 : 0
  function_name    = "qgi-pipeline-c-worker"
  handler          = "lambda_function.lambda_handler"
  timeout          = 900
  memory_size      = 256
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role
  layers           = local.lambda_defaults.layers

  environment {
    variables = {
      S3_BUCKET             = var.data_lake_bucket_name
      ATHENA_DATABASE       = var.glue_database_name
      SCDIS_TABLE           = "scdis"
      COUNTRIES_NAMES_TABLE = "countries"
      ATHENA_WORKGROUP      = var.athena_workgroup_name
      S3_OUTPUT_LOCATION    = local.s3_output_location
      SQS_QUEUE_URL         = var.queue_c_main_url
      COMPLETION_TABLE      = var.completion_table_name
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# moved block: aws_lambda_event_source_mapping.c_worker_sqs -> c_worker_sqs[0]
moved {
  from = aws_lambda_event_source_mapping.c_worker_sqs
  to   = aws_lambda_event_source_mapping.c_worker_sqs[0]
}

resource "aws_lambda_event_source_mapping" "c_worker_sqs" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count                              = var.enable_cascade ? 1 : 0
  event_source_arn                   = var.queue_c_main_arn
  function_name                      = aws_lambda_function.c_worker[0].arn
  batch_size                         = 10
  maximum_batching_window_in_seconds = 5
  enabled                            = true
}

# ---------------------------------------------------------------------------
# Phase 4 — completion checker (Cascade/SCDI-exclusive — gated by enable_cascade)
# ---------------------------------------------------------------------------
# moved block: aws_lambda_function.c_checker -> c_checker[0]
moved {
  from = aws_lambda_function.c_checker
  to   = aws_lambda_function.c_checker[0]
}

resource "aws_lambda_function" "c_checker" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count            = var.enable_cascade ? 1 : 0
  function_name    = "qgi-pipeline-c-checker"
  handler          = "lambda_function.lambda_handler"
  timeout          = 30
  memory_size      = 128
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role
  layers           = local.lambda_defaults.layers

  environment {
    variables = {
      COMPLETION_TABLE = var.completion_table_name
      S3_BUCKET        = var.data_lake_bucket_name
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Phase 4/5 — c DLQ inspector (Cascade/SCDI-exclusive — gated by enable_cascade)
# ---------------------------------------------------------------------------
# moved block: aws_lambda_function.c_dlq_inspector -> c_dlq_inspector[0]
moved {
  from = aws_lambda_function.c_dlq_inspector
  to   = aws_lambda_function.c_dlq_inspector[0]
}

resource "aws_lambda_function" "c_dlq_inspector" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count            = var.enable_cascade ? 1 : 0
  function_name    = "qgi-pipeline-c-dlq-inspector"
  handler          = "lambda_function.lambda_handler"
  timeout          = 900
  memory_size      = 128
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role
  layers           = local.lambda_defaults.layers

  environment {
    variables = {
      DLQ_URL               = var.queue_c_dlq_url
      S3_BUCKET             = var.data_lake_bucket_name
      ATHENA_DATABASE       = var.glue_database_name
      COUNTRIES_NAMES_TABLE = "countries"
      ATHENA_WORKGROUP      = var.athena_workgroup_name
      S3_OUTPUT_LOCATION    = local.s3_output_location
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# moved block: aws_lambda_event_source_mapping.c_dlq_inspector_sqs -> c_dlq_inspector_sqs[0]
moved {
  from = aws_lambda_event_source_mapping.c_dlq_inspector_sqs
  to   = aws_lambda_event_source_mapping.c_dlq_inspector_sqs[0]
}

resource "aws_lambda_event_source_mapping" "c_dlq_inspector_sqs" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count            = var.enable_cascade ? 1 : 0
  event_source_arn = var.queue_c_dlq_arn
  function_name    = aws_lambda_function.c_dlq_inspector[0].arn
  batch_size       = 1
  enabled          = true
}

# ---------------------------------------------------------------------------
# Phase 5 — DLQ scanner (scans all DLQs, sends SNS summary)
# Expanded from prod: prod only scanned a+b DLQs; now includes c.
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "ops_dlq_scanner" {
  function_name    = "qgi-pipeline-ops-dlq-scanner"
  handler          = "lambda_function.lambda_handler"
  timeout          = 900
  memory_size      = 128
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role
  layers           = local.lambda_defaults.layers

  environment {
    variables = {
      # Cross-reference guard #3: include B/C DLQ urls only when enable_cascade=true.
      # compact() strips empty strings that flow through when cascade is off.
      DLQ_URLS = join(",", compact([
        var.queue_a_dlq_url,
        var.enable_cascade ? var.queue_b_dlq_url : "",
        var.enable_cascade ? var.queue_c_dlq_url : "",
      ]))
      SNS_TOPIC_ARN = var.sns_topic_arn
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Phase 5 — Recipe engine (Cascade/SCDI-exclusive — gated by enable_cascade)
# ---------------------------------------------------------------------------
# moved block: aws_lambda_function.recipe_engine -> recipe_engine[0]
moved {
  from = aws_lambda_function.recipe_engine
  to   = aws_lambda_function.recipe_engine[0]
}

resource "aws_lambda_function" "recipe_engine" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count            = var.enable_cascade ? 1 : 0
  function_name    = "qgi-pipeline-recipe-engine"
  handler          = "lambda_function.lambda_handler"
  timeout          = 900
  memory_size      = 1024
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role
  layers           = local.lambda_defaults.layers

  environment {
    variables = {
      S3_BUCKET          = var.data_lake_bucket_name
      ATHENA_DATABASE    = var.glue_database_name
      ATHENA_WORKGROUP   = var.athena_workgroup_name
      S3_OUTPUT_LOCATION = local.s3_output_location
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Phase 5 — Recipe Engine List Formatter (Cascade/SCDI-exclusive — gated by enable_cascade)
#
# Tiny Lambda (~20 lines of real work) that parses the Athena query results
# from the "5b.2. Enumerate country_a_ids" state and pre-generates all
# per-country SQL strings (one CTAS for the smallest-by-pattern-count
# country, and INSERTs for the rest). Does NO Athena execution itself.
# Max wall time: ~10 seconds.
# ---------------------------------------------------------------------------
# moved block: aws_lambda_function.recipe_engine_list_formatter -> recipe_engine_list_formatter[0]
moved {
  from = aws_lambda_function.recipe_engine_list_formatter
  to   = aws_lambda_function.recipe_engine_list_formatter[0]
}

resource "aws_lambda_function" "recipe_engine_list_formatter" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count         = var.enable_cascade ? 1 : 0
  function_name = "qgi-pipeline-recipe-engine-list-formatter"
  handler       = "lambda_function.lambda_handler"
  # timeout 60s → 900s + memory 256MB → 512MB per #533 (smart-chunking,
  # 2026-04-29). The Lambda now (a) runs an Athena enumerate query that
  # scans patterns × events and can take 4-6 min on the 12M-pattern
  # India case, then (b) builds the chunk list with up to ~5K items
  # including pre-baked SQL strings. Discovered when SF v3 + v4 timed
  # out at 60s waiting for the enumerate query. Lambda max is 900s; we
  # use the full max for safety.
  #
  # #739 (2026-05-16): memory 512 → 2048 MB. Pipeline data growth
  # between May 11 and May 16 raised the post-JOIN chunk count from
  # ~5K to ~41K (smart-chunking now emits 40,972 INSERT items across
  # ~200 countries; country 100 alone reports 891M patterns post-JOIN).
  # Each chunk's INSERT SQL is ~6KB → ~245MB of JSON strings, plus
  # Python dict overhead, plus json.dumps peak doubles memory. The
  # first cost-leak verify run OOM'd at Max Memory Used: 510 / 512 MB
  # (99.6%) during the s3.put_object call after smart-chunking
  # completed. 2048 MB gives ~4× headroom and lets json.dumps complete
  # cleanly. Bumped via CLI first (`aws lambda update-function-
  # configuration`) to unblock the test run; TF source updated here so
  # the value persists across future `terraform apply` runs.
  #
  # Structural follow-up (separate ticket): stream insert_items to S3
  # in batches rather than materializing the full list in memory.
  # Would reduce memory pressure back to ~50-100 MB regardless of
  # chunk count. Until then this memory bump is the operating budget.
  timeout          = 900
  memory_size      = 2048
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role
  layers           = local.lambda_defaults.layers

  environment {
    variables = {
      ATHENA_DATABASE    = var.glue_database_name
      ATHENA_WORKGROUP   = var.athena_workgroup_name
      S3_OUTPUT_LOCATION = local.s3_output_location
      # #241 Phase B full-pipeline run (2026-04-20) discovered this was
      # missing: the Lambda writes the ~1.3MB insert-items JSON to S3
      # at ``recipe-engine/insert-items-{run_id}.json`` (exceeds SF's
      # 256KB state payload limit so it can't be inlined). Without
      # S3_BUCKET the put_object was called with Bucket="" which raises
      # ParamValidationError and failed Main SF at state 5b.3.
      S3_BUCKET = var.data_lake_bucket_name
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Phase 5 — Recipe Engine Finalize (Cascade/SCDI-exclusive — gated by enable_cascade)
#
# Post-write Lambda: runs AFTER the Map state has populated all recipe
# partitions. Responsibilities: count/category stats, recipes_normalized
# view (#158 follow-up), convergence view (#133), dashboard JSONs (#146).
# All bounded aggregates on the finished recipes table: ~2-3 min wall time.
# ---------------------------------------------------------------------------
# moved block: aws_lambda_function.recipe_engine_finalize -> recipe_engine_finalize[0]
moved {
  from = aws_lambda_function.recipe_engine_finalize
  to   = aws_lambda_function.recipe_engine_finalize[0]
}

resource "aws_lambda_function" "recipe_engine_finalize" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count            = var.enable_cascade ? 1 : 0
  function_name    = "qgi-pipeline-recipe-engine-finalize"
  handler          = "lambda_function.lambda_handler"
  timeout          = 900
  memory_size      = 1024
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role
  layers           = local.lambda_defaults.layers

  environment {
    variables = {
      S3_BUCKET          = var.data_lake_bucket_name
      ATHENA_DATABASE    = var.glue_database_name
      ATHENA_WORKGROUP   = var.athena_workgroup_name
      S3_BUCKET          = var.data_lake_bucket_name
      S3_OUTPUT_LOCATION = local.s3_output_location
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Phase 5b.7 — Partners Index Generator (Cascade/SCDI-exclusive — gated by enable_cascade)
#
# Reads the finished recipes table and generates a partners-index JSON
# (country-pair co-occurrence rankings) for the frontend.
# ---------------------------------------------------------------------------
# moved block: aws_lambda_function.partners_index_generator -> partners_index_generator[0]
moved {
  from = aws_lambda_function.partners_index_generator
  to   = aws_lambda_function.partners_index_generator[0]
}

resource "aws_lambda_function" "partners_index_generator" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count            = var.enable_cascade ? 1 : 0
  function_name    = "qgi-pipeline-partners-index-generator"
  handler          = "lambda_function.lambda_handler"
  timeout          = 900
  memory_size      = 512
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role
  layers           = local.lambda_defaults.layers

  environment {
    variables = {
      S3_BUCKET        = var.data_lake_bucket_name
      ATHENA_DATABASE  = var.glue_database_name
      ATHENA_WORKGROUP = var.athena_workgroup_name
      # #371 — ATHENA_OUTPUT_LOCATION removed; workgroup
      # QGI-Lambda-Workgroup has EnforceWorkGroupConfiguration=true and
      # supplies its own OutputLocation. Keeping this env var was a
      # latent landmine (same class as #369 Fix 7).
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Phase 5b.8 — Pattern Density Generator (Cascade/SCDI-exclusive — gated by enable_cascade)
#
# Computes per-country pattern density metrics and writes a density JSON
# for use in risk scoring and frontend visualisations.
# ---------------------------------------------------------------------------
# moved block: aws_lambda_function.pattern_density_generator -> pattern_density_generator[0]
moved {
  from = aws_lambda_function.pattern_density_generator
  to   = aws_lambda_function.pattern_density_generator[0]
}

resource "aws_lambda_function" "pattern_density_generator" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count            = var.enable_cascade ? 1 : 0
  function_name    = "qgi-pipeline-pattern-density-generator"
  handler          = "lambda_function.lambda_handler"
  timeout          = 900
  memory_size      = 256
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role
  layers           = local.lambda_defaults.layers

  environment {
    variables = {
      S3_BUCKET        = var.data_lake_bucket_name
      ATHENA_DATABASE  = var.glue_database_name
      ATHENA_WORKGROUP = var.athena_workgroup_name
      # #371 — ATHENA_OUTPUT_LOCATION removed; workgroup
      # QGI-Lambda-Workgroup has EnforceWorkGroupConfiguration=true and
      # supplies its own OutputLocation. Keeping this env var was a
      # latent landmine (same class as #369 Fix 7).
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Phase 5b.9 — Structural Twins Generator (Cascade/SCDI-exclusive — gated by enable_cascade)
#
# Identifies structurally similar country pairs based on shared pattern
# profiles and writes a twins JSON for the frontend analogue feature.
# ---------------------------------------------------------------------------
# moved block: aws_lambda_function.structural_twins_generator -> structural_twins_generator[0]
moved {
  from = aws_lambda_function.structural_twins_generator
  to   = aws_lambda_function.structural_twins_generator[0]
}

resource "aws_lambda_function" "structural_twins_generator" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count            = var.enable_cascade ? 1 : 0
  function_name    = "qgi-pipeline-structural-twins-generator"
  handler          = "lambda_function.lambda_handler"
  timeout          = 900
  memory_size      = 256
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role
  layers           = local.lambda_defaults.layers

  environment {
    variables = {
      S3_BUCKET        = var.data_lake_bucket_name
      ATHENA_DATABASE  = var.glue_database_name
      ATHENA_WORKGROUP = var.athena_workgroup_name
      # #371 — ATHENA_OUTPUT_LOCATION removed; workgroup
      # QGI-Lambda-Workgroup has EnforceWorkGroupConfiguration=true and
      # supplies its own OutputLocation. Keeping this env var was a
      # latent landmine (same class as #369 Fix 7).
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Phase 5b.10 — Pair Windows Generator (Cascade/SCDI-exclusive — gated by enable_cascade)
#
# Queries ALL patterns ordered by (country_a_id, country_b_id, pps DESC),
# takes top 200 windows per pair, and writes one JSON file per predictor
# country to dashboard/pair-windows/{country_a_id}.json.
# ---------------------------------------------------------------------------
# moved block: aws_lambda_function.pair_windows_generator -> pair_windows_generator[0]
moved {
  from = aws_lambda_function.pair_windows_generator
  to   = aws_lambda_function.pair_windows_generator[0]
}

resource "aws_lambda_function" "pair_windows_generator" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count            = var.enable_cascade ? 1 : 0
  function_name    = "qgi-pipeline-pair-windows-generator"
  handler          = "lambda_function.lambda_handler"
  timeout          = 900
  memory_size      = 1024
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role
  layers           = local.lambda_defaults.layers

  environment {
    variables = {
      S3_BUCKET        = var.data_lake_bucket_name
      ATHENA_DATABASE  = var.glue_database_name
      ATHENA_WORKGROUP = var.athena_workgroup_name
      # #371 — ATHENA_OUTPUT_LOCATION removed; workgroup
      # QGI-Lambda-Workgroup has EnforceWorkGroupConfiguration=true and
      # supplies its own OutputLocation. Keeping this env var was a
      # latent landmine (same class as #369 Fix 7).
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Phase 5b.10b — Pair Windows Enumerator (Cascade/SCDI-exclusive — gated by enable_cascade)
#
# AFTER the 5b.10a CTAS has materialised ``pair_windows_staging``,
# this Lambda runs a tiny ``SELECT DISTINCT country_a_id`` query
# and writes the item array to S3 for the 5b.10c Distributed Map.
# Wall time <10s; no risk of Lambda timeout.
#
# Replaces the legacy ``pair_windows_generator`` pattern of running
# a full-table window function in-Lambda (900s cap blocked it at
# ~2B rows during #241 Phase B). Legacy Lambda stays deployed as
# rollback fallback — delete after 2 successful prod runs of the
# new pipeline (see #369 migration plan).
# ---------------------------------------------------------------------------
# moved block: aws_lambda_function.pair_windows_enumerator -> pair_windows_enumerator[0]
moved {
  from = aws_lambda_function.pair_windows_enumerator
  to   = aws_lambda_function.pair_windows_enumerator[0]
}

resource "aws_lambda_function" "pair_windows_enumerator" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count            = var.enable_cascade ? 1 : 0
  function_name    = "qgi-pipeline-pair-windows-enumerator"
  handler          = "lambda_function.lambda_handler"
  timeout          = 60
  memory_size      = 256
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role
  layers           = local.lambda_defaults.layers

  environment {
    variables = {
      S3_BUCKET        = var.data_lake_bucket_name
      ATHENA_DATABASE  = var.glue_database_name
      ATHENA_WORKGROUP = var.athena_workgroup_name
      # #371 — ATHENA_OUTPUT_LOCATION removed; workgroup
      # QGI-Lambda-Workgroup has EnforceWorkGroupConfiguration=true and
      # supplies its own OutputLocation. Keeping this env var was a
      # latent landmine (same class as #369 Fix 7).
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Phase 5b.10c child — Pair Windows Writer (Cascade/SCDI-exclusive — gated by enable_cascade)
#
# Distributed-Map child. Reads ONE country_a_id's partition from
# ``pair_windows_staging`` (bounded ~42K rows), builds the JSON
# blob, writes ``dashboard/pair-windows/{country_a_id}.json``.
# Wall time ~5-10s per invocation. With MaxConcurrency=20 across
# 214 countries, the full Map completes in ~2 min.
# ---------------------------------------------------------------------------
# moved block: aws_lambda_function.pair_windows_writer -> pair_windows_writer[0]
moved {
  from = aws_lambda_function.pair_windows_writer
  to   = aws_lambda_function.pair_windows_writer[0]
}

resource "aws_lambda_function" "pair_windows_writer" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count            = var.enable_cascade ? 1 : 0
  function_name    = "qgi-pipeline-pair-windows-writer"
  handler          = "lambda_function.lambda_handler"
  timeout          = 300
  memory_size      = 512
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role
  layers           = local.lambda_defaults.layers

  environment {
    variables = {
      ATHENA_DATABASE  = var.glue_database_name
      ATHENA_WORKGROUP = var.athena_workgroup_name
      # #371 — ATHENA_OUTPUT_LOCATION removed; workgroup enforces its own
      # OutputLocation. See #369 Fix 7 for the failure class this avoids.
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# #175: Indicator manifest reader (decoupled pipeline)
#
# Reads the fetch manifest from S3 and returns it for the Main SF.
# ~35 LOC, no external dependencies, <1 second wall time.
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "indicator_manifest_reader" {
  function_name    = "qgi-pipeline-indicator-manifest-reader"
  handler          = "lambda_function.lambda_handler"
  timeout          = 30
  memory_size      = 128
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role

  environment {
    variables = {
      S3_BUCKET    = var.data_lake_bucket_name
      MANIFEST_KEY = "indicator-freshness/latest-fetch-manifest.json"
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Utility — Batch job terminator (Step Function + Lambda fan-out)
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "batch_job_terminator" {
  function_name    = "qgi-batch-job-terminator"
  handler          = "lambda_function.lambda_handler"
  timeout          = 900
  memory_size      = 512
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = local.lambda_defaults.role
  layers           = local.lambda_defaults.layers

  environment {
    variables = {
      # Cross-reference guard #5: the cost kill-switch watches the Phase B SCDI
      # queue when cascade is ON (staging — UNCHANGED), and the TE recipe-fleet
      # queue when cascade is OFF (QA), where the Phase B queue does not exist.
      BATCH_JOB_QUEUE = var.enable_cascade ? "qgi-pipeline-b-high-priority-queue" : "qgi-recipe-fleet-queue"
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

resource "aws_sfn_state_machine" "batch_job_terminator" {
  name     = "qgi-batch-job-terminator"
  role_arn = var.stepfunctions_role_arn

  definition = jsonencode({
    Comment = "Kill all active AWS Batch jobs. List → S3 chunks → parallel Map kill → Report."
    StartAt = "List Active Jobs"
    States = {

      "List Active Jobs" = {
        Type     = "Task"
        Resource = aws_lambda_function.batch_job_terminator.arn
        Parameters = {
          mode       = "list"
          reason     = "Terminated by Step Function."
          bucket     = var.data_lake_bucket_name
          "run_id.$" = "$$.Execution.Name"
        }
        ResultPath = "$.listing"
        Next       = "Any Jobs?"
      }

      "Any Jobs?" = {
        Type = "Choice"
        Choices = [{
          Variable           = "$.listing.total_jobs"
          NumericGreaterThan = 0
          Next               = "Kill All Chunks"
        }]
        Default = "No Jobs Found"
      }

      "No Jobs Found" = {
        Type    = "Succeed"
        Comment = "Nothing to kill."
      }

      "Kill All Chunks" = {
        Type           = "Map"
        ItemsPath      = "$.listing.chunk_indices"
        MaxConcurrency = 10
        ItemProcessor = {
          ProcessorConfig = {
            Mode = "INLINE"
          }
          StartAt = "Kill Chunk"
          States = {
            "Kill Chunk" = {
              Type     = "Task"
              Resource = aws_lambda_function.batch_job_terminator.arn
              Parameters = {
                mode            = "kill"
                reason          = "Terminated by Step Function."
                bucket          = var.data_lake_bucket_name
                "run_id.$"      = "$$.Execution.Name"
                "chunk_index.$" = "$.chunk_index"
              }
              End = true
              Retry = [{
                ErrorEquals     = ["States.ALL"]
                IntervalSeconds = 10
                MaxAttempts     = 3
                BackoffRate     = 2
              }]
            }
          }
        }
        ResultPath = "$.kill_results"
        Next       = "Report"
      }

      "Report" = {
        Type     = "Task"
        Resource = aws_lambda_function.batch_job_terminator.arn
        Parameters = {
          mode = "report"
        }
        ResultPath = "$.report"
        Next       = "Done"
      }

      "Done" = {
        Type = "Succeed"
      }
    }
  })

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Step Functions — Fetch SF (#175: decoupled indicator data refresher)
#
# Standalone SF that fetches indicator data from WB/FAOSTAT/ILOSTAT,
# writes parquets to S3, and produces a manifest JSON for the Main SF.
# Runs monthly via EventBridge or manually. Does NOT process SCDIs/patterns.
# ---------------------------------------------------------------------------
resource "aws_sfn_state_machine" "fetch_pipeline" {
  name     = "qgi-indicator-data-refresher"
  role_arn = var.stepfunctions_role_arn

  definition = jsonencode({
    Comment = "QGI Fetch Pipeline (#175) — fetches indicator data, writes manifest"
    StartAt = "F.0 Fetch XLSX"
    States = {
      "F.0 Fetch XLSX" = {
        Type       = "Task"
        Resource   = aws_lambda_function.a_sheet_fetcher.arn
        ResultPath = "$.fetcher_output"
        Retry      = local.lambda_retry
        Next       = "F.1 Dispatch Fargate"
      }

      "F.1 Dispatch Fargate" = {
        Type     = "Task"
        Resource = aws_lambda_function.a_batch_dispatcher.arn
        Parameters = {
          "run_id.$" = "$$.Execution.Name"
        }
        ResultPath = "$.dispatch_output"
        Retry      = local.lambda_retry
        Next       = "F.2 Wait 2m"
      }

      "F.2 Wait 2m" = {
        Type    = "Wait"
        Seconds = 120
        Next    = "F.3 Check Counter"
      }

      "F.3 Check Counter" = {
        Type     = "Task"
        Resource = aws_lambda_function.a_batch_checker.arn
        Parameters = {
          "run_id.$"            = "$$.Execution.Name"
          "phase1_started_at.$" = "$.dispatch_output.phase1_started_at"
          "total.$"             = "$.dispatch_output.total"
        }
        ResultPath = "$.check"
        Retry      = local.lambda_retry
        Next       = "F.4 Fetchers Done?"
      }

      "F.4 Fetchers Done?" = {
        Type = "Choice"
        Choices = [{
          Variable      = "$.check.done"
          BooleanEquals = true
          Next          = "F.5 Report"
        }]
        Default = "F.2 Wait 2m"
      }

      # Reporter now writes manifest to S3 (#175) so the Main SF
      # can read it via the manifest-reader Lambda.
      "F.5 Report" = {
        Type     = "Task"
        Resource = aws_lambda_function.a_reporter.arn
        Parameters = {
          "run_id.$"          = "$$.Execution.Name"
          "deadman_expired.$" = "$.check.deadman_expired"
          "total.$"           = "$.check.total"
          "done.$"            = "$.check.done"
          "pending.$"         = "$.check.pending"
        }
        ResultPath = "$.reporter_result"
        Retry      = local.lambda_retry
        End        = true
      }
    }
  })

  tags = var.tags
}

# ---------------------------------------------------------------------------
# EventBridge Scheduler — Fetch SF monthly (#175)
# DISABLED by default. Enable after first manual verification.
# ---------------------------------------------------------------------------
resource "aws_scheduler_schedule" "fetch_monthly" {
  name       = "qgi-indicator-data-refresher-1st"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = "cron(0 6 1 * ? *)"
  schedule_expression_timezone = "Europe/Berlin"

  state = "DISABLED"

  target {
    arn      = aws_sfn_state_machine.fetch_pipeline.arn
    role_arn = var.eventbridge_scheduler_role_arn
  }
}

# ---------------------------------------------------------------------------
# Step Functions — Main cascade pipeline state machine
# (Cascade/SCDI-exclusive — gated by enable_cascade)
#
# Changes vs production:
# - Phase 3: Glue crawler replaced with MSCK REPAIR TABLE scdis (issue #66)
# - Phase 4 MSCK uses QGI-Lambda-Workgroup (prod used hardcoded 'primary')
# - All ARNs are environment-specific (no management account hardcoding)
# ---------------------------------------------------------------------------
# moved block: aws_sfn_state_machine.pipeline -> pipeline[0]
moved {
  from = aws_sfn_state_machine.pipeline
  to   = aws_sfn_state_machine.pipeline[0]
}

resource "aws_sfn_state_machine" "pipeline" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count    = var.enable_cascade ? 1 : 0
  name     = "qgi-indicator-monthly-updater"
  role_arn = var.stepfunctions_role_arn

  definition = jsonencode({
    Comment = "QGI Monthly Pipeline — stages 0-6"
    # TimeoutSeconds = 14400 (4h) per qgi-aws-tf#805 + cost-incident-2026-05-16
    # post-mortem. Historic full bake completes <4h (#241, #533); 17h is
    # pathological. A timed-out execution is much cheaper to restart than
    # the $139 burn of the 2026-05-16 incident.
    TimeoutSeconds = 14400
    StartAt        = "0. Janitor"
    States = {
      "0. Janitor" = {
        Type       = "Task"
        Resource   = aws_lambda_function.ops_janitor.arn
        ResultPath = "$.janitor_output"
        Retry      = local.lambda_retry
        Next       = "Route by Mode"
      }

      # -----------------------------------------------------------------
      # #175: Mode routing — decoupled pipeline supports four run modes.
      #
      # Input: {"mode": "full"|"recipes_only"|"post_recipes"|"dashboards_only",
      #         "force_full_run": bool (optional, default false)}
      #
      # "full" (default): read manifest → completer → SCDI → patterns → recipes → report
      # "recipes_only":   skip phases 1-4, jump to 5b.1 (drop + rebuild recipes table)
      # "post_recipes":   skip everything up to 5b.5 — assume the recipes table is
      #                   already fully populated (e.g., previous run died at 5b.7
      #                   stub Lambda but 5b.5 Map completed). Starts at 5b.6 Finalize
      #                   and chains naturally through 5b.7 → 5b.8 → 5b.9 → 5b.10 →
      #                   5c MSCK → 6 Ops Report → Complete. Total wall time ~3-5 min.
      #                   Added 2026-04-20 after #241 Phase B cycle burned 70-min
      #                   full re-runs to resume past 5b.5.
      # "dashboards_only": legacy shortcut — just runs 5b.6 Finalize then 6 Ops Report,
      #                   skipping 5b.7-10 generators + 5c MSCK. Kept for back-compat
      #                   but most resume scenarios want "post_recipes" instead.
      # -----------------------------------------------------------------
      "Route by Mode" = {
        Type = "Choice"
        Choices = [
          {
            Variable     = "$.mode"
            StringEquals = "recipes_only"
            Next         = "5b.1. Drop Recipes Table"
          },
          {
            Variable     = "$.mode"
            StringEquals = "post_recipes"
            Next         = "post_recipes. Inject Defaults"
          },
          {
            Variable     = "$.mode"
            StringEquals = "dashboards_only"
            Next         = "Finalize Dashboards"
          }
        ]
        Default = "1a. Fetch Indicators XLSX"
      }

      # post_recipes: synthesize the $.recipe_list structure that 5b.3
      # List Formatter would normally produce, so 5b.6 Finalize finds
      # its expected input ($.recipe_list.partitions_total). The
      # Finalize Lambda only uses this value for logging, so any
      # placeholder works — it does not drive control flow.
      "post_recipes. Inject Defaults" = {
        Type = "Pass"
        Result = {
          partitions_total = "post_recipes_resume"
        }
        ResultPath = "$.recipe_list"
        Next       = "5b.6. Finalize"
      }

      # dashboards_only: invoke finalize directly, skip everything else
      "Finalize Dashboards" = {
        Type     = "Task"
        Resource = aws_lambda_function.recipe_engine_finalize[0].arn
        Parameters = {
          "run_id.$" = "$$.Execution.Name"
        }
        ResultPath = "$.recipe_finalize_output"
        Retry      = local.lambda_retry
        Next       = "6. Ops Report"
      }

      "1a. Fetch Indicators XLSX" = {
        Type       = "Task"
        Resource   = aws_lambda_function.a_sheet_fetcher.arn
        ResultPath = "$.fetcher_output"
        Retry      = local.lambda_retry
        Next       = "1-manifest. Read Fetch Manifest"
      }

      # #175: Reads the fetch manifest from S3 (written by the separate
      # Fetch SF qgi-indicator-data-refresher). Returns updated_ids +
      # all_indicator_ids. If force_full_run=true, overrides updated_ids
      # with all indicators for a full recompute.
      #
      # Output goes to $.reporter_result so all downstream states (1g,
      # 1h, 2a) work unchanged — they already reference
      # $.reporter_result.updated_ids and $.reporter_result.updated_count.
      "1-manifest. Read Fetch Manifest" = {
        Type       = "Task"
        Resource   = aws_lambda_function.indicator_manifest_reader.arn
        InputPath  = "$"
        ResultPath = "$.reporter_result"
        Retry      = local.lambda_retry
        Next       = "1g. Complete Indicator Series"
      }

      # #157: pass updated_ids into the completer so it only mirrors
      # changed indicators to qgi-indicator-values DDB.
      "1g. Complete Indicator Series" = {
        Type     = "Task"
        Resource = aws_lambda_function.a_completer.arn
        Parameters = {
          "run_id.$"      = "$$.Execution.Name"
          "updated_ids.$" = "$.reporter_result.updated_ids"
        }
        ResultPath = "$.completer_result"
        Retry      = local.lambda_retry
        Next       = "1h. Updates Found?"
      }

      "1h. Updates Found?" = {
        Type = "Choice"
        Choices = [{
          Variable           = "$.reporter_result.updated_count"
          NumericGreaterThan = 0
          Next               = "2a. Dispatch SCDI Batch"
        }]
        Default = "6. Ops Report"
      }

      "2a. Dispatch SCDI Batch" = {
        Type     = "Task"
        Resource = aws_lambda_function.b_orchestrator[0].arn
        Parameters = {
          mode              = var.batch_invoke_mode
          "indicator_ids.$" = "$.reporter_result.updated_ids"
        }
        ResultPath = "$.trigger_b_output"
        Retry      = local.lambda_retry
        Next       = "2b. Wait 2m (SCDI Poll)"
      }

      # #167: replaced 30m hard wait with 2m poll loop (matches Phase 1 pattern).
      # Saves 20+ min of dead time on small test runs (3-indicator runs finish
      # in ~5 min but the old 30m wait sat idle). On full 60-indicator runs,
      # Batch takes ~20-30 min so the poll loop checks ~15 times and exits
      # within a minute of completion instead of waiting for the next 30m tick.
      "2b. Wait 2m (SCDI Poll)" = {
        Type    = "Wait"
        Seconds = 120
        Next    = "2c. Check SCDI Batch"
      }

      "2c. Check SCDI Batch" = {
        Type       = "Task"
        Resource   = aws_lambda_function.ops_batch_checker[0].arn
        ResultPath = "$.batch_status"
        Retry      = local.lambda_retry
        Next       = "2d. SCDI Done?"
      }

      "2d. SCDI Done?" = {
        Type = "Choice"
        Choices = [{
          Variable           = "$.batch_status.jobs_running"
          NumericGreaterThan = 0
          Next               = "2b. Wait 2m (SCDI Poll)"
        }]
        Default = "3. Athena MSCK scdis"
      }

      # Phase 3: replaced Glue crawler with MSCK REPAIR TABLE scdis (issue #66)
      # Faster, cheaper (~$0), and avoids Glue crawler $0.44/DPU-hour cost.
      "3. Athena MSCK scdis" = {
        Type     = "Task"
        Resource = "arn:aws:states:::athena:startQueryExecution.sync"
        Parameters = {
          QueryString = "MSCK REPAIR TABLE `${var.glue_database_name}`.`scdis`;"
          WorkGroup   = var.athena_workgroup_name
          QueryExecutionContext = {
            Database = var.glue_database_name
          }
          ResultConfiguration = {
            OutputLocation = local.s3_output_location
          }
        }
        ResultPath = "$.repair_scdis_output"
        Next       = "4a. Dispatch Pattern Synth"
      }

      "4a. Dispatch Pattern Synth" = {
        Type     = "Task"
        Resource = aws_lambda_function.c_dispatcher[0].arn
        Parameters = {
          action     = "start"
          "run_id.$" = "$$.Execution.Name"
        }
        ResultPath = "$.dispatch_c_output"
        Retry      = local.lambda_retry
        Next       = "4b. Wait 30s (Pattern Poll)"
      }

      "4b. Wait 30s (Pattern Poll)" = {
        Type    = "Wait"
        Seconds = 30
        Next    = "4c. Check Pattern Counter"
      }

      "4c. Check Pattern Counter" = {
        Type     = "Task"
        Resource = aws_lambda_function.c_checker[0].arn
        Parameters = {
          "run_id.$"   = "$$.Execution.Name"
          "expected.$" = "$.dispatch_c_output.dispatched_count"
        }
        ResultPath = "$.c_check"
        Retry      = local.lambda_retry
        Next       = "4d. Patterns Done?"
      }

      "4d. Patterns Done?" = {
        Type = "Choice"
        Choices = [{
          Variable      = "$.c_check.done"
          BooleanEquals = true
          Next          = "4e. Athena MSCK patterns"
        }]
        Default = "4b. Wait 30s (Pattern Poll)"
      }

      "4e. Athena MSCK patterns" = {
        Type     = "Task"
        Resource = "arn:aws:states:::athena:startQueryExecution.sync"
        Parameters = {
          QueryString = "MSCK REPAIR TABLE `${var.glue_database_name}`.`patterns`;"
          WorkGroup   = var.athena_workgroup_name
          QueryExecutionContext = {
            Database = var.glue_database_name
          }
          ResultConfiguration = {
            OutputLocation = local.s3_output_location
          }
        }
        ResultPath = "$.repair_patterns_output"
        Next       = "5a. Athena MSCK events"
      }

      # Phase 5: Recipe engine — match patterns against events (D4/D5)
      "5a. Athena MSCK events" = {
        Type     = "Task"
        Resource = "arn:aws:states:::athena:startQueryExecution.sync"
        Parameters = {
          QueryString = "MSCK REPAIR TABLE `${var.glue_database_name}`.`events`;"
          WorkGroup   = var.athena_workgroup_name
          QueryExecutionContext = {
            Database = var.glue_database_name
          }
          ResultConfiguration = {
            OutputLocation = local.s3_output_location
          }
        }
        ResultPath = "$.repair_events_output"
        Next       = "5b.1. Drop Recipes Table"
      }

      # -----------------------------------------------------------------
      # Phase 5b: Recipe Engine (#162 Layer 2)
      #
      # Replaces the single monolithic recipe-engine Lambda that timed out
      # at 900s with a 6-state chain. Athena queries now run via SF native
      # .sync integration (no Lambda 15-min ceiling). Per-country INSERTs
      # fan out via Map state at concurrency 20.
      #
      # Flow:
      #   5b.1 DROP TABLE recipes     (Athena .sync)
      #   5b.2 Enumerate country_ids  (Athena .sync, sorted by pattern count)
      #   5b.3 List Formatter Lambda  (parse results, pre-gen SQL strings)
      #   5b.3a Create External Table  (Athena .sync, DDL from Lambda — #622)
      #   5b.4 Seed INSERT             (Athena .sync, INSERT INTO smallest chunk)
      #   5b.5 Map per-country INSERT (Athena .sync × 80, idempotent)
      #   5b.6 Finalize Lambda        (views + dashboard JSONs)
      # -----------------------------------------------------------------

      "5b.1. Drop Recipes Table" = {
        Type     = "Task"
        Resource = "arn:aws:states:::athena:startQueryExecution.sync"
        Parameters = {
          QueryString           = "DROP TABLE IF EXISTS `${var.glue_database_name}`.`recipes`;"
          WorkGroup             = var.athena_workgroup_name
          QueryExecutionContext = { Database = var.glue_database_name }
          ResultConfiguration   = { OutputLocation = local.s3_output_location }
        }
        ResultPath = "$.drop_recipes_output"
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 5
          MaxAttempts     = 2
          BackoffRate     = 2
        }]
        # 5b.2 removed: Athena .sync doesn't support plain SELECT.
        # The enumerate query now runs inside 5b.3 (list-formatter Lambda).
        Next = "5b.3. List Formatter"
      }

      "5b.3. List Formatter" = {
        Type     = "Task"
        Resource = aws_lambda_function.recipe_engine_list_formatter[0].arn
        Parameters = {
          "run_id.$" = "$$.Execution.Name"
        }
        ResultPath = "$.recipe_list"
        Retry      = local.lambda_retry
        # #622 (2026-05-16) — Lambda now emits $.recipe_list.ddl_sql
        # alongside seed_sql. The new state 5b.3a runs the DDL to
        # create the recipes EXTERNAL TABLE at the stable prefix
        # BEFORE the seed INSERT writes to it.
        Next = "5b.3a. Create External Table"
      }

      # ---------------------------------------------------------------
      # 5b.3a (#622, 2026-05-16): Create EXTERNAL TABLE recipes at the
      # stable S3 prefix s3://{bucket}/pipeline-recipe-engine/output/recipes/.
      #
      # WHY THIS STATE EXISTS
      # ---------------------
      # Pre-fix: 5b.4 ran `CREATE TABLE recipes AS SELECT ...` (CTAS),
      # which lands data at `query_results/tables/<uuid>/` with 1-day
      # S3 expiry. Every Lambda re-run cycled DROP -> CTAS -> expire ->
      # re-CTAS, dominating the May 2-5 cost spike (~$13/day).
      #
      # Post-fix: this state CREATEs the table at the stable prefix
      # FIRST, then 5b.4 (now "Seed INSERT") writes the seed chunk
      # via INSERT INTO. The same stable prefix is used by the Map
      # state INSERTs in 5b.5 — so every partition lives under one
      # known location with NO 1-day expiry.
      #
      # SCHEMA AUTHORITY
      # ----------------
      # The 27-column DDL is generated INSIDE the Lambda
      # (lambdas/pipeline-recipe-engine-list-formatter/lambda_function.py
      # build_external_table_ddl) and emitted as $.recipe_list.ddl_sql.
      # Co-locating DDL with the SELECT-list eliminates cross-repo
      # schema-drift risk — a vitest-style regression guard
      # (test_ddl_select_column_parity) catches any divergence at
      # test time.
      #
      # IDEMPOTENCY
      # -----------
      # DDL uses `CREATE EXTERNAL TABLE IF NOT EXISTS`. 5b.1 DROPs the
      # table before this state runs; on a partial-retry the IF NOT
      # EXISTS handles the case where this state succeeded but a later
      # state failed — re-running this is harmless.
      "5b.3a. Create External Table" = {
        Type     = "Task"
        Resource = "arn:aws:states:::athena:startQueryExecution.sync"
        Parameters = {
          "QueryString.$"       = "$.recipe_list.ddl_sql"
          WorkGroup             = var.athena_workgroup_name
          QueryExecutionContext = { Database = var.glue_database_name }
          ResultConfiguration   = { OutputLocation = local.s3_output_location }
        }
        ResultPath = "$.create_external_table_output"
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 5
          MaxAttempts     = 2
          BackoffRate     = 2
        }]
        Next = "5b.4. Seed INSERT"
      }

      # #622 (2026-05-16): renamed from "5b.4. Seed CTAS". The SQL
      # emitted by the Lambda's $.recipe_list.seed_sql now contains
      # INSERT INTO (mode='insert') instead of CREATE TABLE AS SELECT.
      # State name updated to reflect actual behavior.
      "5b.4. Seed INSERT" = {
        Type     = "Task"
        Resource = "arn:aws:states:::athena:startQueryExecution.sync"
        Parameters = {
          "QueryString.$"       = "$.recipe_list.seed_sql"
          WorkGroup             = var.athena_workgroup_name
          QueryExecutionContext = { Database = var.glue_database_name }
          ResultConfiguration   = { OutputLocation = local.s3_output_location }
        }
        # ResultPath kept as $.seed_ctas_output for backward-compat
        # with any downstream consumer/log query that grep'd for that
        # key. Comment marks the historical name.
        ResultPath = "$.seed_ctas_output"
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 10
          MaxAttempts     = 1
          BackoffRate     = 1
        }]
        Next = "5b.5. Per-Country INSERTs"
      }

      "5b.5. Per-Country INSERTs" = {
        Type = "Map"
        # MaxConcurrency 80 → 40 per qgi-aws-tf#805 (cost-incident-2026-05-16).
        # Prior history: 20 → 80 per #533 (smart-chunking, 2026-04-29). The
        # 2026-05-16 incident showed that even with per-query 50 GB caps on
        # QGI-Lambda-Workgroup, 80-way fanout × ~3,000 chunks = 11.17 TB
        # aggregate scan and 17.5h wall-clock. Halving to 40 doubles wall
        # time but halves peak Athena DML pressure + halves the cost rate.
        # Still well under the 150-concurrent-DML account quota; leaves
        # ~110 headroom for enumerate queries, retries, ad-hoc Athena.
        MaxConcurrency = 40
        ItemReader = {
          Resource = "arn:aws:states:::s3:getObject"
          ReaderConfig = {
            InputType = "JSON"
          }
          Parameters = {
            "Bucket.$" = "$.recipe_list.insert_items_bucket"
            "Key.$"    = "$.recipe_list.insert_items_key"
          }
        }
        ItemProcessor = {
          ProcessorConfig = {
            Mode          = "DISTRIBUTED"
            ExecutionType = "STANDARD"
          }
          StartAt = "Drop Partition"
          States = {
            "Drop Partition" = {
              Type     = "Task"
              Resource = "arn:aws:states:::athena:startQueryExecution.sync"
              Parameters = {
                "QueryString.$"       = "$.drop_partition_sql"
                WorkGroup             = var.athena_workgroup_name
                QueryExecutionContext = { Database = var.glue_database_name }
                ResultConfiguration   = { OutputLocation = local.s3_output_location }
              }
              ResultPath = "$.drop_output"
              Retry = [{
                ErrorEquals     = ["States.ALL"]
                IntervalSeconds = 5
                MaxAttempts     = 2
                BackoffRate     = 2
              }]
              Next = "Run INSERT"
            }
            "Run INSERT" = {
              Type     = "Task"
              Resource = "arn:aws:states:::athena:startQueryExecution.sync"
              Parameters = {
                "QueryString.$"       = "$.insert_sql"
                WorkGroup             = var.athena_workgroup_name
                QueryExecutionContext = { Database = var.glue_database_name }
                ResultConfiguration   = { OutputLocation = local.s3_output_location }
              }
              ResultPath = "$.insert_output"
              Retry = [{
                ErrorEquals     = ["States.ALL"]
                IntervalSeconds = 10
                MaxAttempts     = 2
                BackoffRate     = 2
              }]
              End = true
            }
          }
        }
        # #162 review issue 3: ToleratedFailurePercentage 0 means any
        # single per-country failure fails the whole Map immediately.
        # Zombie queries from in-flight iterations will keep running on
        # Athena (SF doesn't cancel them). Acceptable: they'll finish
        # harmlessly; the next pipeline run's DROP TABLE cleans up.
        # A cleanup Lambda (Catch → StopQueryExecution on survivors)
        # can be added later if the zombie cost is material.
        ToleratedFailurePercentage = 0
        # #241 Phase B full-pipeline run (2026-04-20): the default
        # Map ResultPath of "$.map_results" aggregates all 214 per-
        # country iteration outputs (each containing the full Athena
        # QueryExecution objects from Drop Partition + Run INSERT,
        # ~2-5KB per iteration × 214 × 2 outputs ≈ 1-2MB) into the
        # SF state payload, which exceeds the 256KB service limit.
        # Downstream 5b.6. Finalize does not read these per-country
        # outputs (only uses $.recipe_list.partitions_total). Drop
        # them via ResultPath: null so the payload stays bounded.
        ResultPath = null
        Next       = "5b.6. Finalize"
      }

      "5b.6. Finalize" = {
        Type     = "Task"
        Resource = aws_lambda_function.recipe_engine_finalize[0].arn
        Parameters = {
          "run_id.$"           = "$$.Execution.Name"
          "partitions_total.$" = "$.recipe_list.partitions_total"
        }
        ResultPath = "$.recipe_finalize_output"
        Retry      = local.lambda_retry
        Next       = "5b.7. Generate Partners Index"
      }

      "5b.7. Generate Partners Index" = {
        Type     = "Task"
        Resource = aws_lambda_function.partners_index_generator[0].arn
        Parameters = {
          "run_id.$" = "$$.Execution.Name"
        }
        ResultPath = "$.partners_index_output"
        Retry      = local.lambda_retry
        Next       = "5b.8. Generate Pattern Density"
      }

      "5b.8. Generate Pattern Density" = {
        Type     = "Task"
        Resource = aws_lambda_function.pattern_density_generator[0].arn
        Parameters = {
          "run_id.$" = "$$.Execution.Name"
        }
        ResultPath = "$.pattern_density_output"
        Retry      = local.lambda_retry
        Next       = "5b.9. Generate Structural Twins"
      }

      "5b.9. Generate Structural Twins" = {
        Type     = "Task"
        Resource = aws_lambda_function.structural_twins_generator[0].arn
        Parameters = {
          "run_id.$" = "$$.Execution.Name"
        }
        ResultPath = "$.structural_twins_output"
        Retry      = local.lambda_retry
        Next       = "5b.10a-drop. Drop Staging Table"
      }

      # #369: Pair windows refactor — replaces the 900s-capped Lambda with
      # a CTAS + Enumerate + Distributed-Map flow. See the ticket body
      # for the full design rationale. The legacy pair_windows_generator
      # Lambda remains deployed (rollback fallback) but is not referenced
      # by the SF any more.
      "5b.10a-drop. Drop Staging Table" = {
        Type     = "Task"
        Resource = "arn:aws:states:::athena:startQueryExecution.sync"
        Parameters = {
          QueryString           = "DROP TABLE IF EXISTS ${var.glue_database_name}.pair_windows_staging"
          WorkGroup             = var.athena_workgroup_name
          QueryExecutionContext = { Database = var.glue_database_name }
          ResultConfiguration   = { OutputLocation = local.s3_output_location }
        }
        ResultPath = "$.pair_windows_drop_output"
        Next       = "5b.10a. Pair Windows CTAS"
      }

      "5b.10a. Pair Windows CTAS" = {
        Type     = "Task"
        Resource = "arn:aws:states:::athena:startQueryExecution.sync"
        Parameters = {
          # NOTE 1: no ``external_location``. QGI-Lambda-Workgroup has
          # EnforceWorkGroupConfiguration=true which rejects CTAS
          # submissions that set their own output location. Let Athena
          # write the staging table into the workgroup's default
          # location (same as 5b.4 Seed INSERT for the recipes table —
          # post-#622 — though that one INSERTs into a stable-prefix
          # EXTERNAL TABLE so query_results doesn't accumulate uuids).
          #
          # NOTE 2: no ``partitioned_by`` either. Athena's Hive writer
          # caps at 100 open partitions per CTAS; we have 214 countries.
          # Writing partitioned hit HIVE_TOO_MANY_OPEN_PARTITIONS. Post-
          # filter (top-200 per pair) the staging table is small —
          # ~9M rows / ~200MB Parquet — so Map children's full-scan
          # WHERE country_a_id = X queries run in ~2-3s each regardless.
          # Idempotency handled by 5b.10a-drop before CREATE.
          QueryString = join("\n", [
            "CREATE TABLE ${var.glue_database_name}.pair_windows_staging",
            "WITH (",
            "  format = 'PARQUET',",
            "  write_compression = 'SNAPPY'",
            ") AS",
            "SELECT country_a_id, country_b_id, length, start_year_a, start_year_b,",
            "       indicator_count, avg_correlation, pattern_power_score",
            "FROM (",
            "  SELECT *,",
            "         ROW_NUMBER() OVER (",
            "           PARTITION BY country_a_id, country_b_id",
            "           ORDER BY pattern_power_score DESC",
            "         ) AS rn",
            "  FROM ${var.glue_database_name}.patterns",
            ")",
            "WHERE rn <= 200",
          ])
          WorkGroup             = var.athena_workgroup_name
          QueryExecutionContext = { Database = var.glue_database_name }
          ResultConfiguration   = { OutputLocation = local.s3_output_location }
        }
        ResultPath = "$.pair_windows_ctas_output"
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 30
          MaxAttempts     = 1
          BackoffRate     = 1
        }]
        Next = "5b.10b. Enumerate Country A IDs"
      }

      "5b.10b. Enumerate Country A IDs" = {
        Type     = "Task"
        Resource = aws_lambda_function.pair_windows_enumerator[0].arn
        Parameters = {
          "run_id.$" = "$$.Execution.Name"
        }
        ResultPath = "$.pair_windows_enumerate"
        Retry      = local.lambda_retry
        Next       = "5b.10c. Per-Country Pair Windows"
      }

      "5b.10c. Per-Country Pair Windows" = {
        Type           = "Map"
        MaxConcurrency = 20
        ItemReader = {
          Resource     = "arn:aws:states:::s3:getObject"
          ReaderConfig = { InputType = "JSON" }
          Parameters = {
            "Bucket.$" = "$.pair_windows_enumerate.items_bucket"
            "Key.$"    = "$.pair_windows_enumerate.items_key"
          }
        }
        ItemProcessor = {
          ProcessorConfig = {
            Mode          = "DISTRIBUTED"
            ExecutionType = "STANDARD"
          }
          StartAt = "Write Pair Windows JSON"
          States = {
            "Write Pair Windows JSON" = {
              Type     = "Task"
              Resource = aws_lambda_function.pair_windows_writer[0].arn
              Retry = [{
                ErrorEquals     = ["States.ALL"]
                IntervalSeconds = 10
                MaxAttempts     = 2
                BackoffRate     = 2
              }]
              End = true
            }
          }
        }
        ToleratedFailurePercentage = 0
        # Drop aggregated children output — same lesson as 5b.5 (256KB cap).
        ResultPath = null
        Next       = "5c. Athena MSCK recipes"
      }

      "5c. Athena MSCK recipes" = {
        Type     = "Task"
        Resource = "arn:aws:states:::athena:startQueryExecution.sync"
        Parameters = {
          QueryString = "MSCK REPAIR TABLE `${var.glue_database_name}`.`recipes`;"
          WorkGroup   = var.athena_workgroup_name
          QueryExecutionContext = {
            Database = var.glue_database_name
          }
          ResultConfiguration = {
            OutputLocation = local.s3_output_location
          }
        }
        ResultPath = "$.repair_recipes_output"
        Next       = "6. Ops Report"
      }

      "6. Ops Report" = {
        Type       = "Task"
        Resource   = aws_lambda_function.ops_dlq_scanner.arn
        ResultPath = "$.dlq_report"
        Retry      = local.lambda_retry
        Next       = "Complete"
      }

      "Complete" = {
        Type = "Succeed"
      }
    }
  })

  tags = var.tags
}

# ---------------------------------------------------------------------------
# EventBridge Scheduler — Main cascade SFN (Cascade/SCDI-exclusive — gated by enable_cascade)
# DISABLED by default in all environments.
# Enable manually or via CI/CD gate after verifying a successful staging run.
# ---------------------------------------------------------------------------
# moved block: aws_scheduler_schedule.monthly -> monthly[0]
moved {
  from = aws_scheduler_schedule.monthly
  to   = aws_scheduler_schedule.monthly[0]
}

resource "aws_scheduler_schedule" "monthly" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count      = var.enable_cascade ? 1 : 0
  name       = "qgi-indicator-monthly-updater-1st"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = "cron(0 6 1 * ? *)"
  schedule_expression_timezone = "Europe/Berlin"

  state = "DISABLED"

  target {
    arn      = aws_sfn_state_machine.pipeline[0].arn
    role_arn = var.eventbridge_scheduler_role_arn
  }
}
