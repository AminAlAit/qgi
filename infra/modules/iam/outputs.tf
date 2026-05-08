output "github_actions_lambda_deploy_role_arn" { value = aws_iam_role.github_actions_lambda_deploy.arn }
output "github_actions_ecr_push_role_arn" { value = aws_iam_role.github_actions_ecr_push.arn }
output "github_actions_frontend_s3_read_role_arn" { value = aws_iam_role.github_actions_frontend_s3_read.arn }
output "github_actions_frontend_te_fleet_sync_role_arn" { value = aws_iam_role.github_actions_frontend_te_fleet_sync.arn }
output "lambda_execution_role_arn" { value = aws_iam_role.lambda_execution.arn }
output "batch_job_role_arn" { value = aws_iam_role.batch_job.arn }
output "ecs_instance_profile_arn" { value = aws_iam_instance_profile.ecs_instance.arn }
output "stepfunctions_role_arn" { value = aws_iam_role.stepfunctions.arn }
output "eventbridge_scheduler_role_arn" { value = aws_iam_role.eventbridge_scheduler.arn }
output "cross_account_ops_role_arn" { value = aws_iam_role.cross_account_ops.arn }
# #FAR-1: Fargate roles for the Phase 1 indicator fetcher
output "fargate_execution_role_arn" { value = aws_iam_role.fargate_execution.arn }
output "fargate_indicator_fetcher_task_role_arn" { value = aws_iam_role.fargate_indicator_fetcher_task.arn }
# #425: Vercel frontend reader — read-only user for live Athena queries.
# Access keys are generated manually post-apply (not stored in TF state).
output "vercel_frontend_reader_user_name" { value = aws_iam_user.vercel_frontend_reader.name }
output "vercel_frontend_reader_user_arn" { value = aws_iam_user.vercel_frontend_reader.arn }
