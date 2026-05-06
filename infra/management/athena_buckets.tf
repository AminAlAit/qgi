# ── Athena query-result buckets ───────────────────────────────────────────────
# Two buckets were auto-created by Athena console usage and accumulated data:
#
#   athena-query-results-783811616921         — used by Step Functions Phase 4
#                                               (MSCK REPAIR TABLE writes here)
#   aws-athena-query-results-783811616921-eu-central-1 — console artifact;
#                                               contains ~58 GiB of orphaned
#                                               CTAS temp tables (#71)
#
# Neither had lifecycle rules. We import them and add expiry to stop unbounded
# growth. The first bucket gets a 30-day rule (results are transient); the
# second gets 7 days (pure garbage, cleanup in progress).
#
# See: https://github.com/AminAlAit/qgi-aws-tf/issues/81

resource "aws_s3_bucket" "athena_results_pipeline" {
  bucket = "athena-query-results-${var.management_account_id}"
}

resource "aws_s3_bucket_lifecycle_configuration" "athena_results_pipeline" {
  bucket = aws_s3_bucket.athena_results_pipeline.id

  rule {
    id     = "expire-query-results"
    status = "Enabled"
    filter {}

    expiration {
      days = 30
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }
}

resource "aws_s3_bucket_public_access_block" "athena_results_pipeline" {
  bucket                  = aws_s3_bucket.athena_results_pipeline.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

# ── Console artifact bucket (58 GiB of orphaned CTAS temp tables) ─────────────

resource "aws_s3_bucket" "athena_results_console" {
  bucket = "aws-athena-query-results-${var.management_account_id}-eu-central-1"
}

resource "aws_s3_bucket_lifecycle_configuration" "athena_results_console" {
  bucket = aws_s3_bucket.athena_results_console.id

  rule {
    id     = "expire-console-results"
    status = "Enabled"
    filter {}

    expiration {
      days = 7
    }

    noncurrent_version_expiration {
      noncurrent_days = 3
    }
  }
}

resource "aws_s3_bucket_public_access_block" "athena_results_console" {
  bucket                  = aws_s3_bucket.athena_results_console.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}
