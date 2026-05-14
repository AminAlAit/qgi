output "function_arn" {
  value       = aws_lambda_function.this.arn
  description = "The ARN of the Lambda function"
}

output "function_name" {
  value       = aws_lambda_function.this.function_name
  description = "The name of the Lambda function"
}

output "role_arn" {
  value       = aws_iam_role.this.arn
  description = "The ARN of the Lambda execution role"
}
