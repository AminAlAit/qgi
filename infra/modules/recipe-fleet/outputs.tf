# ---------------------------------------------------------------------------
# Recipe-fleet module outputs
#
# GUESS / PLAN-TIME NOTES (flagged for founder review):
#
# 1. SFN Batch:SubmitJob permissions — the shared stepfunctions_role_arn
#    (from modules/iam/main.tf) grants Lambda:InvokeFunction + Athena +
#    S3 + states:StartExecution. It does NOT currently have
#    Batch:SubmitJob / Batch:DescribeJobs on qgi-recipe-fleet-queue. At
#    terraform plan / apply time this will succeed (IAM resources are
#    created), but at SFN *execution* time the SubmitJob call will fail
#    with AccessDenied.
#    Fix: add Batch:SubmitJob + Batch:DescribeJobs to qgi-stepfunctions-policy
#    in modules/iam/main.tf, scoped to the qgi-recipe-fleet-queue ARN.
#    Also add sqs:SendMessage on qgi-recipe-fleet-approval (for the
#    waitForTaskToken approval gate — the SFN role sends a message to the
#    approval queue to deliver the token to the founder).
#
# 2. waitForTaskToken SQS approval — the "Await Founder Approval" state
#    references a queue named "qgi-recipe-fleet-approval" which does NOT
#    exist in Terraform (not in modules/storage). At plan time this will
#    validate (the ARN is a string literal; TF does not validate SFN ASL
#    ARNs), but the SFN execution will fail at that state. Options:
#      a) Add an aws_sqs_queue resource for qgi-recipe-fleet-approval
#         (recommended — simple, audit-trail via DLQ).
#      b) Wire a different token-delivery mechanism (SNS email, Slack Lambda).
#      c) Accept the failure and implement send-task-success via CLI directly
#         by reading the token from CloudWatch logs or the canary result JSON.
#    The canary structural gate itself is correctly wired regardless.
#
# 3. ECR image — qgi-recipe-fleet:latest must be pushed before any Batch
#    job can execute. The ECR repo exists after apply; CI/CD pipeline must
#    push the image from qgi-pipeline/batch/recipe-fleet/ (to be created).
#    Job definition tolerates a missing image at registration time.
#
# 4. github-actions-qgi-ecr-push resource policy in modules/iam/main.tf
#    lists specific repo ARNs. Add
#    "arn:aws:ecr:${region}:${aws_account_id}:repository/qgi-recipe-fleet"
#    to the Resource list in aws_iam_role_policy.github_actions_ecr_push,
#    or CI pushes to qgi-recipe-fleet will 403.
#
# 5. SQS approval queue — create aws_sqs_queue.recipe_fleet_approval
#    (name = "qgi-recipe-fleet-approval") in modules/storage or inline
#    here before the first execution. The queue URL
#    https://sqs.{region}.{account}/qgi-recipe-fleet-approval is hardcoded
#    in the SFN definition's "Await Founder Approval" state.
# ---------------------------------------------------------------------------

output "compute_environment_arn" {
  value       = aws_batch_compute_environment.recipe_fleet_spot.arn
  description = "ARN of the recipe-fleet Spot compute environment"
}

output "job_queue_arn" {
  value       = aws_batch_job_queue.recipe_fleet.arn
  description = "ARN of the recipe-fleet Batch job queue"
}

output "job_queue_name" {
  value       = aws_batch_job_queue.recipe_fleet.name
  description = "Name of the recipe-fleet Batch job queue"
}

output "job_definition_arn" {
  value       = aws_batch_job_definition.recipe_fleet_walker.arn
  description = "ARN of the recipe-fleet-walker Batch job definition"
}

output "job_definition_name" {
  value       = aws_batch_job_definition.recipe_fleet_walker.name
  description = "Name of the recipe-fleet-walker Batch job definition"
}

output "ecr_repository_url" {
  value       = aws_ecr_repository.recipe_fleet.repository_url
  description = "ECR repository URL for the recipe-fleet container image"
}

output "recipe_fleet_job_role_arn" {
  value       = aws_iam_role.recipe_fleet_job.arn
  description = "ARN of the Batch job task role (no Athena)"
}

output "post_pass_lambda_arn" {
  value       = aws_lambda_function.recipe_fleet_post_pass.arn
  description = "ARN of the post-pass Lambda (stub; real code via CI/CD)"
}

output "state_machine_arn" {
  value       = aws_sfn_state_machine.recipe_fleet.arn
  description = "ARN of the recipe-fleet Step Functions state machine"
}

output "state_machine_name" {
  value       = aws_sfn_state_machine.recipe_fleet.name
  description = "Name of the recipe-fleet Step Functions state machine"
}
