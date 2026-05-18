# ---------------------------------------------------------------------------
# QGI live news-pulse poller (qgi-aws-tf live-pulse track, founder go 2026-06-11)
#
# A single bounded Lambda, fired hourly by EventBridge Scheduler, that turns
# the free raw GDELT GKG feed into dashboard/hf-pulse-live.json. The frontend
# reads that file at runtime (same pattern as country-risks.json) behind a
# staleness gate. No GitHub Actions minutes, no always-on box, no second
# cloud, no API keys: the write is an in-account IAM-role call.
#
# DIVERGENCE FROM THE QGI LAMBDA CONVENTION (intentional, documented):
# Other QGI Lambdas ship a placeholder zip and let qgi-pipeline CI deploy the
# real code. This poller packages its REAL handler directly via archive_file
# so `terraform apply` deploys working code with ZERO GitHub minutes — which
# is the entire reason this track exists (the free CI pool is depleted by the
# founder's other repos). The handler is stdlib + runtime-provided boto3 only,
# so there is nothing for CI to build. There is therefore NO lifecycle
# ignore_changes on the source: a code edit + apply is the deploy path.
#
# COST: $0/mo structural. GDELT raw files are public HTTP; Lambda compute is a
# few seconds/run (perpetual free tier, ~5% of the monthly free GB-seconds);
# EventBridge Scheduler's 24 fires/day is ~0.005% of its free 14M/mo. The
# budget below is a belt, not an expectation.
# ---------------------------------------------------------------------------

locals {
  function_name = "qgi-live-pulse-poller"
}

# Package the real handler. Source hash drives redeploy on every code change.
data "archive_file" "poller" {
  type        = "zip"
  source_file = "${path.module}/src/lambda_function.py"
  output_path = "${path.module}/build/poller.zip"
}

# ---------------------------------------------------------------------------
# IAM — execution role, scoped to the four dashboard keys + its own log group
# ---------------------------------------------------------------------------
resource "aws_iam_role" "poller" {
  name = "${local.function_name}-role"
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

resource "aws_iam_role_policy" "poller" {
  role = aws_iam_role.poller.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:${var.aws_account_id}:log-group:/aws/lambda/${local.function_name}*"
      },
      {
        # Read the baseline + rolling bucket cache + the rolling article feed.
        Sid    = "ReadState"
        Effect = "Allow"
        Action = ["s3:GetObject"]
        Resource = [
          "${var.data_lake_bucket_arn}/dashboard/hf-pulse-baseline.json",
          "${var.data_lake_bucket_arn}/dashboard/hf-pulse-buckets.json",
          "${var.data_lake_bucket_arn}/dashboard/hf-pulse-articles.json",
        ]
      },
      {
        # GetObject on a not-yet-written key (the buckets cache, on the first
        # run) returns 404 NoSuchKey ONLY if the caller has s3:ListBucket on the
        # bucket; without it S3 returns 403 AccessDenied, which the handler
        # (correctly) treats as a real error and fails. Unconditioned because a
        # prefix condition is not honored for GetObject's implicit existence
        # check. GetObject/PutObject above stay scoped to the two dashboard keys,
        # so this only grants the ability to LIST key names. (Found by the canary.)
        Sid      = "ListForMissingKey404"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = var.data_lake_bucket_arn
      },
      {
        # Write the rolling bucket cache + the live output the frontend reads +
        # the rolling 24h headline feed for the terminal news rail.
        Sid    = "WriteOutput"
        Effect = "Allow"
        Action = ["s3:PutObject"]
        Resource = [
          "${var.data_lake_bucket_arn}/dashboard/hf-pulse-buckets.json",
          "${var.data_lake_bucket_arn}/dashboard/hf-pulse-live.json",
          "${var.data_lake_bucket_arn}/dashboard/hf-pulse-articles.json",
        ]
      },
      {
        # Park failed async invocations on the DLQ.
        Sid      = "Dlq"
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = aws_sqs_queue.dlq.arn
      },
    ]
  })
}

# ---------------------------------------------------------------------------
# Logs — explicit group so retention is managed (Lambda auto-creates with
# never-expire otherwise).
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "poller" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

# ---------------------------------------------------------------------------
# The poller Lambda
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "poller" {
  function_name    = local.function_name
  description      = "Hourly live news-pulse nowcast from raw GDELT GKG -> dashboard/hf-pulse-live.json"
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.13"
  architectures    = ["arm64"]
  timeout          = var.timeout
  memory_size      = var.memory_size
  filename         = data.archive_file.poller.output_path
  source_code_hash = data.archive_file.poller.output_base64sha256
  role             = aws_iam_role.poller.arn
  # No layers: stdlib + runtime-provided boto3.

  environment {
    variables = {
      QGI_DATA_LAKE_BUCKET = var.data_lake_bucket_name
    }
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.dlq.arn
  }

  depends_on = [aws_cloudwatch_log_group.poller]
  tags       = var.tags
}

# ---------------------------------------------------------------------------
# DLQ — failed async invokes land here (14-day retention) so a silent run of
# failures is visible and alarmable rather than lost.
# ---------------------------------------------------------------------------
resource "aws_sqs_queue" "dlq" {
  name                      = "${local.function_name}-dlq"
  message_retention_seconds = 1209600 # 14 days
  tags                      = var.tags
}

# ---------------------------------------------------------------------------
# EventBridge Scheduler — the hourly clock.
#
# Founder-ratified Scheduler exception (2026-06-11): the org convention keeps
# Scheduler DISABLED to guard expensive pipeline fan-outs ($37/$139 incidents).
# This target is a single bounded free Lambda, so it ships ENABLED by default.
# Set var.schedule_state = "DISABLED" to stage the infra without the clock.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "scheduler" {
  name = "${local.function_name}-scheduler-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "aws:SourceAccount" = var.aws_account_id }
      }
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy" "scheduler_invoke" {
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = [aws_lambda_function.poller.arn, "${aws_lambda_function.poller.arn}:*"]
    }]
  })
}

resource "aws_scheduler_schedule" "hourly" {
  name       = "${local.function_name}-hourly"
  group_name = "default"
  state      = var.schedule_state

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = var.schedule_expression

  target {
    arn      = aws_lambda_function.poller.arn
    role_arn = aws_iam_role.scheduler.arn

    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 3600
    }

    dead_letter_config {
      arn = aws_sqs_queue.dlq.arn
    }
  }
}

# ---------------------------------------------------------------------------
# Cost guard — a $1/mo Lambda-service budget. Real expectation is $0; this
# fires only if something pathological happens (mis-set schedule, fetch loop).
#
# SCOPE CAVEAT: AWS Budgets cannot filter to a single function, so this filters
# on Service = "AWS Lambda" account-wide. In staging that also covers the
# pipeline + recipe-fleet Lambdas, so it is a coarse account-Lambda backstop,
# not a per-function meter. The DLQ alarm below is the function-specific signal.
# ---------------------------------------------------------------------------
resource "aws_budgets_budget" "lambda_monthly" {
  name         = "qgi-${var.environment}-live-pulse-lambda-monthly"
  budget_type  = "COST"
  limit_amount = "1.00"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "Service"
    values = ["AWS Lambda"]
  }

  dynamic "notification" {
    for_each = var.cost_alerts_topic_arn == "" ? [] : [1]
    content {
      comparison_operator       = "GREATER_THAN"
      threshold                 = 100
      threshold_type            = "PERCENTAGE"
      notification_type         = "ACTUAL"
      subscriber_sns_topic_arns = [var.cost_alerts_topic_arn]
    }
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Health alarm — DLQ depth > 0 means runs are failing; surface it.
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  alarm_name          = "${local.function_name}-dlq-not-empty"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300 # 5-min window so a parked failure surfaces promptly
  statistic           = "Maximum"
  threshold           = 0
  alarm_description   = "live-pulse poller is parking failures on its DLQ"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.dlq.name
  }

  alarm_actions = var.cost_alerts_topic_arn == "" ? [] : [var.cost_alerts_topic_arn]
  ok_actions    = var.cost_alerts_topic_arn == "" ? [] : [var.cost_alerts_topic_arn]
  tags          = var.tags
}

# ---------------------------------------------------------------------------
# Runaway guard (FinOps review) — the $1 Lambda budget is account-wide and lags
# up to 24h, so a `rate(1 minute)` typo could burn real money before it fires.
# This per-function alarm trips within the hour: an hourly schedule means ~1
# invocation/hour (3 at most with the 2 Scheduler retries); >4/hour is a
# misconfigured rate() or a loop. Cheap insurance with a fast signal.
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "invocations_runaway" {
  alarm_name          = "${local.function_name}-invocations-runaway"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Invocations"
  namespace           = "AWS/Lambda"
  period              = 3600
  statistic           = "Sum"
  threshold           = 4
  alarm_description   = "live-pulse poller firing far more than hourly — possible rate() misconfig or loop"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.poller.function_name
  }

  alarm_actions = var.cost_alerts_topic_arn == "" ? [] : [var.cost_alerts_topic_arn]
  tags          = var.tags
}
