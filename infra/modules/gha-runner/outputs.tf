output "asg_name" {
  description = "Auto Scaling Group name."
  value       = aws_autoscaling_group.runner.name
}

output "launch_template_id" {
  description = "Launch template ID (diagnostic)."
  value       = aws_launch_template.runner.id
}

output "launch_template_latest_version" {
  description = "Latest version number of the launch template."
  value       = aws_launch_template.runner.latest_version
}

output "instance_profile_arn" {
  description = "IAM instance profile ARN attached to the runner instance."
  value       = aws_iam_instance_profile.runner.arn
}

output "instance_role_arn" {
  description = "IAM role ARN (for diagnostics — Session Manager policy lives here)."
  value       = aws_iam_role.runner.arn
}

output "security_group_id" {
  description = "Security group ID (outbound-only)."
  value       = aws_security_group.runner.id
}

output "runner_label" {
  description = "Label this runner advertises. Echo this back to workflow authors so `runs-on:` matches exactly."
  value       = var.runner_label
}
