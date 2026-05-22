variable "function_name" {
  type        = string
  description = "Name of the Lambda function"
}

variable "description" {
  type        = string
  default     = ""
  description = "Description of the Lambda function"
}

variable "package_type" {
  type        = string
  default     = "Zip"
  description = "Lambda package type: Zip or Image"
}

variable "image_uri" {
  type        = string
  default     = null
  description = "ECR Image URI if package_type is Image"
}

variable "filename" {
  type        = string
  default     = null
  description = "Path to zip file if package_type is Zip"
}

variable "source_code_hash" {
  type        = string
  default     = null
  description = "Base64-encoded SHA256 hash of the zip file"
}

variable "handler" {
  type        = string
  default     = "lambda_function.lambda_handler"
  description = "Lambda handler string"
}

variable "runtime" {
  type        = string
  default     = "python3.11"
  description = "Lambda runtime"
}

variable "architectures" {
  type        = list(string)
  default     = ["arm64"]
  description = "Instruction set architecture (arm64 or x86_64)"
}

variable "memory_size" {
  type        = number
  default     = 512
  description = "Memory size allocated to Lambda in MB"
}

variable "timeout" {
  type        = number
  default     = 300
  description = "Execution timeout in seconds"
}

variable "log_retention_days" {
  type        = number
  default     = 30
  description = "CloudWatch log retention in days"
}

variable "environment_variables" {
  type        = map(string)
  default     = {}
  description = "Environment variables for the function"
}

variable "policy_arns" {
  type        = list(string)
  default     = []
  description = "Additional IAM policy ARNs to attach to the execution role"
}

variable "tags" {
  type        = map(string)
  default     = {}
  description = "Tags for the resources"
}
