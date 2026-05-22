variable "environment" {
  type        = string
  description = "Deployment environment (staging | qa | prod)."
}

variable "aws_account_id" {
  type        = string
  description = "Target AWS account id for this environment."
}

variable "region" {
  type        = string
  default     = "eu-central-1"
  description = "AWS region. MUST match the frontend's AWS_REGION — the Cognito issuer URL (and thus NextAuth's JWKS/JWT verification) is derived from it."
}

variable "password_minimum_length" {
  type        = number
  default     = 10
  description = "Minimum password length for the user pool policy."
}

variable "tags" {
  type        = map(string)
  description = "Resource tags (Project/Environment/ManagedBy/Owner), passed from the env's local.tags."
}
