variable "bucket_name" {
  type        = string
  description = "Name of the S3 lakehouse bucket"
}

variable "force_destroy" {
  type        = bool
  default     = false
  description = "Whether all objects should be deleted when bucket is destroyed"
}

variable "versioning_enabled" {
  type        = bool
  default     = true
  description = "Enable versioning for S3 bucket"
}

variable "kms_key_arn" {
  type        = string
  default     = null
  description = "KMS Key ARN for S3 SSE-KMS encryption. If null, AES256 is used."
}

variable "bucket_key_enabled" {
  type        = bool
  default     = true
  description = "Enable S3 Bucket Key for reduced KMS costs"
}

variable "enforce_tls" {
  type        = bool
  default     = true
  description = "Enforce TLS-only in-transit transport"
}

variable "lifecycle_rules" {
  type        = any
  default     = []
  description = "List of lifecycle rules for objects"
}

variable "tags" {
  type        = map(string)
  default     = {}
  description = "Tags to attach to resources"
}
