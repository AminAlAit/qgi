output "role_arn" {
  value       = aws_iam_role.this.arn
  description = "The ARN of the GitHub Actions OIDC role"
}

output "role_name" {
  value       = aws_iam_role.this.name
  description = "The name of the GitHub Actions OIDC role"
}
