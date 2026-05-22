terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}

# All resources deploy into the qgi-staging account.
#
# #96: assume_role is now toggleable via var.use_cross_account_assume_role.
# Default (false) = caller credentials are used directly. Set to true when
# running from the management account to cross-account into staging.
provider "aws" {
  region = "eu-central-1"

  dynamic "assume_role" {
    for_each = var.use_cross_account_assume_role ? [1] : []
    content {
      role_arn     = "arn:aws:iam::${var.aws_account_id}:role/OrganizationAccountAccessRole"
      session_name = "terraform-qgi-${var.environment}"
    }
  }

  default_tags {
    tags = local.tags
  }
}
