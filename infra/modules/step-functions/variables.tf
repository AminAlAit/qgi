variable "name" {
  type        = string
  description = "Name of the Step Functions state machine"
}

variable "definition" {
  type        = string
  description = "JSON state machine definition"
}

variable "type" {
  type        = string
  default     = "STANDARD"
  description = "State machine type: STANDARD or EXPRESS"
}

variable "enable_logging" {
  type        = bool
  default     = false
  description = "Enable CloudWatch execution logging for the state machine"
}

variable "logging_level" {
  type        = string
  default     = "ERROR"
  description = "Execution logging level: ALL, ERROR, FATAL, or OFF"
}

variable "log_retention_days" {
  type        = number
  default     = 30
  description = "CloudWatch log retention in days"
}

variable "policy_arns" {
  type        = list(string)
  default     = []
  description = "List of IAM policy ARNs to attach to the state machine role"
}

variable "tags" {
  type        = map(string)
  default     = {}
  description = "Tags for the resources"
}
