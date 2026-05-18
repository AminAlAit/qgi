output "function_name" {
  value       = aws_lambda_function.poller.function_name
  description = "Name of the live-pulse poller Lambda."
}

output "function_arn" {
  value       = aws_lambda_function.poller.arn
  description = "ARN of the live-pulse poller Lambda."
}

output "schedule_name" {
  value       = aws_scheduler_schedule.hourly.name
  description = "Name of the hourly EventBridge schedule."
}

output "dlq_url" {
  value       = aws_sqs_queue.dlq.url
  description = "URL of the poller's dead-letter queue."
}

output "role_arn" {
  value       = aws_iam_role.poller.arn
  description = "Execution role ARN (scoped to the dashboard keys)."
}
