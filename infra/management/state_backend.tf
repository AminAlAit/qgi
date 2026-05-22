# ---------------------------------------------------------------------------
# Terraform State Backend Resources
#
# These resources were bootstrapped manually (closes #18) and are now
# imported into Terraform management (closes #38).
#
# Hardening applied:
#   - TLS-only bucket policy                    (closes #37)
#   - Noncurrent version expiry lifecycle rule  (closes #39)
#   - Deletion protection on DynamoDB table     (already active, closes #40)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# S3 bucket (imported)
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "tf_state" {
  bucket = "qgi-aws-tf-state-${var.management_account_id}"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

# TLS-only access (closes #37)
resource "aws_s3_bucket_policy" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyNonTLS"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.tf_state.arn,
          "${aws_s3_bucket.tf_state.arn}/*",
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
}

# Expire old noncurrent state versions after 90 days (closes #39)
resource "aws_s3_bucket_lifecycle_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    filter {} # apply to all objects

    noncurrent_version_expiration {
      noncurrent_days = 90
    }

    noncurrent_version_transition {
      noncurrent_days = 30
      storage_class   = "STANDARD_IA"
    }
  }
}

# ---------------------------------------------------------------------------
# DynamoDB state lock table (imported)
# Deletion protection is already enabled on the live table (closes #40)
# ---------------------------------------------------------------------------

resource "aws_dynamodb_table" "tf_state_lock" {
  name         = "qgi-aws-tf-state-lock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  deletion_protection_enabled = true

  lifecycle {
    prevent_destroy = true
  }
}
