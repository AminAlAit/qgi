variable "repo" {
  description = "GitHub repository slug (e.g. AminAlAit/qgi-frontend). The runner registers to this single repo."
  type        = string
}

variable "runner_label" {
  description = "Custom label the runner advertises (e.g. qgi-frontend). Workflows match via `runs-on: [self-hosted, <label>]`. MUST exactly match the label string used by every workflow that targets this runner."
  type        = string
}

variable "runner_pat_secret_name" {
  description = "AWS Secrets Manager secret name holding the fine-grained PAT used by cloud-init to mint a short-lived runner-registration token. The secret value is a plain string."
  type        = string
}

variable "subnet_id" {
  description = "VPC subnet (private preferred — outbound NAT to GitHub + S3 is sufficient)."
  type        = string
}

variable "vpc_id" {
  description = "VPC ID for the runner security group."
  type        = string
}

variable "instance_type" {
  description = "Spot Graviton instance type. Default sized for the workload (git + s3 sync + gh CLI; CPU-light, network-bound)."
  type        = string
  default     = "c7g.medium"
}

variable "spot_max_price" {
  description = "Maximum Spot price per instance-hour. Leave null for the on-demand-equivalent cap. (QA nit: empty string causes perpetual plan diffs against the provider.)"
  type        = string
  default     = null
}

variable "tags" {
  description = "Standard QGI tags applied to all created resources."
  type        = map(string)
  default     = {}
}

variable "desired_capacity" {
  description = <<-EOT
    How many runners to keep warm.

    0 = switched off but fully restorable: the launch template, IAM role, PAT
    secret and this module's config all remain. Flip back to 1 and apply to get
    a runner in ~2 minutes.

    Set to 0 for qgi-frontend on 2026-08-28: measured over 14 days the runner
    showed 0.4% mean CPU and not one hour above 20% - it was idling 24/7 at
    ~$17.30/month. This is a Terraform variable rather than a console change
    because the ASG is managed here; changing desired capacity in the console
    would be silently reverted by the next apply.
  EOT
  type        = number
  default     = 1

  validation {
    condition     = var.desired_capacity >= 0 && var.desired_capacity <= 1
    error_message = "desired_capacity must be 0 or 1; max_size for this ASG is 1."
  }
}

variable "name_prefix" {
  description = "Prefix for created resource names. Defaults to a deterministic value derived from `runner_label`."
  type        = string
  default     = ""
}
