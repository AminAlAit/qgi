# ---------------------------------------------------------------------------
# #417 Option C — Frontend bake trigger
#
# When the finalize Lambda writes a new `dashboard/country-risks.json`,
# the S3 event notification fires this Lambda, which POSTs a
# `workflow_dispatch` to AminAlAit/qgi-frontend. The workflow pulls the
# file from S3 via OIDC, commits it to `data/country-risks.json`, and
# pushes — Vercel auto-deploys on push.
#
# Three resources below:
#   1. IAM role for the bake trigger Lambda (scoped to CloudWatch Logs
#      + SecretsManager GetSecretValue on the GitHub PAT).
#   2. The GitHub PAT secret (value set manually via AWS console — see
#      deployment notes on #417).
#   3. The Lambda function + S3 notification + invoke permission.
#
# The real Python code lives in
# qgi-pipeline/lambdas/qgi-frontend-bake-trigger/ and deploys via
# qgi-pipeline's deploy-lambdas.yml workflow. Terraform supplies the
# placeholder zip; first real deploy lands via CI.
#
# Manual post-apply step (tracked on #417):
#   aws secretsmanager put-secret-value \
#     --secret-id qgi-github-frontend-dispatch-pat \
#     --secret-string 'github_pat_...'
# PAT must have `actions:write` on AminAlAit/qgi-frontend. Fine-grained
# is preferred; rotate via `put-secret-value` (no Lambda redeploy needed
# — the handler reads the secret on every invocation).
# ---------------------------------------------------------------------------

# The GitHub PAT, stored empty. Amin populates via console or CLI after
# apply. Lambda reads at invocation time (not cached) so rotation is
# instant.
resource "aws_secretsmanager_secret" "github_frontend_dispatch_pat" {
  name                    = "qgi-github-frontend-dispatch-pat"
  description             = "GitHub PAT for workflow_dispatch on AminAlAit/qgi-frontend (#417)"
  recovery_window_in_days = 7

  tags = var.tags
}

# IAM role scoped tightly — CloudWatch Logs + the one secret.
resource "aws_iam_role" "frontend_bake_trigger" {
  name = "qgi-frontend-bake-trigger-role"
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

resource "aws_iam_role_policy" "frontend_bake_trigger" {
  role = aws_iam_role.frontend_bake_trigger.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:${var.aws_account_id}:log-group:/aws/lambda/qgi-frontend-bake-trigger*"
      },
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = aws_secretsmanager_secret.github_frontend_dispatch_pat.arn
      },
    ]
  })
}

resource "aws_lambda_function" "frontend_bake_trigger" {
  function_name    = "qgi-frontend-bake-trigger"
  handler          = "lambda_function.lambda_handler"
  timeout          = 30
  memory_size      = 128
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_defaults.source_code_hash
  role             = aws_iam_role.frontend_bake_trigger.arn
  # No layers — the Lambda uses only boto3 (runtime-provided) + stdlib.

  environment {
    variables = {
      GITHUB_OWNER           = "AminAlAit"
      GITHUB_REPO            = "qgi-frontend"
      GITHUB_WORKFLOW_FILE   = "bake-country-risks.yml"
      GITHUB_REF             = "main"
      GITHUB_PAT_SECRET_NAME = aws_secretsmanager_secret.github_frontend_dispatch_pat.name
      S3_EXPECTED_KEY        = "dashboard/country-risks.json"
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

# Allow S3 to invoke the Lambda.
resource "aws_lambda_permission" "frontend_bake_trigger_s3" {
  statement_id  = "AllowExecutionFromS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.frontend_bake_trigger.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = "arn:aws:s3:::${var.data_lake_bucket_name}"
}

# S3 event notification on the data-lake bucket. `aws_s3_bucket_notification`
# is a SINGLE RESOURCE per bucket — if another notification is ever added,
# merge into the same resource's lambda_function blocks rather than creating
# a second aws_s3_bucket_notification (Terraform will clobber).
resource "aws_s3_bucket_notification" "data_lake" {
  bucket = var.data_lake_bucket_name

  # #494 step 6: enable EventBridge forwarding so S3 ObjectCreated
  # events on the bucket reach the `qgi-vdem-zip-uploaded` rule
  # (defined in modules/pipeline/vdem.tf). Without this flag, the
  # rule will never fire even though the rule's event_pattern
  # matches. EventBridge forwarding is bucket-wide; the rule's
  # filter narrows it to the vdem-staging/incoming/*.zip prefix.
  eventbridge = true

  lambda_function {
    id                  = "frontend-bake-trigger"
    lambda_function_arn = aws_lambda_function.frontend_bake_trigger.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "dashboard/"
    filter_suffix       = "country-risks.json"
  }

  depends_on = [aws_lambda_permission.frontend_bake_trigger_s3]
}
