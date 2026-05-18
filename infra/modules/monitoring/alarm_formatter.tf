# ---------------------------------------------------------------------------
# #412 — SNS alarm formatter Lambda
#
# Subscribed to the `qgi-monthly-updates` SNS topic (var.sns_topic_arn).
# Parses CloudWatch alarm JSON, renders a readable subject + body per
# alarm family, sends to qgintelligence@gmail.com via SES.
#
# The actual Python lives in qgi-pipeline/lambdas/qgi-sns-alarm-formatter/
# and deploys via qgi-pipeline's deploy-lambdas.yml workflow (same pattern
# as every other QGI Lambda). Terraform provides the placeholder zip; the
# real code lands on CI deploy.
#
# SES sandbox caveat (manual Amin step):
# 1. Verify sender identity (e.g., `alerts@qgintelligence.com`):
#      aws sesv2 create-email-identity --email-identity alerts@qgintelligence.com
# 2. Verify recipient (`qgintelligence@gmail.com`) — click the confirmation
#    link AWS sends to the recipient.
# Skipping either step makes the Lambda fail on first invocation; CloudWatch
# logs will show a `MessageRejected` exception. Production-access exit
# (removes the recipient-verification restriction) is a separate SES console
# request, not required for this single-recipient setup.
# ---------------------------------------------------------------------------

# Placeholder zip — identical pattern to every other QGI Lambda in
# modules/pipeline/main.tf. If CI/CD hasn't deployed real code yet, any
# invocation raises a descriptive RuntimeError so bugs surface immediately
# rather than silently succeeding with a stub.
data "archive_file" "alarm_formatter_placeholder" {
  type        = "zip"
  output_path = "${path.module}/alarm_formatter_placeholder.zip"
  source {
    content  = <<-EOT
      """Placeholder for qgi-sns-alarm-formatter. See #412.
      Real code in qgi-pipeline/lambdas/qgi-sns-alarm-formatter/ deploys
      via qgi-pipeline deploy-lambdas.yml workflow.
      """
      def lambda_handler(event, context):
          raise RuntimeError(
              "PLACEHOLDER STUB STILL LIVE for qgi-sns-alarm-formatter. "
              "Terraform created this function but CI/CD has not deployed "
              "the real code. Trigger: `gh workflow run deploy-lambdas.yml "
              "--repo AminAlAit/qgi-pipeline -f deploy_all=true` or push a "
              "commit touching lambdas/qgi-sns-alarm-formatter/."
          )
    EOT
    filename = "lambda_function.py"
  }
}

# IAM role for the formatter Lambda — scoped to SES send + CloudWatch logs.
resource "aws_iam_role" "alarm_formatter" {
  name = "qgi-sns-alarm-formatter-role"
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

resource "aws_iam_role_policy" "alarm_formatter" {
  role = aws_iam_role.alarm_formatter.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # SES send-email is identity-based; the IAM resource is "*" and
        # authorization is enforced by the verified sender identity itself.
        # Attempting to send from a non-verified identity returns
        # MessageRejected regardless of IAM.
        Effect   = "Allow"
        Action   = ["ses:SendEmail", "ses:SendRawEmail"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

resource "aws_lambda_function" "alarm_formatter" {
  function_name    = "qgi-sns-alarm-formatter"
  role             = aws_iam_role.alarm_formatter.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.13"
  architectures    = ["arm64"]
  filename         = data.archive_file.alarm_formatter_placeholder.output_path
  source_code_hash = data.archive_file.alarm_formatter_placeholder.output_base64sha256
  timeout          = 30
  memory_size      = 128

  environment {
    variables = {
      SENDER_EMAIL    = var.alarm_formatter_sender_email
      RECIPIENT_EMAIL = var.alarm_formatter_recipient_email
      SES_REGION      = data.aws_region.current.name
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
  tags = var.tags
}

data "aws_region" "current" {}

# SNS permission + subscription — route qgi-monthly-updates alarm events
# through the formatter Lambda.
resource "aws_lambda_permission" "alarm_formatter_sns" {
  statement_id  = "AllowExecutionFromSNS"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.alarm_formatter.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = var.sns_topic_arn
}

resource "aws_sns_topic_subscription" "alarm_formatter" {
  topic_arn = var.sns_topic_arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.alarm_formatter.arn
}
