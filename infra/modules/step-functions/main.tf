data "aws_iam_policy_document" "assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = "${var.name}-sfn-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "extra" {
  for_each   = toset(var.policy_arns)
  role       = aws_iam_role.this.name
  policy_arn = each.value
}

resource "aws_cloudwatch_log_group" "this" {
  count             = var.enable_logging ? 1 : 0
  name              = "/aws/vendedlogs/states/${var.name}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_sfn_state_machine" "this" {
  name       = var.name
  role_arn   = aws_iam_role.this.arn
  definition = var.definition
  type       = var.type

  dynamic "logging_configuration" {
    for_each = var.enable_logging ? [1] : []
    content {
      log_destination        = "${aws_cloudwatch_log_group.this[0].arn}:*"
      include_execution_data = true
      level                  = var.logging_level
    }
  }

  tags = var.tags
}
