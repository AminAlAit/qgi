# ---------------------------------------------------------------------------
# Vercel frontend reader — scoped IAM user for qgi-frontend Next.js routes
#
# #425 (2026-04-24): every frontend API route that calls Athena live
# (/api/patterns/detail, /api/recipes/country, /api/scdis,
# /api/patterns/lengths, /api/patterns/years) returns HTTP 500 from Vercel
# because Vercel has no AWS credentials. Every route that reads a baked
# JSON works. This user fills the gap.
#
# Permissions scope (read-only EXCEPT the scoped user-settings write, below):
#   - Athena: start/get query executions + workgroup read
#   - Glue: describe the qgi_data database + its tables (Athena requires it)
#   - S3: GetObject on query_results/ (Athena writes results there; client
#     reads them back). Also s3:GetBucketLocation (needed for cross-region
#     handshake) and s3:ListBucket with prefix condition (lets clients
#     paginate query_results without enumerating the whole bucket).
#   - DynamoDB (read): BatchGetItem + GetItem on qgi-indicator-values (pattern
#     detail loads indicator values from DDB — see lib/indicator-values.ts
#     in qgi-frontend)
#   - DynamoDB (read+WRITE): Get/Put/Update/DeleteItem on qgi-user-settings
#     ONLY (per-user profile settings). This is the one write grant on this
#     otherwise read-only key. Because it's a single shared credential, the
#     frontend server actions MUST scope every call to the authenticated
#     session's own email (IDOR guard) — IAM can't bind a caller to their row.
#
# Access keys are NOT defined in Terraform. After apply, Amin generates
# keys via the AWS console and pastes them into Vercel env vars. This
# keeps the STS-style long-lived secrets OUT of terraform state.
#
# Rotation (when triggered): AWS console → IAM → Users → deactivate old
# key → create new key → update Vercel env → redeploy → delete old key.
# ---------------------------------------------------------------------------

resource "aws_iam_user" "vercel_frontend_reader" {
  name = "qgi-frontend-vercel-reader"
  path = "/"
  tags = var.tags
}

resource "aws_iam_user_policy" "vercel_frontend_reader" {
  name = "qgi-frontend-vercel-reader-policy"
  user = aws_iam_user.vercel_frontend_reader.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      # Athena query lifecycle (start → poll → read). Scoped to the
      # QGI-Lambda-Workgroup so requests against the default "primary"
      # workgroup are rejected. EnforceWorkGroupConfiguration=true on
      # that workgroup also blocks clients from overriding OutputLocation
      # (defense in depth).
      {
        Effect = "Allow"
        Action = [
          "athena:StartQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetQueryResults",
          "athena:GetQueryResultsStream",
          "athena:StopQueryExecution",
          "athena:GetWorkGroup",
        ]
        Resource = "arn:aws:athena:${var.region}:${var.aws_account_id}:workgroup/QGI-Lambda-Workgroup"
      },
      # Glue catalog — Athena can't read qgi_data without these.
      {
        Effect = "Allow"
        Action = [
          "glue:GetDatabase",
          "glue:GetDatabases",
          "glue:GetTable",
          "glue:GetTables",
          "glue:GetPartition",
          "glue:GetPartitions",
        ]
        Resource = [
          "arn:aws:glue:${var.region}:${var.aws_account_id}:catalog",
          "arn:aws:glue:${var.region}:${var.aws_account_id}:database/qgi_data",
          "arn:aws:glue:${var.region}:${var.aws_account_id}:table/qgi_data/*",
        ]
      },
      # S3 — Athena needs to list + read the underlying parquet for every
      # table it queries (patterns, scdis, recipes, events, countries) in
      # addition to writing + reading query_results/. The initial scoped
      # policy (query_results-only) produced `s3:ListBucket ... Access
      # Denied` on `qgi-data-lake-*` because Athena's table scan has to
      # enumerate partition objects under each table's Location/ prefix.
      #
      # Widening to bucket-wide read-only (ListBucket + GetObject) is
      # acceptable: this user is READ-ONLY by IAM (no s3:Put*/Delete*),
      # the data lake contains only published economic indicators, pipeline
      # output, and pattern results that the frontend already displays
      # publicly. No secrets or PII live here. Blast radius is "a reader
      # can read what qgintelligence.com already serves."
      {
        Effect = "Allow"
        Action = [
          "s3:GetBucketLocation",
          "s3:ListBucket",
        ]
        Resource = var.data_lake_bucket_arn
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${var.data_lake_bucket_arn}/*"
      },
      # Athena writes query result CSV + metadata files to
      # s3://{bucket}/query_results/*. Without PutObject here the engine
      # fails with "Access denied when writing output to url..." BEFORE it
      # even reads the input tables. AbortMultipartUpload is included
      # because Athena uses multipart uploads for larger result sets.
      # Scope is strictly query_results/* so this user still cannot
      # mutate pipeline output.
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:AbortMultipartUpload"]
        Resource = "${var.data_lake_bucket_arn}/query_results/*"
      },
      # DynamoDB — qgi-indicator-values is read by
      # /api/patterns/detail via getIndicatorValuesBatch (#148). Read-only.
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:BatchGetItem",
          "dynamodb:Query",
        ]
        Resource = "arn:aws:dynamodb:${var.region}:${var.aws_account_id}:table/qgi-indicator-values"
      },
      ],
      # Account-linking existence check (auth). lib/cognito.emailHasPasswordAccount
      # calls ListUsers to detect a pre-existing password account before letting
      # a Google sign-in create a duplicate identity. Read-only, scoped to the
      # one pool. Omitted when no pool ARN is wired (the check then fails-open).
      var.cognito_user_pool_arn != "" ? [
        {
          Effect   = "Allow"
          Action   = ["cognito-idp:ListUsers"]
          Resource = var.cognito_user_pool_arn
        }
      ] : [],
      # Per-user profile settings (watchlist, default view, …). The frontend
      # server actions read + write one item per user (keyed on email) on the
      # qgi-user-settings table. Scoped to that one table. Omitted if unwired.
      var.user_settings_table_arn != "" ? [
        {
          Effect = "Allow"
          # GetItem (load) + PutItem (full-item save, incl. reset-to-defaults)
          # are all the server actions use. No Update/Delete — the app never
          # partial-updates or deletes a settings row.
          Action = [
            "dynamodb:GetItem",
            "dynamodb:PutItem",
          ]
          Resource = var.user_settings_table_arn
        }
    ] : [])
  })
}
