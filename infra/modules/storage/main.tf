locals {
  bucket_name = "qgi-data-lake-${var.aws_account_id}"
}

# ---------------------------------------------------------------------------
# S3 — data lake
# ---------------------------------------------------------------------------
resource "aws_s3_bucket" "data_lake" {
  bucket = local.bucket_name
  tags   = var.tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id
  versioning_configuration {
    # #930: enabled so an accidental overwrite / bad pipeline write is recoverable
    # (the data lake's Parquet outputs take hours to regenerate; the $37 V-Dem
    # fix-and-retry incident needed manual reversal). Noncurrent versions are
    # bounded by the lifecycle rule below so storage cost stays minimal.
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  # Athena temp results — expire after 1 day (#593, tightened from #419's
  # 14 days, which itself was tightened from #69's 30 days). May 2026 S3
  # cost-spike forensic (cost spike occurred 2026-05-02; forensic run
  # 2026-05-03) revealed: median file size in this prefix is 100 BYTES
  # (Athena workgroup metadata), with thousands of tiny files
  # accumulating per script session. Athena CSV results are never
  # re-read after the originating session ends — the 14-day window was
  # pure cost overhead with no operational benefit. 1 day covers any
  # reasonable in-session re-fetch window. The `pipeline-B-scdi-finder/`
  # fragmentation problem is a separate ticket (#592 + #595).
  rule {
    id     = "expire-query-results"
    status = "Enabled"
    filter {
      prefix = "query_results/"
    }
    expiration {
      days = 1
    }
  }

  # #160: Quarantined parquet files — forensic backups from forced reruns.
  # Nobody looks at them after ~30 days. Move to Glacier IR after 90 days
  # (retrieval still instant, ~5x cheaper storage), delete after 180.
  rule {
    id     = "archive-quarantine"
    status = "Enabled"
    filter {
      prefix = "_quarantine/"
    }
    transition {
      days          = 90
      storage_class = "GLACIER_IR"
    }
    expiration {
      days = 180
    }
  }

  # #160: Abort incomplete multipart uploads after 1 day (prevents orphaned
  # partial uploads from accumulating storage cost).
  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }

  # #630 (QA audit 2026-05-07): S3 Inventory daily reports.
  # The aws_s3_bucket_inventory.data_lake resource (defined later in this
  # file) writes Parquet snapshots of bucket composition into
  # s3-inventory/. 30-day expiry keeps the rolling history bounded;
  # older snapshots stop being useful for cost-trend analysis past ~30d.
  rule {
    id     = "expire-s3-inventory"
    status = "Enabled"
    filter {
      prefix = "s3-inventory/"
    }
    expiration {
      days = 30
    }
  }

  # #627 (QA audit 2026-05-07): S3 server access logs MOVED to a
  # dedicated bucket (aws_s3_bucket.access_logs). New logs no longer
  # land here; see aws_s3_bucket.access_logs / lifecycle / logging below.
  #
  # Transitional rule for the ~119K legacy log files (37 GB) that
  # accumulated under s3-access-logs/ before the relocation. Keeping the
  # 7-day expiry on the legacy prefix lets them age out naturally.
  # Without this rule the legacy files would be permanently orphaned —
  # the original `expire-access-logs` rule covered them, and removing
  # it without a replacement would silently regress storage cost on
  # the very prefix this PR set out to clean up.
  #
  # Remove this rule in a follow-up PR once a Storage Lens / S3
  # Inventory report confirms the prefix is empty (~7 days post-apply).
  rule {
    id     = "expire-legacy-access-logs"
    status = "Enabled"
    filter {
      prefix = "s3-access-logs/"
    }
    expiration {
      days = 7
    }
  }

  # #623 (QA audit 2026-05-07): scdi-finder Batch job intermediate writes.
  #
  # pipeline-B-scdi-finder/tmp/ — per-indicator per-country Parquet files
  # written by the scdi-finder Batch job BEFORE compaction. Once the job
  # compacts output into scdis-compacted/, tmp/ files are dead weight with
  # zero business value. The Glue `scdis` table reads ONLY from
  # scdis-compacted/ (see aws_glue_catalog_table.scdis storage_descriptor
  # location above). As of the 2026-05-07 S3 audit these objects numbered
  # 1,632,851 — 91% of the entire bucket's object count. 3-day expiry gives
  # the Batch job ample runway: typical end-to-end scdi-finder run is < 1 day.
  rule {
    id     = "expire-scdi-tmp"
    status = "Enabled"
    filter {
      prefix = "pipeline-B-scdi-finder/tmp/"
    }
    expiration {
      days = 3
    }
  }

  # #623 (QA review 2026-05-07): NO lifecycle rule for the uncompacted
  # `pipeline-B-scdi-finder/scdis/` prefix.
  #
  # The 2026-05-07 audit flagged 18,115 objects (~67 GB) at this prefix as
  # "dead weight" because the Glue scdis table reads from scdis-compacted/
  # only. However, the founder override on 2026-05-04 mandates that these
  # originals be RETAINED INDEFINITELY as rollback insurance. The mandate
  # is documented in:
  #   - qgi-ml/scripts/compact_scdi_prefix.py (docstring lines 13-15)
  #   - qgi-ml/scripts/delete_scdi_originals.py (deprecated, hard-blocked)
  #
  # Adding a lifecycle rule here would silently violate that policy. If the
  # retention mandate is ever reversed, expire-scdi-raw can land in a
  # follow-up PR with the founder override documented in this comment.
  #
  # NOTE (#930, 2026-05-26): versioning on this bucket is already Enabled in AWS
  # and noncurrent-version expiration already exists on some rules out-of-band —
  # the TF code for this lifecycle_configuration is DRIFTED from AWS. Adding a
  # noncurrent-expiration rule here was reverted because a non-targeted apply
  # would also strip the existing (drifted) noncurrent settings. The lifecycle
  # drift reconciliation is its own ticket; do NOT apply this resource until the
  # code is reconciled to the live state.
}

# #597 + #627 (QA audit 2026-05-07): S3 server access logging.
#
# Original rationale (#597): logs enable post-hoc forensics on cost
# spikes — which IAM principal opened how many objects in which prefix.
# The May 2 2026 GET spike ($9.44 in one day) was diagnosable only via
# Cost Explorer aggregates without these logs.
#
# Architecture (#627, 2026-05-07): logs are now delivered to a DEDICATED
# `aws_s3_bucket.access_logs` bucket (qgi-access-logs-{account_id}),
# NOT self-logged into the data lake. The old self-logging pattern
# polluted the data lake with 119,375 access log files (37 GB at peak)
# which inflated object-count metrics and complicated cost attribution.
# AWS recommends target_bucket != source for production buckets.
#
# Cost: log generation is free, but the resulting PUTs and storage
# incur standard S3 charges (now on the dedicated bucket — separated
# from primary data cost attribution). Estimate ~$2-5/month total;
# storage capped by the 7-day lifecycle rule on the access_logs bucket.
# The paid S3 Request Metrics filter is NOT enabled; daily
# request-count visibility comes from S3 Storage Lens free tier (#594).
#
# Retention rationale (7 days): chosen for cost containment and because
# the upstream cause (#592 SCDI fragmentation) explains the bulk of
# cost spikes. If a future incident requires a longer forensic window,
# bump to 30d in the lifecycle rule on `aws_s3_bucket_lifecycle_configuration.access_logs` —
# storage stays trivial.
#
# Legacy logs: 119K files at the OLD `s3-access-logs/` prefix on this
# bucket are aged out by the `expire-legacy-access-logs` rule above
# (transitional, removable in a follow-up PR once the prefix confirms empty).
#
# Permission path: server access logging requires the logging service
# principal (logging.s3.amazonaws.com) to write to the target prefix.
# Default delivery uses the log-delivery-write canned ACL, but our
# bucket has block_public_acls=true + ignore_public_acls=true (see
# aws_s3_bucket_public_access_block) — that ACL grant is silently
# rejected. We instead grant the permission via the access_logs
# bucket's resource policy (`aws_s3_bucket_policy.access_logs`) with
# the modern ACL-free path: aws:SourceAccount + aws:SourceArn guard.
resource "aws_s3_bucket_logging" "data_lake" {
  bucket        = aws_s3_bucket.data_lake.id
  target_bucket = aws_s3_bucket.access_logs.id
  target_prefix = "qgi-data-lake/"

  # #627 (QA audit 2026-05-07): retargeted from self → dedicated
  # access_logs bucket. The old self-logging architecture polluted the
  # data lake with 119K log files (37 GB) at peak. The dedicated bucket
  # has its own 7-day lifecycle rule and a tighter bucket policy
  # (logging service principal only). Object-count and cost-attribution
  # metrics for the data lake are now clean.
  depends_on = [aws_s3_bucket_policy.access_logs]
}

# ---------------------------------------------------------------------------
# #627 (QA audit 2026-05-07): dedicated S3 server access logs bucket
# ---------------------------------------------------------------------------
# Replaces the old self-logging pattern (data lake → data lake). Reasons:
#
#  1. Pollution: at the May 5 peak the data lake held 65,848 access log
#     files (28.5 GB) on a single day. They expired after 7 days but
#     during retention they inflated object-count metrics, complicated
#     Cost Explorer attribution, and made any LIST operation against the
#     primary data prefixes more expensive.
#  2. Best practice: AWS recommends the target bucket be different from
#     the source for production buckets so that access-log delivery
#     never competes with user reads/writes for the same key namespace.
#  3. Cleaner forensics: scdi-finder partition scans no longer surface
#     access log keys in their query plans.
#
# Bucket name: qgi-access-logs-{aws_account_id}. Same naming convention
# as the data lake. No `prevent_destroy` because losing logs is
# acceptable; lifecycle keeps storage bounded at 7 days.
resource "aws_s3_bucket" "access_logs" {
  bucket = "qgi-access-logs-${var.aws_account_id}"
  tags   = var.tags

  # Forensic data may be the only evidence of a live incident in
  # progress. Mirroring the data_lake bucket's prevent_destroy ensures
  # symmetric durability protection — accidental `terraform destroy`
  # cannot wipe forensic logs mid-investigation.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "access_logs" {
  bucket = aws_s3_bucket.access_logs.id

  rule {
    id     = "expire-logs"
    status = "Enabled"
    filter {}
    expiration {
      days = 7
    }
  }

  # Abort orphaned multipart uploads — defensive; log delivery doesn't
  # use multipart but a future tooling change might.
  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

# Block public access. Logs contain IP addresses + IAM ARNs of every
# caller — they must never be world-readable.
resource "aws_s3_bucket_public_access_block" "access_logs" {
  bucket                  = aws_s3_bucket.access_logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Bucket policy: grant the S3 logging service principal write access,
# scoped to the qgi-data-lake/ prefix and this account only. ACL-free
# pattern (block_public_acls=true blocks the canned-ACL path that S3
# uses by default; we substitute a policy-based grant).
#
# This policy is INTENTIONALLY pinned to a single source bucket via
# `aws:SourceArn = aws_s3_bucket.data_lake.arn`. The target_prefix
# convention (`qgi-data-lake/`) was chosen so that future logging
# sources can land here under their own prefix (e.g. `qgi-ml-artifacts/`
# if that bucket ever gets server access logging). To extend coverage,
# add a SECOND statement with that source's ARN — do NOT relax the
# SourceArn condition (which would risk cross-bucket log injection
# from any compromised principal in this account).
resource "aws_s3_bucket_policy" "access_logs" {
  bucket = aws_s3_bucket.access_logs.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowS3LogDelivery"
        Effect    = "Allow"
        Principal = { Service = "logging.s3.amazonaws.com" }
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.access_logs.arn}/qgi-data-lake/*"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = var.aws_account_id
            # ARN of the source bucket — prevents a foreign bucket in
            # this account from delivering its logs here.
            "aws:SourceArn" = aws_s3_bucket.data_lake.arn
          }
        }
      }
    ]
  })
}

# Allow management account to write to this bucket (for legacy data
# sync) AND allow the S3 logging service principal to deliver server
# access logs to the s3-access-logs/ prefix (#597). Both statements
# live in one policy to keep policy management contained.
resource "aws_s3_bucket_policy" "data_lake_cross_account" {
  bucket = aws_s3_bucket.data_lake.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowManagementAccountSync"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${var.management_account_id}:root" }
        Action    = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.data_lake.arn,
          "${aws_s3_bucket.data_lake.arn}/*"
        ]
      },
      # #627 (QA audit 2026-05-07): the old AllowS3LogDelivery
      # statement was REMOVED from this policy because access logs are
      # now delivered to the dedicated `aws_s3_bucket.access_logs`
      # bucket. The ACL-free log-delivery grant lives in
      # `aws_s3_bucket_policy.access_logs` instead.
      {
        # #630 (QA review 2026-05-07): S3 Inventory delivery requires
        # an explicit bucket-policy grant when block_public_acls=true
        # (the canned-ACL path used by default Inventory delivery is
        # silently rejected by the public-access block, same mechanism
        # that affected #597 server access logging). Without this
        # statement, aws_s3_bucket_inventory.data_lake applies cleanly
        # but the inventory NEVER delivers — silent failure, no console
        # error. The s3:x-amz-acl condition mirrors the AWS-recommended
        # tightening: ensures the delivery call sets the bucket-owner-
        # full-control ACL header, preventing any other s3.amazonaws.com
        # action from using this statement to write arbitrary objects.
        Sid       = "AllowS3InventoryDelivery"
        Effect    = "Allow"
        Principal = { Service = "s3.amazonaws.com" }
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.data_lake.arn}/s3-inventory/*"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = var.aws_account_id
            "aws:SourceArn"     = aws_s3_bucket.data_lake.arn
            "s3:x-amz-acl"      = "bucket-owner-full-control"
          }
        }
      }
    ]
  })
}

resource "aws_s3_bucket_public_access_block" "data_lake" {
  bucket                  = aws_s3_bucket.data_lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---------------------------------------------------------------------------
# SQS — Phase A
# ---------------------------------------------------------------------------
resource "aws_sqs_queue" "a_dlq" {
  name                      = "qgi-pipeline-a-dlq"
  message_retention_seconds = 1209600 # 14 days
  tags                      = var.tags
}

resource "aws_sqs_queue" "a_main" {
  name                       = "qgi-pipeline-a-main-queue"
  visibility_timeout_seconds = 900
  message_retention_seconds  = 345600 # 4 days
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.a_dlq.arn
    maxReceiveCount     = 3
  })
  tags = var.tags
}

# ---------------------------------------------------------------------------
# SQS — Phase B  (Cascade/SCDI-exclusive — gated by enable_cascade)
# ---------------------------------------------------------------------------
# moved blocks: adding count requires state address to change from
#   module.storage.aws_sqs_queue.b_dlq   -> .b_dlq[0]
#   module.storage.aws_sqs_queue.b_main  -> .b_main[0]
moved {
  from = aws_sqs_queue.b_dlq
  to   = aws_sqs_queue.b_dlq[0]
}

moved {
  from = aws_sqs_queue.b_main
  to   = aws_sqs_queue.b_main[0]
}

resource "aws_sqs_queue" "b_dlq" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count                     = var.enable_cascade ? 1 : 0
  name                      = "qgi-pipeline-b-dlq"
  message_retention_seconds = 1209600
  tags                      = var.tags
}

resource "aws_sqs_queue" "b_main" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count                      = var.enable_cascade ? 1 : 0
  name                       = "qgi-pipeline-b-main-queue"
  visibility_timeout_seconds = 900
  message_retention_seconds  = 345600
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.b_dlq[0].arn
    maxReceiveCount     = 3
  })
  tags = var.tags
}

# ---------------------------------------------------------------------------
# SQS — Phase C  (Cascade/SCDI-exclusive — gated by enable_cascade)
# ---------------------------------------------------------------------------
# moved blocks: adding count requires state address to change from
#   module.storage.aws_sqs_queue.c_dlq   -> .c_dlq[0]
#   module.storage.aws_sqs_queue.c_main  -> .c_main[0]
moved {
  from = aws_sqs_queue.c_dlq
  to   = aws_sqs_queue.c_dlq[0]
}

moved {
  from = aws_sqs_queue.c_main
  to   = aws_sqs_queue.c_main[0]
}

resource "aws_sqs_queue" "c_dlq" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count                      = var.enable_cascade ? 1 : 0
  name                       = "qgi-pipeline-c-dlq"
  message_retention_seconds  = 1209600
  visibility_timeout_seconds = 900 # must be >= c-dlq-inspector Lambda timeout
  tags                       = var.tags
}

resource "aws_sqs_queue" "c_main" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count                      = var.enable_cascade ? 1 : 0
  name                       = "qgi-pipeline-c-main-queue"
  visibility_timeout_seconds = 900
  message_retention_seconds  = 345600
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.c_dlq[0].arn
    maxReceiveCount     = 3
  })
  tags = var.tags
}

# ---------------------------------------------------------------------------
# DynamoDB — indicator updates tracker (Phase A reporter)
# ---------------------------------------------------------------------------
resource "aws_dynamodb_table" "indicator_updates" {
  name         = "qgi-indicator-updates"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "run_id"
  range_key    = "indicator_id"

  attribute {
    name = "run_id"
    type = "S"
  }
  attribute {
    name = "indicator_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  # #929: guard the coordination table against accidental terraform destroy /
  # console delete. Additive — does not change runtime behaviour.
  deletion_protection_enabled = true

  tags = var.tags
}

# ---------------------------------------------------------------------------
# DynamoDB — indicator values (#148)
#
# Frontend latency fix: pattern detail pages issue an N+1 burst of Athena
# queries (one per indicator). Each cold-start adds 2-10s. With ~22 indicators
# per pattern that's 10-50s of cumulative latency. Migrating reads to DDB
# turns the entire batch into a single BatchGetItem (sub-second).
#
# Schema:
#   PK   indicator_country : S   (e.g. "SP.POP.TOTL#South Korea")
#   SK   year              : N
#   attr value             : N
#
# Access pattern: BatchGetItem with up to 100 keys per call. The frontend
# pre-computes the (indicator, country, year) tuples for the requested
# pattern window and fetches them all in one round trip.
#
# Capacity: PAY_PER_REQUEST (workload is bursty + small — total dataset is
# ~750k items, well within DDB free tier).
# ---------------------------------------------------------------------------
resource "aws_dynamodb_table" "indicator_values" {
  name         = "qgi-indicator-values"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "indicator_country"
  range_key    = "year"

  attribute {
    name = "indicator_country"
    type = "S"
  }
  attribute {
    name = "year"
    type = "N"
  }

  # #929: this is the frontend's primary read path (~750k items) — protect it
  # against accidental deletion and make a data-integrity incident recoverable.
  deletion_protection_enabled = true
  point_in_time_recovery {
    enabled = true
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# qgi-user-settings — per-user frontend profile settings (watchlist, default
# landing view, trend focus, methodology verbosity, analogue floor, …).
# Keyed on the signed-in user's email (both Google and Cognito users have one).
# Read + written by the frontend reader IAM user via server actions. Small,
# low-traffic (one item per user), PAY_PER_REQUEST. PITR on so a bad write is
# recoverable.
# ---------------------------------------------------------------------------
resource "aws_dynamodb_table" "user_settings" {
  # Gated so it only exists where the frontend auth/profile store is wired
  # (staging today). Mirrors the enable_cascade convention.
  count        = var.enable_user_settings ? 1 : 0
  name         = "qgi-user-settings"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "email"

  attribute {
    name = "email"
    type = "S"
  }

  # Live user data — match the guard on the other stateful tables (#929):
  # protect against accidental deletion + make a bad write recoverable.
  deletion_protection_enabled = true
  point_in_time_recovery {
    enabled = true
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# CloudWatch alarm — qgi-indicator-values write capacity surge guard (#157)
#
# 2026-04-08: a bug in pipeline-a-completer caused it to mirror every
# indicator on every pipeline run instead of just the changed ones.
# Result: ~1.77M DynamoDB writes in one day, $2.21 cost surge from a
# baseline of $0.0004/day. Fix shipped, but a defense-in-depth alarm
# is cheap insurance against the next regression.
#
# Threshold rationale: a healthy run mirrors at most ~24K writes
# (1-2 changed indicators × ~12K rows each). 100K writes in any single
# 5-min window is presumptively a bug. The alarm triggers on 2 of 2
# breaching periods to filter transient spikes from initial pipeline
# population runs.
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "indicator_values_write_surge" {
  alarm_name          = "qgi-indicator-values-write-surge"
  alarm_description   = "Triggers when qgi-indicator-values write capacity exceeds 100K units in a 5-min window. See #157 — guard against the completer mirroring all indicators instead of only updated ones."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ConsumedWriteCapacityUnits"
  namespace           = "AWS/DynamoDB"
  period              = 300
  statistic           = "Sum"
  threshold           = 100000
  treat_missing_data  = "notBreaching"

  dimensions = {
    TableName = aws_dynamodb_table.indicator_values.name
  }

  alarm_actions = [aws_sns_topic.pipeline_notifications.arn]
  ok_actions    = [aws_sns_topic.pipeline_notifications.arn]

  tags = var.tags
}

# ---------------------------------------------------------------------------
# DynamoDB — Phase 1 fetcher counter (#FAR-1)
#
# Replaces the legacy completion-counters table for Phase 1 specifically.
# The dispatcher Lambda seeds `pending=N` at run start; each Fargate Spot
# task decrements `pending` by 1 when it finishes (success OR graceful
# failure). The checker Lambda polls until pending <= 0, then advances
# to the Reporter.
#
# Why a dedicated table (not reusing qgi-completion-counters):
#  - Phase 1 has its own lifecycle and deadman timeout
#  - Phase 4 (qgi-completion-counters) uses a different schema (processed_c
#    counter that goes UP, not DOWN)
#  - Cleaner blast radius — a Phase 1 race can't corrupt Phase 4 state
#
# Schema:
#   PK   run_id   : S   (Step Function execution name)
#   attr pending  : N   (decrements from total to 0)
#   attr total    : N   (immutable, set by dispatcher, used by reporter)
#   attr expires_at : N (TTL — clean up old run records after 30 days)
# ---------------------------------------------------------------------------
resource "aws_dynamodb_table" "pipeline_a_counter" {
  name         = "qgi-pipeline-a-counter"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "run_id"

  attribute {
    name = "run_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  deletion_protection_enabled = true # #929 — losing this mid-run silently breaks the pipeline

  tags = var.tags
}

# ---------------------------------------------------------------------------
# DynamoDB — completion counters (D6: replaces Phase 1/4 hard waits)
# Dispatcher writes run_id + total worker count; each worker decrements.
# Not yet wired into Step Functions — Lambda code update required (issue #76).
# ---------------------------------------------------------------------------
resource "aws_dynamodb_table" "completion_counters" {
  name         = "qgi-completion-counters"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "run_id"

  attribute {
    name = "run_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  deletion_protection_enabled = true # #929

  tags = var.tags
}

# ---------------------------------------------------------------------------
# SNS — pipeline notifications (reporter + dlq-scanner)
# ---------------------------------------------------------------------------
resource "aws_sns_topic" "pipeline_notifications" {
  name = "qgi-monthly-updates"
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Glue — database
# ---------------------------------------------------------------------------
resource "aws_glue_catalog_database" "qgi_data" {
  name = "qgi_data"
}

# ---------------------------------------------------------------------------
# Glue — scdis table (Cascade/SCDI-exclusive — gated by enable_cascade)
# ---------------------------------------------------------------------------
# moved block: aws_glue_catalog_table.scdis -> scdis[0]
moved {
  from = aws_glue_catalog_table.scdis
  to   = aws_glue_catalog_table.scdis[0]
}

resource "aws_glue_catalog_table" "scdis" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count         = var.enable_cascade ? 1 : 0
  name          = "scdis"
  database_name = aws_glue_catalog_database.qgi_data.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "parquet.compress" = "SNAPPY"
    "classification"   = "parquet"
    "EXTERNAL"         = "TRUE"
  }

  storage_descriptor {
    location      = "s3://${local.bucket_name}/pipeline-B-scdi-finder/scdis-compacted/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      name                  = "parquet"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "1"
      }
    }

    columns {
      name = "country_b_id"
      type = "smallint"
    }
    columns {
      name = "length"
      type = "smallint"
    }
    columns {
      name = "start_year_a"
      type = "smallint"
    }
    columns {
      name = "start_year_b"
      type = "smallint"
    }
    columns {
      name = "correlation"
      type = "float"
    }
    columns {
      name = "indicator_numeric_id"
      type = "smallint"
    }
    # #461 (D7 plumbing): true when any year in either segment_a or
    # segment_b had `is_predicted=true` in indicators_completed. Pre-#461
    # rows have NULL; downstream consumers must coalesce to false.
    columns {
      name = "contains_predicted"
      type = "boolean"
    }
  }

  partition_keys {
    name = "country_a_id"
    type = "smallint"
  }
}

# ---------------------------------------------------------------------------
# Glue — dscdis table (Cascade/SCDI-exclusive — gated by enable_cascade)
# ---------------------------------------------------------------------------
# moved block: aws_glue_catalog_table.dscdis -> dscdis[0]
moved {
  from = aws_glue_catalog_table.dscdis
  to   = aws_glue_catalog_table.dscdis[0]
}
# DSCDI = Detrended Similar-Country Dynamic Indicator. Per the Phase 5 v0.0b
# unanimous CSD reconvene DECISION 2026-05-05, this table is ADDITIVE alongside
# scdis (not a replacement). The 6-way mini-Majles agreed on a two-pass
# computation for severe-CSD global-arc indicators (Class A): an undemeaned
# baseline and a common-factor-demeaned primary output, distinguished by the
# `is_demeaned` column. Class B (WGI-pre-normalized) and Class C (idiosyncratic)
# indicators are single-pass with `is_demeaned=false`.
#
# Schema is INTENTIONALLY NARROWER than `scdis`. SCDI is a windowed-segment
# search (FFT cross-correlation finds time-shifted analogues with specific
# segment lengths and start years). DSCDI is fundamentally different: it
# computes a single full-panel pairwise Pearson correlation across all
# common years per country pair. There is no segment, no window, no time
# shift. Therefore the SCDI columns `length`, `start_year_a`, `start_year_b`
# are SEMANTICALLY MEANINGLESS for DSCDI and are NOT in this schema. (Earlier
# Stage D drafts inherited these columns by copy-paste; they were dropped
# 2026-05-06 as part of the Stage F preflight per the 6-way mini-Majles
# methodology DECISION.)
#
# Two columns drive Phase 6 ablation queries and downstream EB framework
# architecture-note logic:
#   - `is_demeaned`: false for baseline (Pass 1) or Class B/C; true for
#     primary demeaned output (Pass 2). Phase 6 reads only `is_demeaned=true`
#     for the canonical DSCDI substrate; the `is_demeaned=false` rows are
#     preserved for Miriam's three-substrate ablation (SCDI + ADF-DSCDI-
#     undemeaned + ADF-DSCDI-demeaned).
#   - `indicator_class`: 'A' / 'B' / 'C' per the Stage C input spec taxonomy.
#     Allows Phase 6 to filter / stratify by class without rejoining to the
#     class-assignment manifest at query time.
#
# Glue table is created here at Stage D; the underlying S3 prefix is empty
# until Stage F (deferred to end-of-cascade-mandate test-run authorization).
# Athena queries against `qgi_data.dscdis` will return zero rows until then,
# which is the correct behavior — code that reads from this table must
# tolerate empty results during the cascade window. See:
#   - Stage C input spec: docs/specs/internal/ops/cascade-track/phase-5-v0.0b-stage-c-input-spec.md
#   - CSD reconvene DECISION: docs/specs/internal/majles/in-progress/2026-05-05_Ihsa_phase5-v0-0b-csd-reconvene_DECISION.md
#   - DSCDI module (the writer's library): qgi-pipeline/batch/dscdi-finder/src/dscdi_finder.py
resource "aws_glue_catalog_table" "dscdis" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count         = var.enable_cascade ? 1 : 0
  name          = "dscdis"
  database_name = aws_glue_catalog_database.qgi_data.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "parquet.compress" = "SNAPPY"
    "classification"   = "parquet"
    "EXTERNAL"         = "TRUE"
  }

  storage_descriptor {
    location      = "s3://${local.bucket_name}/pipeline-B-dscdi-finder/dscdis/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      name                  = "parquet"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "1"
      }
    }

    columns {
      name = "country_b_id"
      type = "smallint"
    }
    columns {
      name = "correlation"
      type = "float"
    }
    columns {
      name = "indicator_numeric_id"
      type = "smallint"
    }
    columns {
      name = "contains_predicted"
      type = "boolean"
    }
    # Stage D additions (per CSD reconvene DECISION):
    columns {
      name = "is_demeaned"
      type = "boolean"
    }
    columns {
      name = "indicator_class"
      type = "string"
    }
  }

  partition_keys {
    name = "country_a_id"
    type = "smallint"
  }
}

# ---------------------------------------------------------------------------
# Glue — dscdi_indicator_manifest table (Cascade/SCDI-exclusive — gated by enable_cascade)
# ---------------------------------------------------------------------------
# moved block: aws_glue_catalog_table.dscdi_indicator_manifest -> dscdi_indicator_manifest[0]
moved {
  from = aws_glue_catalog_table.dscdi_indicator_manifest
  to   = aws_glue_catalog_table.dscdi_indicator_manifest[0]
}
# One row per indicator processed by dscdi-finder. This is the Phase 6 EB
# framework's queryable substrate-quality surface — distinguishes the 4
# Class A demeaning_insufficient flagged indicators (FP.CPI.TOTL.ZG,
# NY.GDP.PCAP.CD, SH.DYN.MORT, SP.POP.TOTL per Stage E results) from the
# 105 indicators where the substrate is clean.
#
# Without this manifest, Phase 6 would have to either hardcode the flagged
# indicator IDs (brittle) or recompute mean_abs_pairwise_corr per indicator
# from the dscdis correlation rows at query time (expensive).
#
# Table is UNPARTITIONED. Each dscdi-finder Batch job writes a single 1-row
# Parquet file at `s3://{bucket}/pipeline-B-dscdi-finder/manifest/{indicator_id}.parquet`.
# Athena reads all files at the location prefix unioned. 109 indicators →
# 109 small files → ~10 KB total. No partition discovery needed; dots in
# indicator IDs (e.g., `FP.CPI.TOTL.ZG`) are valid in plain S3 object keys
# (only Hive partition VALUES are sensitive to dots).
#
# References:
#   - DSCDIResult dataclass: qgi-pipeline/batch/dscdi-finder/src/dscdi_finder.py
#   - Stage E completion report: docs/specs/internal/ops/cascade-track/results/phase-5-v0.0b-stage-e-completion.md
resource "aws_glue_catalog_table" "dscdi_indicator_manifest" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count         = var.enable_cascade ? 1 : 0
  name          = "dscdi_indicator_manifest"
  database_name = aws_glue_catalog_database.qgi_data.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "parquet.compress" = "SNAPPY"
    "classification"   = "parquet"
    "EXTERNAL"         = "TRUE"
  }

  storage_descriptor {
    location      = "s3://${local.bucket_name}/pipeline-B-dscdi-finder/manifest/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      name                  = "parquet"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "1"
      }
    }

    columns {
      name = "indicator_id"
      type = "string"
    }
    # from result.disposition.indicator_class on the DSCDIResult dataclass
    # (qgi-pipeline/batch/dscdi-finder/src/dscdi_finder.py — entrypoint
    # flattens this when constructing the manifest row).
    columns {
      name = "indicator_class"
      type = "string"
    }
    # from result.disposition.transform (same indirection note as above)
    columns {
      name = "transform"
      type = "string"
    }
    # bigint matches pandas int64 default for Python int columns; avoids
    # silent type drift when Athena/Glue reads the Parquet output.
    columns {
      name = "n_countries"
      type = "bigint"
    }
    # double (not float) so the Priya Stage C exit-gate threshold value
    # (0.25 boundary) is stored at full pandas float64 precision and
    # not silently downcast to FLOAT32 on Athena read. This is a
    # diagnostic-gate scalar, not a raw correlation value; precision
    # matters for Phase 6 architecture-note decisions.
    columns {
      name = "mean_abs_pairwise_corr"
      type = "double"
    }
    columns {
      name = "demeaning_applied"
      type = "boolean"
    }
    # Priya's Stage C exit gate flag — true when mean_abs_pairwise_corr
    # post-demeaning > 0.25 (Class A only; surfaces the 4 flagged indicators).
    columns {
      name = "demeaning_insufficient"
      type = "boolean"
    }
    # Reason demeaning was suppressed for an otherwise-Class-A indicator
    # (e.g., "no_transform_outlier" for NY.GDP.MKTP.KD.ZG which is already
    # a differenced series). Nullable string.
    #
    # PRODUCER CONTRACT: This column is derived AT WRITE TIME by the
    # dscdi-finder entrypoint (PR-3, qgi-pipeline) from indicator_id
    # membership in `OUTLIER_NO_TRANSFORM` / `OUTLIER_LOG_DIFFERENCE` etc.
    # `DSCDIResult` does not have a `suppressed_reason` field directly —
    # the dataclass exposes `demeaning_applied` (boolean), and the
    # entrypoint encodes the reason. PR-3 must include a unit test
    # asserting `suppressed_reason = 'no_transform_outlier'` for
    # NY.GDP.MKTP.KD.ZG and `suppressed_reason IS NULL` for indicators
    # where demeaning was actually applied.
    columns {
      name = "suppressed_reason"
      type = "string"
    }
  }
}

# ---------------------------------------------------------------------------
# Glue — patterns table (Cascade/SCDI-exclusive — gated by enable_cascade)
# ---------------------------------------------------------------------------
# moved block: aws_glue_catalog_table.patterns -> patterns[0]
moved {
  from = aws_glue_catalog_table.patterns
  to   = aws_glue_catalog_table.patterns[0]
}

resource "aws_glue_catalog_table" "patterns" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count         = var.enable_cascade ? 1 : 0
  name          = "patterns"
  database_name = aws_glue_catalog_database.qgi_data.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "parquet.compress" = "SNAPPY"
    "classification"   = "parquet"
    "EXTERNAL"         = "TRUE"
  }

  storage_descriptor {
    location      = "s3://${local.bucket_name}/pipeline-C-pattern-synthesizer/output/data/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      name                  = "parquet"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "1"
      }
    }

    columns {
      name = "pattern_id"
      type = "string"
    }
    columns {
      name = "country_b_id"
      type = "smallint"
    }
    columns {
      name = "length"
      type = "smallint"
    }
    columns {
      name = "start_year_a"
      type = "smallint"
    }
    columns {
      name = "start_year_b"
      type = "smallint"
    }
    columns {
      name = "indicator_count"
      type = "bigint"
    }
    columns {
      name = "avg_correlation"
      type = "double"
    }
    columns {
      name = "pattern_power_score"
      type = "double"
    }
    columns {
      name = "indicator_numeric_ids"
      type = "array<smallint>"
    }
    # #128: Pattern length tier (S/M/L/XL). Derived from `length` in the
    # Phase 4 INSERT. Must be the last non-partition column to match the
    # SELECT order in pipeline-c-worker.
    columns {
      name = "pattern_tier"
      type = "string"
    }
    # #461 (D7 plumbing): aggregated `OR(scdi.contains_predicted)` across
    # the SCDIs that contributed to this pattern. Pre-#461 rows have NULL;
    # the recipe-engine + frontend badge logic coalesces NULL to false.
    columns {
      name = "contains_predicted"
      type = "boolean"
    }
  }

  partition_keys {
    name = "country_a_id"
    type = "smallint"
  }
}

# ---------------------------------------------------------------------------
# Glue — indicators table (Phase 1 output, Parquet)
# ---------------------------------------------------------------------------
resource "aws_glue_catalog_table" "indicators" {
  name          = "indicators"
  database_name = aws_glue_catalog_database.qgi_data.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "parquet.compress" = "SNAPPY"
    "classification"   = "parquet"
    "EXTERNAL"         = "TRUE"
  }

  storage_descriptor {
    location      = "s3://${local.bucket_name}/pipeline-A-indicator-extractor/output/parquet/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      name                  = "parquet"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "1"
      }
    }

    columns {
      name = "country"
      type = "string"
    }
    columns {
      name = "year"
      type = "int"
    }
    columns {
      name = "value"
      type = "double"
    }
    # #348 V-Dem integration (#485): per-row provider attribution.
    # Legacy parquet (pre-#485) does not have this column; Athena returns
    # NULL for those rows. New writes (V-Dem ingest #487, future provider
    # ingestion scripts) populate "WB" / "FAO" / "VDEM" / "ILO" / "UCDP".
    # Backfill of legacy NULL rows happens implicitly on the next full
    # pipeline regeneration from source.
    columns {
      name = "provider"
      type = "string"
    }
  }

  partition_keys {
    name = "indicator_id"
    type = "string"
  }
}

# ---------------------------------------------------------------------------
# Glue — indicators_completed table (Phase 1.5 output, Parquet with is_predicted)
# ---------------------------------------------------------------------------
resource "aws_glue_catalog_table" "indicators_completed" {
  name          = "indicators_completed"
  database_name = aws_glue_catalog_database.qgi_data.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "parquet.compress" = "SNAPPY"
    "classification"   = "parquet"
    "EXTERNAL"         = "TRUE"
  }

  storage_descriptor {
    location      = "s3://${local.bucket_name}/pipeline-A-indicator-extractor/output/parquet-completed/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      name                  = "parquet"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "1"
      }
    }

    columns {
      name = "country"
      type = "string"
    }
    columns {
      name = "year"
      type = "int"
    }
    columns {
      name = "value"
      type = "double"
    }
    columns {
      name = "is_predicted"
      type = "boolean"
    }
  }

  partition_keys {
    name = "indicator_id"
    type = "string"
  }
}

# ---------------------------------------------------------------------------
# Glue — recipes_aggregated table (Cascade/SCDI-exclusive — gated by enable_cascade)
#
# Phase 5b.6.5 output: one row per L3 event_category (71 rows total). The
# Recipe-as-aggregated-fingerprint phase the audit found missing — founder's
# bullets 1, 2, 6 implemented as a real Athena CTAS scanning the deduped
# recipes view (#458) joined to patterns (for indicator IDs).
#
# Per Majles consult Decision 3 (carried OPPOSE 6-5): MVP property list
# extended from 3 to 11 to satisfy the council's calibration / uncertainty /
# coverage-bias / provenance pushback. See:
#   - docs/specs/internal/majles/2026-04-25_recipe_v2_majles_consult.md
#     (Decision 3 + Step 4 synthesis)
#   - docs/specs/internal/majles/2026-04-25_recipe_audit.md §4 (schema)
#
# This table is Terraform-managed (unlike `recipes` which goes through
# Athena CTAS) — V2.0's first-class object deserves explicit schema
# control so a producer-side regression fails LOUD on the next pipeline
# run rather than silently drifting.
# ---------------------------------------------------------------------------
# moved block: aws_glue_catalog_table.recipes_aggregated -> recipes_aggregated[0]
moved {
  from = aws_glue_catalog_table.recipes_aggregated
  to   = aws_glue_catalog_table.recipes_aggregated[0]
}

resource "aws_glue_catalog_table" "recipes_aggregated" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count         = var.enable_cascade ? 1 : 0
  name          = "recipes_aggregated"
  database_name = aws_glue_catalog_database.qgi_data.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "parquet.compress" = "SNAPPY"
    "classification"   = "parquet"
    "EXTERNAL"         = "TRUE"
  }

  storage_descriptor {
    location      = "s3://${local.bucket_name}/pipeline-recipe-aggregator/output/data/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      name                  = "parquet"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "1"
      }
    }

    # Core spec
    columns {
      name = "event_category"
      type = "string"
    }
    columns {
      name = "canonical_length"
      type = "smallint"
    }
    # Marcus + Roshani: dispersion alongside point estimate.
    columns {
      name = "length_distribution"
      type = "array<struct<length:smallint,count:bigint>>"
    }
    # Marcus + Roshani + Kwame: TF-IDF frequency, per-indicator CI, top-K=15.
    columns {
      name = "indicator_fingerprint"
      type = "array<struct<indicator_id:smallint,frequency:float,ci_lower:float,ci_upper:float,avg_corr_magnitude:float,tfidf_score:float>>"
    }
    # Amara: surface Eurocentric-data-skew as first-class property.
    columns {
      name = "coverage_bias_diagnostic"
      type = "struct<n_pairs:int,oecd_share:float,regional_concentration:array<struct<region:string,share:float>>>"
    }
    columns {
      name = "total_instances"
      type = "bigint"
    }
    columns {
      name = "n_distinct_country_pairs"
      type = "bigint"
    }
    # Ciaran: provenance for ops + drift detection.
    columns {
      name = "last_recomputed_at"
      type = "timestamp"
    }
    columns {
      name = "pipeline_version"
      type = "string"
    }
    # Nadia: schema-evolution discipline.
    columns {
      name = "schema_version"
      type = "smallint"
    }
    # #461 D7 plumbing inherited.
    columns {
      name = "contains_predicted"
      type = "boolean"
    }
  }

  # No partition keys: 71 rows total, partitioning is overkill.
}

# ---------------------------------------------------------------------------
# Glue — pattern_indicator_lookup table (Cascade/SCDI-exclusive — gated by enable_cascade)
#
# A thin projection of qgi_data.patterns containing only
# (pattern_id, indicator_numeric_ids) — ~50 MB compressed vs 64 GB for the
# full patterns table. The recipe-engine CTAS uses this as the JOIN target
# for the recipes_deduped → patterns join, replacing the 64 GB full-table
# scan with a ~50 MB scan (~90% cost reduction per invocation).
#
# Built by build_pattern_indicator_lookup_table() in
# pipeline-recipe-engine-finalize/lambda_function.py, which:
#   1. Clears s3://…/pattern-indicator-lookup/parquet/
#   2. INSERT INTO SELECT pattern_id, indicator_numeric_ids FROM patterns
#   3. Guarded by the same 60-min idempotency window as recipes_aggregated
#
# No partition key: the table is tiny (one row per pattern — estimated
# ~500K rows at 50 MB total). Full-table scans on the lookup are cheap;
# no partition pruning benefit.
# ---------------------------------------------------------------------------
# moved block: aws_glue_catalog_table.pattern_indicator_lookup -> pattern_indicator_lookup[0]
moved {
  from = aws_glue_catalog_table.pattern_indicator_lookup
  to   = aws_glue_catalog_table.pattern_indicator_lookup[0]
}

resource "aws_glue_catalog_table" "pattern_indicator_lookup" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count         = var.enable_cascade ? 1 : 0
  name          = "pattern_indicator_lookup"
  database_name = aws_glue_catalog_database.qgi_data.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "parquet.compress" = "SNAPPY"
    "classification"   = "parquet"
    "EXTERNAL"         = "TRUE"
  }

  storage_descriptor {
    location      = "s3://${local.bucket_name}/pattern-indicator-lookup/parquet/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      name                  = "parquet"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "1"
      }
    }

    columns {
      name = "pattern_id"
      type = "string"
    }
    columns {
      name = "indicator_numeric_ids"
      type = "array<smallint>"
    }
  }

  # No partition keys: the full table is ~50 MB; full scans are negligible.
}

# ---------------------------------------------------------------------------
# Glue — country_recipe_scores table (#463 Fork B Phase 5b.6.6)
#
# One row per (country, event_category) — ~89 × 71 = 6.3K rows total.
# Output of the Country-vs-Recipe Scoring Lambda: how does this country's
# current trajectory match the canonical Recipe for this event_category?
#
# Per Majles consult Decision 1 (11-0) + Decision 3 calibration requirement
# (Roshani / Nasrin: "calibration is not optional and is not deferred").
#
# Read by:
# - frontend `/signals/{country}` (all recipes for one country, sorted by score)
# - frontend `/signals/{country}/{slug}` (single (country, recipe) leaf)
# - frontend `/precedents/{slug}` ("currently flagged countries" section)
#
# No partitioning — table is small enough that full scans cost <0.01¢. The
# frontend queries are by country_id (signals pages) or event_category
# (precedents pages); both project well without partitioning.
# ---------------------------------------------------------------------------
resource "aws_glue_catalog_table" "country_recipe_scores" {
  name          = "country_recipe_scores"
  database_name = aws_glue_catalog_database.qgi_data.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "parquet.compress" = "SNAPPY"
    "classification"   = "parquet"
    "EXTERNAL"         = "TRUE"
  }

  storage_descriptor {
    location      = "s3://${local.bucket_name}/pipeline-recipe-scorer/output/data/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      name                  = "parquet"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "1"
      }
    }

    columns {
      name = "country_id"
      type = "smallint"
    }
    columns {
      name = "event_category"
      type = "string"
    }
    # Raw similarity in [0, 1] before calibration.
    columns {
      name = "similarity_raw"
      type = "float"
    }
    # Calibrated probability in [0, 1] via Platt or isotonic. This is the
    # number the frontend renders. Roshani's requirement.
    columns {
      name = "similarity_calibrated"
      type = "float"
    }
    # Sebastien's partial-coverage tolerance: how many of the fingerprint's
    # indicators were present in the country's data.
    columns {
      name = "indicators_matched"
      type = "smallint"
    }
    columns {
      name = "indicators_in_fingerprint"
      type = "smallint"
    }
    columns {
      name = "coverage_ratio"
      type = "float"
    }
    # When coverage < threshold (e.g. 30%), suppressed=true and the
    # frontend shows "insufficient indicator coverage" rather than a
    # potentially-misleading score.
    columns {
      name = "suppressed"
      type = "boolean"
    }
    columns {
      name = "suppression_reason"
      type = "string"
    }
    # #461 D7 plumbing inherited from the Recipe.
    columns {
      name = "contains_predicted"
      type = "boolean"
    }
    # Ciaran provenance.
    columns {
      name = "last_computed_at"
      type = "timestamp"
    }
    columns {
      name = "pipeline_version"
      type = "string"
    }
    columns {
      name = "calibration_mapping_version"
      type = "string"
    }
  }

  # No partition keys (~6.3K rows total).
}

# ---------------------------------------------------------------------------
# Glue — countries table (reference data, backed by CSV in S3)
# ---------------------------------------------------------------------------
resource "aws_glue_catalog_table" "countries" {
  name          = "countries"
  database_name = aws_glue_catalog_database.qgi_data.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "classification"         = "csv"
    "EXTERNAL"               = "TRUE"
    "skip.header.line.count" = "1"
  }

  storage_descriptor {
    # #370 — dedicated prefix, not the shared `input/` prefix. The latter
    # holds countries.csv alongside indicator_map*.csv files whose
    # 2-column schemas are NOT countries-shaped. Reading the whole
    # `input/` prefix produced 811 rows instead of 261 (pre-fix) and
    # created the 2026-04-20 Phase B crash where FAO m49 map values
    # ("Afghanistan") landed in the id column and broke a later integer
    # cast in the recipe engine.
    #
    # First attempt (2026-04-22) used a file-level URI
    # (`.../input/countries.csv`). Glue OpenCSVSerde rejected it —
    # Athena returned 0 rows. Falling back to a dedicated sibling prefix
    # `pipeline-A-indicator-extractor/countries/` containing ONLY
    # countries.csv; this prefix is not used for any other pipeline
    # input, so future uploads cannot pollute it.
    #
    # IMPORTANT sync note: the original countries.csv at
    # `pipeline-A-indicator-extractor/input/countries.csv` is still read
    # directly (outside Glue) by three Batch containers (scdi-finder,
    # indicator-fetcher, indicator-fetcher-fao). The file in the new
    # `countries/` prefix is a COPY. When countries.csv is updated,
    # both copies must be updated. See pitfalls.md "countries.csv
    # duplicated locations" for the sync playbook.
    location      = "s3://${local.bucket_name}/pipeline-A-indicator-extractor/countries/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      name                  = "csv"
      serialization_library = "org.apache.hadoop.hive.serde2.OpenCSVSerde"
      parameters = {
        "separatorChar" = ","
        "quoteChar"     = "\""
      }
    }

    dynamic "columns" {
      for_each = ["0_index_id", "id", "name_1", "name_2", "name_3", "name_4", "name_5",
        "name_6", "name_7", "name_8", "name_9", "name_10", "alpha_2", "alpha_3",
        "numeric_code", "name_11", "name_12", "name_13", "name_14", "name_15",
      "name_16", "name_17", "name_18", "name_19", "name_20"]
      content {
        name = columns.value
        type = "string"
      }
    }
  }
}

# ---------------------------------------------------------------------------
# Glue — events table (historical baseline events)
# ---------------------------------------------------------------------------
resource "aws_glue_catalog_table" "events" {
  name          = "events"
  database_name = aws_glue_catalog_database.qgi_data.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "parquet.compress" = "SNAPPY"
    "classification"   = "parquet"
    "EXTERNAL"         = "TRUE"
  }

  storage_descriptor {
    location      = "s3://${local.bucket_name}/events/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      name                  = "parquet"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "1"
      }
    }

    columns {
      name = "country_name"
      type = "string"
    }
    columns {
      name = "year"
      type = "smallint"
    }
    columns {
      name = "title"
      type = "string"
    }
    columns {
      name = "description"
      type = "string"
    }
    columns {
      name = "category"
      type = "string"
    }
    columns {
      name = "category_normalized"
      type = "string"
    }
    columns {
      name = "source"
      type = "string"
    }
  }

  partition_keys {
    name = "country_id"
    type = "smallint"
  }
}

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Glue — recipes table: pipeline-managed, NOT in Terraform (2026-04-22, #410)
#
# The recipes table is created + populated by the Phase 5b Layer 2 recipe
# engine via Athena CTAS (qgi-pipeline/lambdas/pipeline-recipe-engine-*).
# The pipeline owns the schema + partitions; Terraform does not.
#
# A prior version of this module defined aws_glue_catalog_table.recipes
# with a lifecycle ignore_changes workaround for partition_keys. That
# resource was never successfully imported into state because the AWS
# provider 5.x import step trips on:
#
#     Error: setting partition_keys:
#     Invalid address to set: []string{"partition_keys", "0", "parameters"}
#
# The provider tries to set partition_keys[0].parameters during refresh,
# but that attribute is not in the resource schema. A Glue catalog table
# created via Athena CTAS writes extra Parameters metadata into the
# partition column definition that Terraform cannot round-trip in 5.x.
#
# Re-adoption path (deferred): bump AWS provider to 6.x (separate ticket
# — breaking-change review needed across all qgi-infra modules), then
# terraform import module.storage.aws_glue_catalog_table.recipes
# "<account_id>:qgi_data:recipes". Until then, recipes stays out of state.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Athena workgroup
# ---------------------------------------------------------------------------
resource "aws_athena_workgroup" "qgi" {
  name          = "QGI-Lambda-Workgroup"
  force_destroy = true

  configuration {
    result_configuration {
      output_location = "s3://${local.bucket_name}/query_results/"
    }
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    # #142 cost guardrail: hard cap on data scanned per query.
    # 50 GB ≈ $0.25 per query at $5/TB. Any query exceeding this is
    # presumptively a bug (full-table scan on patterns/recipes without
    # partition pruning is the canonical example — that's how the 04-06
    # surge hit $18 in 3 hours from frontend dev). Athena aborts the
    # query immediately when this is exceeded; pipeline INSERTs are
    # well under this threshold (largest is ~few GB for SCDIs aggregation).
    #
    # Pipeline-side queries: cap is generous because Phase 2/4 INSERTs
    # legitimately scan multi-GB partitions during synthesis.
    # Frontend-side queries: cap forces frontend devs to use Children C/D
    # caches and pre-computed JSONs rather than direct SELECTs.
    bytes_scanned_cutoff_per_query = 50 * 1024 * 1024 * 1024 # 50 GiB

    engine_version {
      selected_engine_version = "Athena engine version 3"
    }
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# CloudWatch alarm — Athena cost guardrail (#142)
#
# 2026-04-06: ~$18 in 3 hours of frontend dev work, from full-table scans
# on patterns/recipes (each call 50–2000 GB). Children A+B fixed the
# worst client-side patterns; this alarm closes the loop with a fast
# feedback signal if anything regresses.
#
# Metric: AWS/Athena ProcessedBytes for the QGI workgroup. Threshold of
# 100 GB in any 5-min window means a single accidental full-scan or a
# burst of expensive queries fires the alarm immediately.
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "athena_processed_bytes_surge" {
  alarm_name          = "qgi-athena-processed-bytes-surge"
  alarm_description   = "Triggers when QGI Athena workgroup scans more than 100GB in a 5-min window. See #142 — guard against frontend or pipeline regressions doing unbounded full-table scans on patterns/recipes."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ProcessedBytes"
  namespace           = "AWS/Athena"
  period              = 300
  statistic           = "Sum"
  threshold           = 100 * 1024 * 1024 * 1024 # 100 GiB
  treat_missing_data  = "notBreaching"

  dimensions = {
    WorkGroup  = aws_athena_workgroup.qgi.name
    QueryState = "SUCCEEDED"
  }

  alarm_actions = [aws_sns_topic.pipeline_notifications.arn]
  ok_actions    = [aws_sns_topic.pipeline_notifications.arn]

  tags = var.tags
}

# ---------------------------------------------------------------------------
# qgi-aws-tf#806 (cost-incident-2026-05-16 follow-up): clone the Athena
# bytes-scanned alarm for the `primary` workgroup + add an SFN execution-
# duration alarm.
#
# Layer B of the 2026-05-16 forensic: the `primary` workgroup had no per-query
# cap (closed by #802 + CLI apply 2026-05-18). This alarm is the secondary
# detection layer — it fires when `primary` scans > 100 GB in a 5-min window
# regardless of whether the workgroup cap is enforced.
#
# The SFN duration alarm is the missing piece from the 2026-05-16 incident:
# the qgi-indicator-monthly-updater "cost-leak-verify-2gb" run took 17.5h
# with no alarm at any "this is taking too long" threshold. 2h is half of
# the new top-level TimeoutSeconds=14400 (4h) from #805 — gives a warning
# before the hard kill.
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "athena_processed_bytes_surge_primary" {
  alarm_name          = "qgi-athena-processed-bytes-surge-primary"
  alarm_description   = "Triggers when the Athena `primary` workgroup scans more than 100GB in a 5-min window. See qgi-aws-tf#806 (cost-incident-2026-05-16) — secondary detection layer beyond the per-query cap on `primary` from #802."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ProcessedBytes"
  namespace           = "AWS/Athena"
  period              = 300
  statistic           = "Sum"
  threshold           = 100 * 1024 * 1024 * 1024 # 100 GiB
  treat_missing_data  = "notBreaching"

  dimensions = {
    WorkGroup  = "primary"
    QueryState = "SUCCEEDED"
  }

  # Routes to cost_alerts (the alert path founder reads), NOT pipeline_notifications.
  alarm_actions = [aws_sns_topic.cost_alerts.arn]
  ok_actions    = [aws_sns_topic.cost_alerts.arn]

  tags = var.tags
}

# SFN duration alarm dropped per QA TF review of qgi-infra#26:
# `AWS/States ExecutionTime` is a TERMINAL metric — CloudWatch only emits
# it when an execution completes. A 2h threshold cannot fire DURING a
# pathological 17h run; the alarm would stay GREEN until completion, by
# which point `TimeoutSeconds=14400` (#805) has already killed the run
# at hour 4. The alarm as originally written defended against nothing
# that TimeoutSeconds doesn't already handle.
#
# Real in-flight monitoring would require a Lambda heartbeat polling
# `aws stepfunctions list-executions --status-filter RUNNING` and
# emitting a custom CloudWatch metric every 15 min. Filed as a follow-up
# to #806 — not in this PR. TimeoutSeconds is the binding guard for now.

# #625 / #632 (2026-05-10): Athena workgroup-level result reuse via
# `update-work-group` does NOT exist in the AWS API. The original #625
# null_resource that called `aws athena update-work-group --configuration-updates
# '{"ResultReuseConfiguration":...}'` was based on a misunderstanding —
# verified against AWS CLI 2.15.50 + botocore 1.40.x: `ResultReuseConfiguration`
# is not a valid `ConfigurationUpdates` key.
#
# `ResultReuseConfiguration` is a PER-QUERY parameter on `StartQueryExecution`,
# not a workgroup-level default. The actual cost-saving fix lives in the
# frontend (qgi-frontend/lib/athena.ts:runQuery) — see #632 for the followup
# ticket that proposes adding the per-query parameter to all callers.
#
# This block was the broken null_resource. Removed 2026-05-10 so future
# `terraform apply` runs do not retry the failing local-exec.

# ---------------------------------------------------------------------------
# #594: Daily S3 cost alert via AWS Budgets (FREE: 2 budgets/account allowed)
# ---------------------------------------------------------------------------
#
# May 2 2026 had a $10.14 S3 cost spike that was completely invisible until
# the bill arrived 24+ hours later. This budget alerts the moment Cost
# Explorer detects S3 spend > $3 in a single day, giving us same-day signal
# vs. the prior end-of-week surprise.
#
# Why AWS Budgets instead of CloudWatch alarm on S3 request count:
#   - The alarm path requires S3 Storage Lens Advanced tier (~$0.36/mo for
#     1.8M-object bucket) since the FREE Storage Lens tier does not expose
#     GetRequests/PutRequests/AllRequests. Founder constraint is explicitly
#     ZERO new ongoing cost — Budgets is the only $0 path that catches the
#     spike same-day. (QA research 2026-05-03 documented full trade-off.)
#   - Budgets alerts on dollar cost (the actual harm signal), not request
#     count. More directly actionable.
#   - 2 budgets per account are FREE; we use 1.
#
# Threshold rationale: $3/day picks up the May 2 incident ($10.14) cleanly
# and stays above QGI's typical daily S3 spend of ~$0.30. Tunable via
# var if needed for QA/prod.
#
# Latency: Cost Explorer cost data lags ~12-24h. The budget fires when AWS
# detects daily spend crossing the threshold — typically next-morning
# rather than real-time. This is the same lag we'd get from CloudWatch
# request metrics anyway (S3 request metrics are also daily).

resource "aws_sns_topic" "cost_alerts" {
  name         = "qgi-${var.environment}-cost-alerts"
  display_name = "QGI Cost Alerts"
  tags         = var.tags
}

# Permission for AWS Budgets to publish to this SNS topic. Without this,
# Budgets' Publish call is silently denied — Budgets does NOT surface a
# permission error in the console; alarms simply don't fire.
#
# The aws:SourceAccount condition prevents the confused-deputy attack
# (per AWS 2023+ guidance for Budgets→SNS). Without it, a Budget in any
# AWS account could legitimately publish to this topic if they happen
# to know its ARN. Mirrors the pattern used by AllowS3LogDelivery
# on aws_s3_bucket_policy.access_logs (in the same module, #627).
resource "aws_sns_topic_policy" "cost_alerts" {
  arn = aws_sns_topic.cost_alerts.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowBudgetsToPublish"
        Effect    = "Allow"
        Principal = { Service = "budgets.amazonaws.com" }
        Action    = "SNS:Publish"
        Resource  = aws_sns_topic.cost_alerts.arn
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = var.aws_account_id
          }
        }
      },
      {
        # qgi-aws-tf#806 — let CloudWatch alarms publish to cost_alerts.
        # Without this, the athena_processed_bytes_surge_primary alarm (and
        # any future cost-routed alarm) would silently fail with AccessDenied
        # from the topic policy while showing ALARM state in CloudWatch —
        # the EXACT trap from the 2026-05-16 incident (broken alert path).
        Sid       = "AllowCloudWatchToPublish"
        Effect    = "Allow"
        Principal = { Service = "cloudwatch.amazonaws.com" }
        Action    = "SNS:Publish"
        Resource  = aws_sns_topic.cost_alerts.arn
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = var.aws_account_id
          }
        }
      },
      {
        # qgi-aws-tf#804 — let AWS Cost Anomaly Detection publish to cost_alerts.
        # The Cost Anomaly monitor + subscription were created via CLI on
        # 2026-05-18 (live in account 771606957899 as
        # arn:aws:ce::771606957899:anomalymonitor/24d55ff2-... and
        # arn:aws:ce::771606957899:anomalysubscription/c01e1ff6-...).
        # Codifying the principal here so subsequent Terraform applies on the
        # topic policy don't overwrite it. The monitor + subscription
        # themselves remain drift-only pending import (follow-up to #810).
        Sid       = "AllowCostAnomalyDetectionToPublish"
        Effect    = "Allow"
        Principal = { Service = "costalerts.amazonaws.com" }
        Action    = "SNS:Publish"
        Resource  = aws_sns_topic.cost_alerts.arn
      }
    ]
  })
}

# Daily S3 cost budget. Fires SNS notification when single-day actual spend
# crosses $3. Uses ACTUAL (not forecasted) so we react to real charges,
# not predictions (FORECASTED would create false positives on bursty
# pipeline runs).
resource "aws_budgets_budget" "s3_daily" {
  name         = "qgi-${var.environment}-s3-daily"
  budget_type  = "COST"
  limit_amount = "3.00"
  limit_unit   = "USD"
  time_unit    = "DAILY"

  cost_filter {
    name   = "Service"
    values = ["Amazon Simple Storage Service"]
  }

  notification {
    comparison_operator = "GREATER_THAN"
    # 100% of the $3.00 limit = fires at >= $3.00 actual spend.
    # Threshold is a PERCENTAGE of limit_amount, not a raw dollar value.
    threshold                 = 100
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_sns_topic_arns = [aws_sns_topic.cost_alerts.arn]
  }

  tags = var.tags

  # Topic policy must be attached BEFORE Budgets tries to publish.
  # Terraform cannot infer this from the topic-arn reference alone
  # (the policy is a side-effect on the topic, not a return value).
  depends_on = [aws_sns_topic_policy.cost_alerts]
}

# To get email or other notifications when this fires, add an
# aws_sns_topic_subscription pointing at qgintelligence@gmail.com (the QGI
# ops alarm inbox). Subscriptions require email
# confirmation outside Terraform — left out of this module to avoid
# imperatively triggering confirmation flows. Add per-environment in the
# environments/*/main.tf if desired.


# ---------------------------------------------------------------------------
# FLEET-9 / trio Condition F — $100/day account cost guard (recipe-fleet fan-out).
# ---------------------------------------------------------------------------
# Founder-set $100 hard ceiling for a recipe-fleet run (2026-05-27). Two layers:
#   (1) STRUCTURAL HARD CAP (the real enforcement, in the Batch layer, not here):
#       the fleet compute env's max_vcpus bounds the worst-case burn — no Spot-retry
#       storm can exceed it. Invariant FLEET-4 must preserve (PR #33 review: a job runs
#       up to attempts × attempt_duration of billed vCPU — the attempts=2 retry DOUBLES
#       it — and the SFN 40h ceiling does NOT kill running Batch jobs):
#         max_vcpus × attempts × attempt_duration_h × ~$0.05 <= $100
#       Today: 16 × 2 × 36 h × $0.05 ≈ $58. To reach max_vcpus=48 FLEET-4 must also cut
#       attempt_duration to 18 h (48 × 2 × 18 × 0.05 ≈ $86). See modules/recipe-fleet/main.tf.
#   (2) THIS MONITOR — a DAILY ACTUAL $100 account budget that pages cost_alerts
#       at 80% (early warning) and 100% (ceiling hit). Account-wide (staging is a
#       dedicated account; the fleet is the dominant spender) so it also catches
#       anything the structural cap can't see. ACTUAL, not FORECASTED, to avoid
#       false positives on bursty fan-out launches.
# A budget ACTION (auto-disable) is deliberately NOT used: applying a deny IAM
# policy / SCP from a budget breach has real blast-radius risk and is strictly
# weaker than the structural max_vcpus cap, which cannot be outrun in the first place.
resource "aws_budgets_budget" "fleet_daily_100" {
  name         = "qgi-${var.environment}-fleet-daily-100"
  budget_type  = "COST"
  limit_amount = "100.00"
  limit_unit   = "USD"
  time_unit    = "DAILY"

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 80 # early warning at $80 actual
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_sns_topic_arns = [aws_sns_topic.cost_alerts.arn]
  }
  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 100 # ceiling hit at $100 actual
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_sns_topic_arns = [aws_sns_topic.cost_alerts.arn]
  }

  tags       = var.tags
  depends_on = [aws_sns_topic_policy.cost_alerts]
}

# Deliver cost_alerts to the QGI ops inbox (PR #33 review: without a subscriber BOTH
# this budget and s3_daily fire into a void — the broken-alert-path failure mode behind
# the 2026-05-16 $139 incident). Email subs are created PENDING and require a one-time
# out-of-band click in the confirmation email; ignore_changes keeps re-applies from
# churning a confirmed sub. qgintelligence@gmail.com is the ops-alarm inbox (NOT personal).
resource "aws_sns_topic_subscription" "cost_alerts_email" {
  topic_arn = aws_sns_topic.cost_alerts.arn
  protocol  = "email"
  endpoint  = "qgintelligence@gmail.com"
  lifecycle {
    ignore_changes = [endpoint]
  }
}


# ---------------------------------------------------------------------------
# #630 (QA audit 2026-05-07): S3 Inventory
# ---------------------------------------------------------------------------
# Daily Parquet snapshot of the data lake bucket (key, size, storage class,
# last-modified, etag). Catches new object-count hotspots BEFORE they become
# cost spikes — which was exactly how the May 5 audit found the 1.63M
# objects under pipeline-B-scdi-finder/tmp/.
#
# Cost: ~$0.0025 per 1M objects/day. At 1.78M objects = ~$0.005/day = ~$0.15/month.
# Plus minor Parquet storage (~$0.01/month for 30 days at small report size).
#
# The output will be queryable via Athena once a Glue table is defined
# for the inventory output (NOT in this PR — schema depends on actual
# delivered Parquet structure; add in a follow-up after the first
# inventory report lands). Until then, the example query below will
# fail with "Table not found"; the inventory WILL deliver, just won't
# be queryable via Athena yet. Once the Glue table exists:
#
#   SELECT regexp_extract(key, '^([^/]+/)') AS top_prefix, COUNT(*) AS n
#   FROM qgi_data.s3_inventory_data_lake
#   WHERE dt = cast(current_date as varchar)
#   GROUP BY 1 ORDER BY n DESC LIMIT 20;
#
# We send the inventory output INTO the data lake bucket itself under
# s3-inventory/, then expire it via a new lifecycle rule (30 days). This
# avoids a separate bucket; the inventory keys are flat Parquet files
# whose presence does not pollute primary-data prefixes.
resource "aws_s3_bucket_inventory" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id
  name   = "daily-inventory"

  included_object_versions = "Current"

  schedule {
    frequency = "Daily"
  }

  destination {
    bucket {
      format     = "Parquet"
      bucket_arn = aws_s3_bucket.data_lake.arn
      prefix     = "s3-inventory/"
      account_id = var.aws_account_id
    }
  }

  optional_fields = ["Size", "LastModifiedDate", "StorageClass", "ETag"]
}

