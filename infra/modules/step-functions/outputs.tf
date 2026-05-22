output "state_machine_arn" {
  value       = aws_sfn_state_machine.this.arn
  description = "ARN of the Step Functions state machine"
}

output "state_machine_id" {
  value       = aws_sfn_state_machine.this.id
  description = "ID of the Step Functions state machine"
}

output "role_arn" {
  value       = aws_iam_role.this.arn
  description = "ARN of the IAM role assumed by the state machine"
}
