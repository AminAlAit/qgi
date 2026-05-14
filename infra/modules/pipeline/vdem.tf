# V-Dem annual-refresh pipeline (#494 step 6).
#
# End-to-end orchestration tying together:
#   - The unzip Lambda  (qgi-pipeline/lambdas/vdem-unzip/)
#   - The Batch ingest  (qgi-pipeline/batch/qgi-vdem-ingest/, JobDef in modules/batch/vdem.tf)
#   - The S3 trigger    (EventBridge on vdem-staging/incoming/*.zip)
#   - The notification  (SNS to qgintelligence@gmail.com)
#
# Operator flow (#494 acceptance):
#   1. Human downloads V-Dem ZIP from v-dem.net (gated form)
#   2. Human drops the ZIP at s3://${var.data_lake_bucket_name}/vdem-staging/incoming/
#   3. S3 EventBridge fires → SF execution starts
#   4. SF Task 1 invokes vdem-unzip Lambda → returns unzipped_key
#   5. SF Task 2 submits Batch job with VDEM_CSV_S3_KEY=$unzipped_key
#   6. SF Task 3 publishes success/failure to SNS → email to ops inbox
#
# Cost discipline (founder direction 2026-04-27 "follow every cost
# saving trick in the book"):
#   - Lambda: ARM64 Graviton, 1024MB memory, 5min timeout
#   - Batch: Fargate Spot (sibling of FAO; m7g instance-type rule
#     doesn't apply since Fargate is per-task billed)
#   - Step Functions: Standard workflow (NOT Express — Express has
#     a 5-min hard limit and our Batch step can take up to 30 min).
#     Standard pricing is per-state-transition: this workflow has
#     ~4 transitions per execution × 1-2 executions/year = pennies.
#   - CloudWatch logs: 14-day retention (matches Batch sibling)
#   - SNS: free for the volume we use
#   - DynamoDB / S3 marker: not used — no idempotency state needed
#     since #505 covers ingest_vdem.py's own idempotency contract


# ===========================================================================
# Lambda: vdem-unzip
# ===========================================================================

resource "aws_cloudwatch_log_group" "vdem_unzip" {
  name              = "/aws/lambda/qgi-vdem-unzip"
  retention_in_days = 14
  tags              = var.tags
}

resource "aws_iam_role" "vdem_unzip" {
  name = "qgi-vdem-unzip-role"

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

resource "aws_iam_role_policy" "vdem_unzip" {
  name = "qgi-vdem-unzip-policy"
  role = aws_iam_role.vdem_unzip.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # CloudWatch Logs — scoped to the function's own log group
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "${aws_cloudwatch_log_group.vdem_unzip.arn}:*"
      },
      {
        # S3 read on vdem-staging/incoming/*.zip (the uploaded ZIP)
        Effect = "Allow"
        Action = [
          "s3:GetObject",
        ]
        Resource = "arn:aws:s3:::${var.data_lake_bucket_name}/vdem-staging/incoming/*"
      },
      {
        # S3 write on vdem-staging/unzipped/*.csv (the extracted CSV
        # the Batch job will pick up)
        Effect = "Allow"
        Action = [
          "s3:PutObject",
        ]
        Resource = "arn:aws:s3:::${var.data_lake_bucket_name}/vdem-staging/unzipped/*"
      },
    ]
  })
}

resource "aws_lambda_function" "vdem_unzip" {
  function_name = "qgi-vdem-unzip"
  role          = aws_iam_role.vdem_unzip.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.13"
  architectures = ["arm64"] # Graviton — ~20% cheaper than x86

  # Memory: V-Dem v16 ZIP ~140MB compressed → ~388MB CSV in memory.
  # Peak resident: ~530MB during read+upload. 1024MB gives ~50%
  # headroom. The MAX_CSV_BYTES guard in the Lambda code (700MB
  # default) raises an actionable UnzipError before we'd OOM.
  memory_size = 1024

  # Timeout: ~30s download + ~10s extract + ~10s upload = ~50s
  # nominal. 5 min budget covers a slow S3 day comfortably.
  timeout = 300

  # Filled in by deploy-lambdas.yml on first push to main; the
  # placeholder here just bootstraps the resource. update-function-code
  # in CI replaces the contents per commit.
  filename         = "${path.module}/placeholder.zip"
  source_code_hash = filebase64sha256("${path.module}/placeholder.zip")

  environment {
    variables = {
      # Cap can be bumped via Terraform if a future V-Dem release
      # legitimately exceeds 700MB uncompressed.
      MAX_CSV_BYTES = "700000000"
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.vdem_unzip.name
  }

  depends_on = [
    aws_cloudwatch_log_group.vdem_unzip,
    aws_iam_role_policy.vdem_unzip,
  ]

  tags = var.tags

  # Suppress diff on filename/source_code_hash — those get rewritten
  # by the deploy-lambdas.yml workflow on each merge to main, and
  # Terraform shouldn't try to revert them.
  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }
}


# ===========================================================================
# SNS: notification topic
# ===========================================================================

resource "aws_sns_topic" "vdem_ingest_status" {
  name              = "qgi-vdem-ingest-status"
  display_name      = "V-Dem ingest pipeline status"
  kms_master_key_id = "alias/aws/sns" # AWS-managed encryption (free)
  tags              = var.tags
}

resource "aws_sns_topic_subscription" "vdem_ingest_status_email" {
  topic_arn = aws_sns_topic.vdem_ingest_status.arn
  protocol  = "email"
  endpoint  = var.ops_email_address
}


# ===========================================================================
# IAM: Step Functions execution role
# ===========================================================================

resource "aws_iam_role" "vdem_state_machine" {
  name = "qgi-vdem-state-machine-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "states.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "vdem_state_machine" {
  name = "qgi-vdem-state-machine-policy"
  role = aws_iam_role.vdem_state_machine.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Invoke the unzip Lambda (specific function, not wildcard)
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = aws_lambda_function.vdem_unzip.arn
      },
      {
        # Submit Batch jobs to the qgi-vdem-ingest job definition
        # only. Wildcard the queue ARN since Batch's job-queue ARN
        # format is verbose and adding the queue name as a Terraform
        # input would couple modules unnecessarily — but the action
        # set (SubmitJob, DescribeJobs, TerminateJob) limits blast
        # radius to Batch operations.
        Effect = "Allow"
        Action = [
          "batch:SubmitJob",
          "batch:DescribeJobs",
          "batch:TerminateJob",
        ]
        Resource = [
          var.vdem_batch_job_definition_arn,
          var.fetcher_job_queue_arn,
          # ":job/*" is required because SubmitJob creates a new job
          # ARN each invocation; SF's resource-level permissions
          # for batch:SubmitJob need the queue + job-def + jobs/*
          "arn:aws:batch:${var.region}:${var.aws_account_id}:job/*",
        ]
      },
      {
        # SubmitJob's CloudWatch event integration: SF needs to
        # CreateRule + PutTargets on a managed rule that delivers
        # job state changes back to SF (the .sync waiter pattern).
        # Scoped to the SF-managed rule prefix.
        Effect = "Allow"
        Action = [
          "events:PutTargets",
          "events:PutRule",
          "events:DescribeRule",
        ]
        Resource = "arn:aws:events:${var.region}:${var.aws_account_id}:rule/StepFunctionsGetEventsForBatchJobsRule"
      },
      {
        # Publish to the V-Dem SNS topic (specific topic only)
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = aws_sns_topic.vdem_ingest_status.arn
      },
      {
        # CloudWatch Logs for SF's own execution history
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery",
          "logs:GetLogDelivery",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries",
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:DescribeLogGroups",
        ]
        Resource = "*"
      },
    ]
  })
}


# ===========================================================================
# Step Functions state machine
# ===========================================================================

resource "aws_cloudwatch_log_group" "vdem_state_machine" {
  name              = "/aws/states/qgi-vdem-ingest-on-upload"
  retention_in_days = 30 # SF executions are sparse; 30d is fine for audit
  tags              = var.tags
}

resource "aws_sfn_state_machine" "vdem_ingest_on_upload" {
  name     = "qgi-vdem-ingest-on-upload"
  role_arn = aws_iam_role.vdem_state_machine.arn
  type     = "STANDARD" # Express has 5-min limit; Batch step can run 30 min

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.vdem_state_machine.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  definition = jsonencode({
    Comment = "V-Dem annual-refresh ingest pipeline (#494)"
    StartAt = "UnzipCSV"
    States = {
      UnzipCSV = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.vdem_unzip.arn
          Payload = {
            "bucket.$"       = "$.bucket"
            "incoming_key.$" = "$.incoming_key"
          }
        }
        # Strip the Lambda invoke envelope; the Lambda's return body
        # is what we want as state input for the next step
        OutputPath = "$.Payload"
        Retry = [{
          ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException", "Lambda.TooManyRequestsException"]
          IntervalSeconds = 2
          MaxAttempts     = 3
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          ResultPath  = "$.error"
          Next        = "NotifyFailure"
        }]
        Next = "RunIngest"
      }

      RunIngest = {
        Type     = "Task"
        Resource = "arn:aws:states:::batch:submitJob.sync"
        Parameters = {
          JobName       = "qgi-vdem-ingest-execution"
          JobQueue      = var.fetcher_job_queue_arn
          JobDefinition = var.vdem_batch_job_definition_arn
          ContainerOverrides = {
            Environment = [
              { Name = "S3_BUCKET", "Value.$" = "$.bucket" },
              { Name = "VDEM_CSV_S3_KEY", "Value.$" = "$.unzipped_key" },
              { Name = "AWS_REGION", Value = var.region },
              { Name = "ATHENA_WORKGROUP", Value = var.athena_workgroup_name },
            ]
          }
        }
        # ResultPath merges the Batch result INTO the existing state
        # (under $.batch_result) instead of REPLACING it. Without this,
        # NotifySuccess's States.Format references to $.bucket /
        # $.unzipped_key / $.csv_size_bytes / $.csv_filename (set by
        # the UnzipCSV Lambda step) would silently disappear, and the
        # SNS message would error at runtime. Sibling SF state machines
        # in modules/pipeline/main.tf use the same pattern.
        ResultPath = "$.batch_result"
        Catch = [{
          ErrorEquals = ["States.ALL"]
          ResultPath  = "$.error"
          Next        = "NotifyFailure"
        }]
        Next = "NotifySuccess"
      }

      NotifySuccess = {
        Type     = "Task"
        Resource = "arn:aws:states:::sns:publish"
        Parameters = {
          TopicArn = aws_sns_topic.vdem_ingest_status.arn
          Subject  = "[QGI] V-Dem ingest succeeded"
          # SF intrinsic functions: serialize the input to a string
          # and prepend a friendly preamble. The unzipped_key +
          # csv_size_bytes give the operator quick context.
          "Message.$" = "States.Format('V-Dem annual ingest pipeline completed.\n\nBucket: {}\nUnzipped CSV: {}\nCSV size: {} bytes\nFilename: {}\n\nThe per-indicator parquets are now in qgi_data.indicators (provider=VDEM). The Athena MSCK REPAIR was run as part of the Batch step.', $.bucket, $.unzipped_key, $.csv_size_bytes, $.csv_filename)"
        }
        End = true
      }

      NotifyFailure = {
        Type     = "Task"
        Resource = "arn:aws:states:::sns:publish"
        Parameters = {
          TopicArn    = aws_sns_topic.vdem_ingest_status.arn
          Subject     = "[QGI] V-Dem ingest FAILED — operator action needed"
          "Message.$" = "States.Format('V-Dem annual ingest pipeline FAILED.\n\nError context:\n{}\n\nCheck the SF execution history in the AWS console for the failed task and CloudWatch logs (/aws/lambda/qgi-vdem-unzip or /aws/batch/qgi-vdem-ingest). The unzipped CSV (if step 1 succeeded) is at vdem-staging/unzipped/ — re-running the SF execution from there is safe.', $.error)"
        }
        # Fail the whole execution after notifying so SF status
        # accurately reflects the run result
        Next = "FailExecution"
      }

      FailExecution = {
        Type  = "Fail"
        Error = "VDemIngestFailed"
        Cause = "See preceding NotifyFailure state's input for details."
      }
    }
  })

  tags = var.tags
}


# ===========================================================================
# EventBridge: S3 PUT trigger on vdem-staging/incoming/*.zip
# ===========================================================================

# Role that EventBridge uses to start SF executions (the rule's target).
# Required because EventBridge → SF is cross-service: EventBridge
# needs an IAM principal with states:StartExecution on the target.
resource "aws_iam_role" "vdem_eventbridge_target" {
  name = "qgi-vdem-eventbridge-target-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "vdem_eventbridge_target" {
  name = "qgi-vdem-eventbridge-target-policy"
  role = aws_iam_role.vdem_eventbridge_target.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["states:StartExecution"]
      Resource = aws_sfn_state_machine.vdem_ingest_on_upload.arn
    }]
  })
}

resource "aws_cloudwatch_event_rule" "vdem_zip_uploaded" {
  name        = "qgi-vdem-zip-uploaded"
  description = "Fires on S3 PUT to vdem-staging/incoming/*.zip → starts the V-Dem ingest SF (#494)"

  event_pattern = jsonencode({
    source        = ["aws.s3"]
    "detail-type" = ["Object Created"]
    detail = {
      bucket = {
        name = [var.data_lake_bucket_name]
      }
      object = {
        # EventBridge content-filtering only allows ONE match expression
        # per match-list element ("Only one key allowed in match
        # expression" error if you nest prefix + suffix together).
        # Use prefix-only — the `vdem-staging/incoming/` prefix is
        # dedicated to V-Dem uploads, so any object dropped there is
        # meant for this pipeline. Non-ZIP objects (e.g., a stray PDF)
        # would still trigger the rule but the unzip Lambda raises
        # UnzipError, which routes through SF NotifyFailure → SNS, and
        # the operator gets an actionable email.
        key = [{
          prefix = "vdem-staging/incoming/"
        }]
      }
    }
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "vdem_zip_uploaded" {
  rule     = aws_cloudwatch_event_rule.vdem_zip_uploaded.name
  arn      = aws_sfn_state_machine.vdem_ingest_on_upload.arn
  role_arn = aws_iam_role.vdem_eventbridge_target.arn

  # Transform the EventBridge S3 event into the input shape the SF
  # state machine expects: {bucket, incoming_key}.
  input_transformer {
    input_paths = {
      bucket = "$.detail.bucket.name"
      key    = "$.detail.object.key"
    }
    input_template = <<EOF
{
  "bucket": <bucket>,
  "incoming_key": <key>
}
EOF
  }
}
