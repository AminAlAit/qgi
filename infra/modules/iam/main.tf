# ---------------------------------------------------------------------------
# GitHub Actions OIDC provider — allows qgi-pipeline CI/CD to deploy Lambdas
# ---------------------------------------------------------------------------
data "tls_certificate" "github_actions" {
  url = "https://token.actions.githubusercontent.com/.well-known/openid-configuration"
}

resource "aws_iam_openid_connect_provider" "github_actions" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github_actions.certificates[0].sha1_fingerprint]
}

resource "aws_iam_role" "github_actions_lambda_deploy" {
  name = "github-actions-qgi-lambda-deploy"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github_actions.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          # Allow from main branch and version tags
          "token.actions.githubusercontent.com:sub" = [
            "repo:AminAlAit/qgi-pipeline:ref:refs/heads/main",
            "repo:AminAlAit/qgi-pipeline:ref:refs/tags/*",
          ]
        }
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "github_actions_lambda_deploy" {
  name = "qgi-lambda-deploy-policy"
  role = aws_iam_role.github_actions_lambda_deploy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["lambda:UpdateFunctionCode", "lambda:GetFunction"]
      Resource = "arn:aws:lambda:${var.region}:${var.aws_account_id}:function:qgi-*"
    }]
  })
}

# ---------------------------------------------------------------------------
# GitHub Actions OIDC role — push Phase 1/2 Batch images to this account's ECR
#
# Per-account companion to the management-account role of the same name
# (which pushes to 783811616921 ECR). This staging/QA/prod role allows
# AminAlAit/qgi-pipeline to push directly to this account's ECR repos so
# JobDefs can reference local URIs without the cross-account pull dance
# (#152 Path A is parked — each env owns its own image copies for now).
#
# Scoped to all three Phase 1/2 image repos so a stale WB image can be
# re-pushed later without coming back for IAM changes.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "github_actions_ecr_push" {
  name = "github-actions-qgi-ecr-push"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github_actions.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = [
            "repo:AminAlAit/qgi-pipeline:ref:refs/heads/main",
            "repo:AminAlAit/qgi-pipeline:ref:refs/tags/*",
          ]
        }
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "github_actions_ecr_push" {
  name = "qgi-ecr-push-policy"
  role = aws_iam_role.github_actions_ecr_push.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # ecr:GetAuthorizationToken must be "*" — ECR authZ is account-wide.
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchGetImage",
          "ecr:CompleteLayerUpload",
          # DescribeImages is the sibling read used during the buildx
          # manifest-merge step (BatchGetImage covers HEAD; DescribeImages
          # covers list/lookup). Mirrors the same 8-action set on the
          # management-account ECRPushIndicatorFetcher + ECRPushDSCDIFinder
          # policies in qgi-aws-tf — see #635 for the sibling-policy drift
          # audit. The staging policy already had BatchGetImage so the
          # buildx 403 the management-account dscdi-finder hit on 2026-05-10
          # (run 25408279393) would not reproduce here, but DescribeImages
          # is needed to keep the 4 sibling policies semantically aligned.
          "ecr:DescribeImages",
          "ecr:DescribeRepositories",
          "ecr:GetDownloadUrlForLayer",
          "ecr:InitiateLayerUpload",
          "ecr:PutImage",
          "ecr:UploadLayerPart",
        ]
        Resource = [
          "arn:aws:ecr:${var.region}:${var.aws_account_id}:repository/qgi-pipeline-a-indicator-fetcher",
          "arn:aws:ecr:${var.region}:${var.aws_account_id}:repository/qgi-pipeline-a-indicator-fetcher-fao",
          # qgi-pipeline-a-vdem-ingest: created in modules/batch/vdem.tf line 21,
          # pushed to by .github/workflows/ecr-push.yml in qgi-pipeline (the
          # same workflow that pushes the 3 other repos). Missing from this
          # Resource list is the second latent issue of #635 class — surfaced
          # by the PR #23 strict review. Without it, next push to
          # batch/qgi-vdem-ingest/** 403s with AccessDenied on the repo ARN
          # (different symptom than the buildx manifest HEAD failure mode,
          # but same root cause: sibling-policy/sibling-resource drift).
          "arn:aws:ecr:${var.region}:${var.aws_account_id}:repository/qgi-pipeline-a-vdem-ingest",
          "arn:aws:ecr:${var.region}:${var.aws_account_id}:repository/qgi-pipeline-b-scdi-finder",
          # #106 recipe-fleet image (qgi-pipeline/batch/recipe-fleet/Dockerfile).
          "arn:aws:ecr:${var.region}:${var.aws_account_id}:repository/qgi-recipe-fleet",
          # Enrichment stage 2: the 7 new-provider fetcher images
          # (modules/batch/new_fetchers.tf). Without these, qgi-pipeline CI image
          # pushes 403 AccessDenied — the #635 sibling-resource-drift pattern.
          "arn:aws:ecr:${var.region}:${var.aws_account_id}:repository/qgi-pipeline-a-indicator-fetcher-unhcr",
          "arn:aws:ecr:${var.region}:${var.aws_account_id}:repository/qgi-pipeline-a-indicator-fetcher-ucdp",
          "arn:aws:ecr:${var.region}:${var.aws_account_id}:repository/qgi-pipeline-a-indicator-fetcher-ilostat",
          "arn:aws:ecr:${var.region}:${var.aws_account_id}:repository/qgi-pipeline-a-indicator-fetcher-oecd",
          "arn:aws:ecr:${var.region}:${var.aws_account_id}:repository/qgi-pipeline-a-indicator-fetcher-idmc",
          "arn:aws:ecr:${var.region}:${var.aws_account_id}:repository/qgi-pipeline-a-indicator-fetcher-undp",
          "arn:aws:ecr:${var.region}:${var.aws_account_id}:repository/qgi-pipeline-a-indicator-fetcher-owid",
        ]
      },
    ]
  })
}

# ---------------------------------------------------------------------------
# Lambda execution role
# ---------------------------------------------------------------------------
resource "aws_iam_role" "lambda_execution" {
  name = "qgi-lambda-execution-role"

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

resource "aws_iam_role_policy" "lambda_execution" {
  name = "qgi-lambda-policy"
  role = aws_iam_role.lambda_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:${var.aws_account_id}:log-group:/aws/lambda/qgi-*"
      },
      # S3 — data lake
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket",
        "s3:GetBucketLocation"]
        Resource = [var.data_lake_bucket_arn, "${var.data_lake_bucket_arn}/*"]
      },
      # SQS — all pipeline queues
      {
        Effect = "Allow"
        Action = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage",
          "sqs:GetQueueAttributes", "sqs:GetQueueUrl", "sqs:ChangeMessageVisibility",
        "sqs:PurgeQueue"]
        Resource = var.queue_arns
      },
      # DynamoDB — indicator updates + completion counters + indicator values (#148)
      {
        Effect = "Allow"
        Action = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
          "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan",
        "dynamodb:BatchGetItem", "dynamodb:BatchWriteItem"]
        Resource = [
          var.indicator_table_arn,
          var.completion_table_arn,
          var.indicator_values_table_arn,
          var.pipeline_a_counter_table_arn,
        ]
      },
      # Athena — scoped to the pipeline workgroup (#915). All six query actions
      # authorize against the workgroup resource, and every pipeline Lambda runs
      # in QGI-Lambda-Workgroup (per architecture spec), so scoping here closes the
      # default-workgroup / unbounded-output vector behind the $139 cost incident
      # without affecting any pipeline query.
      {
        Effect = "Allow"
        Action = ["athena:StartQueryExecution", "athena:GetQueryExecution",
          "athena:GetQueryResults", "athena:StopQueryExecution",
        "athena:ListQueryExecutions", "athena:GetWorkGroup"]
        Resource = "arn:aws:athena:${var.region}:${var.aws_account_id}:workgroup/QGI-Lambda-Workgroup"
      },
      # Glue — qgi_data database
      {
        Effect = "Allow"
        Action = ["glue:GetDatabase", "glue:GetTable", "glue:GetTables",
          "glue:CreateTable", "glue:UpdateTable", "glue:DeleteTable",
          "glue:GetPartition", "glue:GetPartitions", "glue:BatchCreatePartition",
        "glue:BatchDeletePartition"]
        Resource = [
          "arn:aws:glue:${var.region}:${var.aws_account_id}:catalog",
          "arn:aws:glue:${var.region}:${var.aws_account_id}:database/qgi_data",
          "arn:aws:glue:${var.region}:${var.aws_account_id}:table/qgi_data/*",
        ]
      },
      # Batch — orchestrator and terminator
      {
        Effect = "Allow"
        Action = ["batch:SubmitJob", "batch:DescribeJobs", "batch:ListJobs",
        "batch:TerminateJob", "batch:DescribeJobQueues", "batch:DescribeJobDefinitions"]
        Resource = "*"
      },
      # SNS — pipeline notifications
      {
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = var.sns_topic_arn
      },
      # Lambda — reporter invokes b-orchestrator directly (known issue, kept for parity)
      {
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = "arn:aws:lambda:${var.region}:${var.aws_account_id}:function:qgi-*"
      },
      # CloudWatch metrics — #381 drift monitoring (finalize Lambda emits
      # HIGH_COUNTRY_COUNT / MEDIAN_SALIENCE_SCORE / COUNTRY_RISKS_BYTES
      # to QGI/Pipeline namespace).
      {
        Effect   = "Allow"
        Action   = ["cloudwatch:PutMetricData"]
        Resource = "*" # CloudWatch PutMetricData requires wildcard; scoped via namespace condition below
        Condition = {
          StringEquals = {
            "cloudwatch:namespace" = "QGI/Pipeline"
          }
        }
      },
      # (#FAR-1) EC2 + SSM perms removed — Phase 1 no longer uses an EC2
      # fetcher instance, so the dispatcher Lambda has no need to start
      # instances or send SSM commands.
    ]
  })
}

# ---------------------------------------------------------------------------
# AWS Batch — ECS instance role (EC2 instances in compute environment)
# ---------------------------------------------------------------------------
resource "aws_iam_role" "ecs_instance" {
  name = "qgi-ecs-instance-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "ecs_instance_container_service" {
  role       = aws_iam_role.ecs_instance.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

resource "aws_iam_instance_profile" "ecs_instance" {
  name = "qgi-ecs-instance-role"
  role = aws_iam_role.ecs_instance.name
}

# ---------------------------------------------------------------------------
# AWS Batch — job role (ECS task role for scdi-finder and dscdi-finder containers)
# ---------------------------------------------------------------------------
resource "aws_iam_role" "batch_job" {
  name = "qgi-batch-job-role"

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

resource "aws_iam_role_policy" "batch_job" {
  name = "qgi-batch-job-policy"
  role = aws_iam_role.batch_job.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # S3 — data lake
      # s3:DeleteObject added 2026-05-06 (Phase 5 v0.0b Stage F preflight) for
      # cleanup-pattern parity with scdi-finder; defensive add for any future
      # checkpoint cleanup the dscdi-finder entrypoint might use.
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket", "s3:GetBucketLocation"]
        Resource = [var.data_lake_bucket_arn, "${var.data_lake_bucket_arn}/*"]
      },
      # ECR — pull image from management account
      # NOTE: management account ECR repo also needs a resource policy allowing this role.
      # Add aws_ecr_repository_policy in qgi-aws-tf management Terraform (see issue #8).
      {
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      # Resource expanded to a list 2026-05-06 (Phase 5 v0.0b Stage F preflight)
      # to add qgi-pipeline-b-dscdi-finder. NOTE: For EC2-backed Batch, the
      # actual image pull is performed by the ECS agent on the host instance
      # using the ECS instance role (qgi-ecs-instance-role). The management-
      # account ECR resource policy (qgi-aws-tf, aws_ecr_repository_policy
      # for qgi-pipeline-b-dscdi-finder) is what actually grants pull access
      # to this staging account. This statement keeps the task role's IAM
      # scope accurate but does NOT gate runtime image pulls.
      {
        Effect = "Allow"
        Action = ["ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage", "ecr:BatchCheckLayerAvailability"]
        Resource = [
          "arn:aws:ecr:${var.region}:${var.management_account_id}:repository/qgi-pipeline-b-scdi-finder",
          "arn:aws:ecr:${var.region}:${var.management_account_id}:repository/qgi-pipeline-b-dscdi-finder",
        ]
      },
      # CloudWatch Logs — Batch job logging
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:${var.aws_account_id}:log-group:/aws/batch/*"
      },
    ]
  })
}

# ---------------------------------------------------------------------------
# Step Functions — execution role
# ---------------------------------------------------------------------------
resource "aws_iam_role" "stepfunctions" {
  name = "qgi-stepfunctions-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "states.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = {
          "aws:SourceAccount" = var.aws_account_id
        }
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "stepfunctions" {
  name = "qgi-stepfunctions-policy"
  role = aws_iam_role.stepfunctions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Invoke all qgi Lambda functions
      {
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = "arn:aws:lambda:${var.region}:${var.aws_account_id}:function:qgi-*"
      },
      # Athena — for MSCK REPAIR TABLE queries (Phase 3 + Phase 4)
      {
        Effect = "Allow"
        Action = ["athena:StartQueryExecution", "athena:GetQueryExecution",
        "athena:GetQueryResults", "athena:StopQueryExecution"]
        Resource = "arn:aws:athena:${var.region}:${var.aws_account_id}:workgroup/*"
      },
      # S3 — Athena query result writes
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:GetBucketLocation",
        "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"]
        Resource = [var.data_lake_bucket_arn, "${var.data_lake_bucket_arn}/*"]
      },
      # Glue — Athena needs Glue for metadata
      {
        Effect = "Allow"
        Action = ["glue:GetDatabase", "glue:GetTable", "glue:GetTables",
          "glue:GetPartition", "glue:GetPartitions", "glue:BatchCreatePartition",
        "glue:UpdateTable", "glue:CreateTable", "glue:DeleteTable"]
        Resource = [
          "arn:aws:glue:${var.region}:${var.aws_account_id}:catalog",
          "arn:aws:glue:${var.region}:${var.aws_account_id}:database/qgi_data",
          "arn:aws:glue:${var.region}:${var.aws_account_id}:table/qgi_data/*",
        ]
      },
      # CloudWatch Logs — Step Functions execution logging
      {
        Effect = "Allow"
        Action = ["logs:CreateLogDelivery", "logs:GetLogDelivery", "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery", "logs:ListLogDeliveries", "logs:PutResourcePolicy",
        "logs:DescribeResourcePolicies", "logs:DescribeLogGroups"]
        Resource = "*"
      },
      # #162: Distributed Map state requires StartExecution on the parent SF
      # (each Map iteration becomes a child execution)
      {
        Effect = "Allow"
        Action = ["states:StartExecution", "states:DescribeExecution", "states:StopExecution"]
        Resource = [
          "arn:aws:states:${var.region}:${var.aws_account_id}:stateMachine:qgi-indicator-monthly-updater",
          "arn:aws:states:${var.region}:${var.aws_account_id}:execution:qgi-indicator-monthly-updater:*",
        ]
      },
      # #106 recipe-fleet SFN: batch:submitJob.sync (canary + Map fan-out + bake).
      # qgi-aws-tf#973 (QA PR #36 round-2 B1): add qgi-bake-te-fleet-run-job*
      # to the JobDefinition Resource list. The "Bake Frontend Corpus" SFN state
      # submits this JobDef on the same queue as the walker; without it the SFN
      # role would get AccessDenied at the bake step despite having SubmitJob on
      # the walker family.
      {
        Effect = "Allow"
        Action = ["batch:SubmitJob", "batch:DescribeJobs", "batch:TerminateJob"]
        Resource = [
          "arn:aws:batch:${var.region}:${var.aws_account_id}:job-queue/qgi-recipe-fleet-queue",
          "arn:aws:batch:${var.region}:${var.aws_account_id}:job-definition/qgi-recipe-fleet-walker-job*",
          "arn:aws:batch:${var.region}:${var.aws_account_id}:job-definition/qgi-bake-te-fleet-run-job*",
          "arn:aws:batch:${var.region}:${var.aws_account_id}:job/*",
        ]
      },
      # #106: the .sync Batch integration creates a managed EventBridge rule to
      # receive job-state-change events. PutRule/PutTargets/DescribeRule CANNOT
      # be resource-scoped (AWS uses a fixed managed rule name), so Resource="*".
      {
        Effect   = "Allow"
        Action   = ["events:PutRule", "events:PutTargets", "events:DescribeRule"]
        Resource = "*"
      },
      # #106: sqs:SendMessage carries the canary approval waitForTaskToken into
      # the dedicated qgi-recipe-fleet-approval queue.
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = "arn:aws:sqs:${var.region}:${var.aws_account_id}:qgi-recipe-fleet-approval"
      },
    ]
  })
}

# ---------------------------------------------------------------------------
# Cross-account ops role — allows management account deployer to trigger and
# monitor staging/qa pipeline executions from the hub Codespace CLI
# ---------------------------------------------------------------------------
resource "aws_iam_role" "cross_account_ops" {
  name = "qgi-cross-account-ops"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = "arn:aws:iam::${var.management_account_id}:user/terraform-deployer" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "cross_account_ops" {
  name = "qgi-cross-account-ops-policy"
  role = aws_iam_role.cross_account_ops.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Step Functions — start and observe executions (#914: scoped to qgi-*
      # state machines + their executions; the deployer never starts a non-qgi
      # SFN. Closes the "start any state machine in the account" cost vector.)
      {
        Effect = "Allow"
        Action = ["states:StartExecution", "states:DescribeExecution",
          "states:ListExecutions", "states:GetExecutionHistory",
        "states:StopExecution"]
        Resource = [
          "arn:aws:states:${var.region}:${var.aws_account_id}:stateMachine:qgi-*",
          "arn:aws:states:${var.region}:${var.aws_account_id}:execution:qgi-*:*",
        ]
      },
      # Lambda — describe, deploy, and invoke
      {
        Effect = "Allow"
        Action = ["lambda:GetFunction", "lambda:GetFunctionConfiguration",
          "lambda:ListFunctions", "lambda:UpdateFunctionCode",
        "lambda:InvokeFunction"]
        Resource = "arn:aws:lambda:${var.region}:${var.aws_account_id}:function:qgi-*"
      },
      # CloudWatch Logs — read pipeline logs
      {
        Effect = "Allow"
        Action = ["logs:DescribeLogGroups", "logs:DescribeLogStreams",
        "logs:GetLogEvents", "logs:FilterLogEvents"]
        Resource = "arn:aws:logs:${var.region}:${var.aws_account_id}:log-group:/aws/*:*"
      },
      # Batch — observe + control (#914). Describe*/List* do NOT support
      # resource-level scoping (must be "*"); Cancel/Terminate act on transient
      # job IDs. REMOVED batch:UpdateComputeEnvironment + batch:UpdateJobQueue
      # (those resize compute upward — an infra-mgmt action Terraform performs
      # with its own creds, not something the ops/deployer role needs).
      {
        Effect = "Allow"
        Action = ["batch:DescribeJobs", "batch:ListJobs",
          "batch:DescribeJobQueues", "batch:DescribeComputeEnvironments",
          "batch:DescribeJobDefinitions", "batch:CancelJob",
        "batch:TerminateJob"]
        Resource = "*"
      },
      # Batch — submit only to qgi-* queues/definitions (#914: was SubmitJob on
      # "*", i.e. any queue in the account, bypassing the canary gate).
      {
        Effect = "Allow"
        Action = ["batch:SubmitJob"]
        Resource = [
          "arn:aws:batch:${var.region}:${var.aws_account_id}:job-queue/qgi-*",
          "arn:aws:batch:${var.region}:${var.aws_account_id}:job-definition/qgi-*",
        ]
      },
      # Athena — run queries (MSCK REPAIR, recipe engine debugging)
      {
        Effect = "Allow"
        Action = ["athena:StartQueryExecution", "athena:GetQueryExecution",
          "athena:GetQueryResults", "athena:StopQueryExecution",
          "athena:GetWorkGroup", "athena:UpdateWorkGroup",
        "athena:ListQueryExecutions"]
        Resource = "*"
      },
      # Glue — catalog access for Athena queries
      {
        Effect = "Allow"
        Action = ["glue:GetTable", "glue:GetTables", "glue:GetDatabase",
          "glue:GetPartitions", "glue:BatchCreatePartition", "glue:GetPartition",
        "glue:CreateTable", "glue:DeleteTable", "glue:UpdateTable"]
        Resource = "*"
      },
      # S3 — read/delete pipeline data lake objects (for e2e test resets)
      {
        Effect = "Allow"
        Action = ["s3:ListBucket", "s3:GetObject", "s3:DeleteObject", "s3:PutObject", "s3:HeadObject",
          "s3:GetBucketLocation", "s3:ListBucketMultipartUploads", "s3:AbortMultipartUpload",
        "s3:ListMultipartUploadParts", "s3:PutObjectAcl"]
        Resource = [
          "arn:aws:s3:::qgi-data-lake-${var.aws_account_id}",
          "arn:aws:s3:::qgi-data-lake-${var.aws_account_id}/*"
        ]
      },
      # SQS — purge DLQ for test resets
      {
        Effect   = "Allow"
        Action   = ["sqs:PurgeQueue", "sqs:GetQueueAttributes", "sqs:ListQueues"]
        Resource = "arn:aws:sqs:${var.region}:${var.aws_account_id}:qgi-*"
      },
      # DynamoDB — read run tracking table
      {
        Effect   = "Allow"
        Action   = ["dynamodb:Scan", "dynamodb:Query", "dynamodb:DeleteItem"]
        Resource = "arn:aws:dynamodb:${var.region}:${var.aws_account_id}:table/qgi-*"
      },
      # T12 #305 HIGH fix (2026-04-19): EC2 + SSM permission blocks removed.
      # These granted Resource="*" for ec2:StartInstances, ec2:StopInstances,
      # ssm:SendCommand — broad host-level access that pre-dates the #FAR-1
      # migration to Fargate Spot. The EC2 indicator-fetcher instance
      # (targeted by these perms) was deleted in 2026-04-08 and the role
      # has not needed these capabilities since. Leaving them on was a
      # dead-permission lateral-movement risk.
      #
      # If the indicator fetcher ever needs to talk to a non-Fargate worker
      # again, scope permissions to that specific resource ARN, not "*".
    ]
  })
}

# ---------------------------------------------------------------------------
# (Removed) EC2 Indicator Fetcher role/profile — Phase 1 now uses Fargate
# Spot tasks via #FAR-1. Roles deleted on next apply.
# ---------------------------------------------------------------------------
# #FAR-1: Fargate task roles for the Phase 1 indicator fetcher
#
# Two roles are required:
#  - Execution role: assumed by Fargate itself to pull the image from ECR
#    and ship logs to CloudWatch (the "infra plumbing" role).
#  - Task role: assumed by the code running INSIDE the container — this is
#    the IAM identity the fetcher script uses to talk to S3, DDB, Athena, etc.
# ---------------------------------------------------------------------------

# --- Execution role ---
resource "aws_iam_role" "fargate_execution" {
  name = "qgi-fargate-execution-role"

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

resource "aws_iam_role_policy_attachment" "fargate_execution_managed" {
  role       = aws_iam_role.fargate_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# --- Task role (the identity the fetcher script runs as) ---
resource "aws_iam_role" "fargate_indicator_fetcher_task" {
  name = "qgi-fargate-indicator-fetcher-task-role"

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

resource "aws_iam_role_policy" "fargate_indicator_fetcher_task" {
  name = "qgi-fargate-indicator-fetcher-task-policy"
  role = aws_iam_role.fargate_indicator_fetcher_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # S3 — read indicators.json + read existing parquet for hash compare + write fresh parquet
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:ListBucket",
        "s3:GetBucketLocation", "s3:HeadObject"]
        Resource = [var.data_lake_bucket_arn, "${var.data_lake_bucket_arn}/*"]
      },
      # DynamoDB — counter (decrement), tracker (PutItem), values mirror (#148)
      {
        Effect = "Allow"
        Action = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
        "dynamodb:Query", "dynamodb:BatchWriteItem", "dynamodb:BatchGetItem"]
        Resource = [
          var.indicator_table_arn,
          var.indicator_values_table_arn,
          var.pipeline_a_counter_table_arn,
        ]
      },
      # Athena — used to ALTER TABLE ADD PARTITION (#149)
      {
        Effect = "Allow"
        Action = ["athena:StartQueryExecution", "athena:GetQueryExecution",
        "athena:GetQueryResults", "athena:StopQueryExecution", "athena:GetWorkGroup"]
        Resource = "*"
      },
      # Glue — Athena needs Glue catalog access for ALTER TABLE
      {
        Effect = "Allow"
        Action = ["glue:GetDatabase", "glue:GetTable", "glue:GetTables",
          "glue:GetPartition", "glue:GetPartitions", "glue:BatchCreatePartition",
        "glue:CreatePartition", "glue:UpdateTable"]
        Resource = [
          "arn:aws:glue:${var.region}:${var.aws_account_id}:catalog",
          "arn:aws:glue:${var.region}:${var.aws_account_id}:database/qgi_data",
          "arn:aws:glue:${var.region}:${var.aws_account_id}:table/qgi_data/*",
        ]
      },
      # CloudWatch Logs — Fargate task application logs
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:${var.aws_account_id}:log-group:/aws/batch/*"
      },
    ]
  })
}

# ---------------------------------------------------------------------------
# EventBridge Scheduler — role to start the Step Functions execution
# ---------------------------------------------------------------------------
resource "aws_iam_role" "eventbridge_scheduler" {
  name = "qgi-eventbridge-scheduler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = {
          "aws:SourceAccount" = var.aws_account_id
        }
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "eventbridge_scheduler" {
  name = "qgi-eventbridge-scheduler-policy"
  role = aws_iam_role.eventbridge_scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["states:StartExecution"]
        Resource = [
          var.state_machine_arn != "" ? var.state_machine_arn : "arn:aws:states:${var.region}:${var.aws_account_id}:stateMachine:qgi-indicator-monthly-updater",
          var.fetch_state_machine_arn != "" ? var.fetch_state_machine_arn : "arn:aws:states:${var.region}:${var.aws_account_id}:stateMachine:qgi-indicator-data-refresher",
        ]
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# #417 Option C — OIDC role for qgi-frontend workflow_dispatch
#
# The `bake-country-risks.yml` workflow in AminAlAit/qgi-frontend assumes
# this role via OIDC to pull `dashboard/country-risks.json` from the
# data-lake bucket. Scope is intentionally narrow: s3:GetObject on the
# one key, nothing else. The workflow writes the file into its own repo
# checkout using GITHUB_TOKEN — no S3 write permission needed.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "github_actions_frontend_s3_read" {
  name = "github-actions-qgi-frontend-s3-read"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github_actions.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          # Allow the workflow from main or any workflow_dispatch caller
          # on the repo. Dispatch events from the Lambda carry a sub like
          # `repo:AminAlAit/qgi-frontend:ref:refs/heads/main` so matching
          # main is sufficient.
          "token.actions.githubusercontent.com:sub" = "repo:AminAlAit/qgi-frontend:ref:refs/heads/main"
        }
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "github_actions_frontend_s3_read" {
  name = "qgi-frontend-s3-read-policy"
  role = aws_iam_role.github_actions_frontend_s3_read.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject"]
      Resource = "${var.data_lake_bucket_arn}/dashboard/country-risks.json"
    }]
  })
}

# ---------------------------------------------------------------------------
# qgi-aws-tf#973 lane 2 — OIDC role for the TE fleet vintage sync workflow
#
# The `sync-te-fleet-vintage.yml` workflow in AminAlAit/qgi-frontend assumes
# this role via OIDC to `aws s3 sync` a new fleet vintage from
# `frontend-data/te-fleet-run-*/` into the repo. Scope is intentionally
# narrow: s3:ListBucket on the bake output prefix + s3:GetObject on the
# objects under it; no put/delete. The workflow writes the files into the
# checkout via GITHUB_TOKEN — no S3 write permission needed.
#
# The sub claim matches workflow_dispatch from main; the Lambda dispatches
# this workflow on the main branch ref so the sub matches.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "github_actions_frontend_te_fleet_sync" {
  name = "github-actions-qgi-frontend-te-fleet-sync"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github_actions.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = "repo:AminAlAit/qgi-frontend:ref:refs/heads/main"
        }
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "github_actions_frontend_te_fleet_sync" {
  name = "qgi-frontend-te-fleet-sync-policy"
  role = aws_iam_role.github_actions_frontend_te_fleet_sync.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:ListBucket"]
        # ListBucket is bucket-scoped; restrict the listing to the prefix via
        # the standard `s3:prefix` condition so the workflow can't enumerate
        # other folders of the data lake.
        Resource = var.data_lake_bucket_arn
        Condition = {
          StringLike = {
            "s3:prefix" = ["frontend-data/te-fleet-run-*"]
          }
        }
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${var.data_lake_bucket_arn}/frontend-data/te-fleet-run-*"
      },
    ]
  })
}
