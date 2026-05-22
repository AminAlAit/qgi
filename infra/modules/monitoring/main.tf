# ---------------------------------------------------------------------------
# Monitoring module — V1.9.1 scoring drift alarms (#381)
#
# The Lambda `qgi-pipeline-recipe-engine-finalize` emits 3 CloudWatch custom
# metrics to namespace `QGI/Pipeline` with dimension ScoringVersion=V1.9.1:
#   - HIGH_COUNTRY_COUNT     (Count)
#   - MEDIAN_SALIENCE_SCORE  (None / dimensionless)
#   - COUNTRY_RISKS_BYTES    (Bytes)
#
# Thresholds below are STATIC guardrails. We don't yet have 7 days of
# history to fit anomaly-detection bands, so we pick loose static bands
# around today's observations. These catch catastrophic drift (schema
# break, empty payload, collapsed distribution) without flapping on
# day-to-day noise.
#
# TODO(#381): Once 7+ days of metric history exists, replace these static
# alarms with `aws_cloudwatch_anomaly_detector` + ANOMALY_DETECTION_BAND
# alarms (±2σ). Keep the SNS wiring identical so the paging contract
# doesn't change.
# ---------------------------------------------------------------------------

locals {
  namespace = "QGI/Pipeline"
  dimensions = {
    ScoringVersion = "V1.9.1"
  }
}

# ---------------------------------------------------------------------------
# 1. HIGH_COUNTRY_COUNT — drift out of the acceptable HIGH-tier band.
#
# Ticket #377 target band: [25, 45] HIGH countries.
# Guardrail band: [15, 60] — catches drift outside the acceptable zone
# without flapping on normal scoring-run noise.
# Current staging observation: 33.
# Each scoring run emits one data point; 1h period / 1 evaluation = page
# on the first bad run. PAGES via SNS.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# V1.9.1 scoring-drift alarms (Cascade/SCDI-exclusive — gated by enable_cascade)
# These alarms monitor recipe_engine_finalize outputs which only exist in a
# Cascade-enabled environment.
# ---------------------------------------------------------------------------
# moved blocks for all 6 V1.9.1 alarms
moved {
  from = aws_cloudwatch_metric_alarm.high_country_count_low
  to   = aws_cloudwatch_metric_alarm.high_country_count_low[0]
}
moved {
  from = aws_cloudwatch_metric_alarm.high_country_count_high
  to   = aws_cloudwatch_metric_alarm.high_country_count_high[0]
}
moved {
  from = aws_cloudwatch_metric_alarm.median_salience_low
  to   = aws_cloudwatch_metric_alarm.median_salience_low[0]
}
moved {
  from = aws_cloudwatch_metric_alarm.median_salience_high
  to   = aws_cloudwatch_metric_alarm.median_salience_high[0]
}
moved {
  from = aws_cloudwatch_metric_alarm.country_risks_bytes_low
  to   = aws_cloudwatch_metric_alarm.country_risks_bytes_low[0]
}
moved {
  from = aws_cloudwatch_metric_alarm.country_risks_bytes_high
  to   = aws_cloudwatch_metric_alarm.country_risks_bytes_high[0]
}

resource "aws_cloudwatch_metric_alarm" "high_country_count_low" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count               = var.enable_cascade ? 1 : 0
  alarm_name          = "qgi-v191-high-country-count-out-of-band-low"
  alarm_description   = "V1.9.1 HIGH_COUNTRY_COUNT dropped below 15 (target band [25,45], guardrail [15,60]). Indicates scoring collapse or upstream data loss."
  namespace           = local.namespace
  metric_name         = "HIGH_COUNTRY_COUNT"
  dimensions          = local.dimensions
  statistic           = "Average"
  period              = 3600
  evaluation_periods  = 1
  comparison_operator = "LessThanThreshold"
  threshold           = 15
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.sns_topic_arn]
  ok_actions          = [var.sns_topic_arn]
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "high_country_count_high" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count               = var.enable_cascade ? 1 : 0
  alarm_name          = "qgi-v191-high-country-count-out-of-band-high"
  alarm_description   = "V1.9.1 HIGH_COUNTRY_COUNT exceeded 60 (target band [25,45], guardrail [15,60]). Indicates score inflation or threshold drift."
  namespace           = local.namespace
  metric_name         = "HIGH_COUNTRY_COUNT"
  dimensions          = local.dimensions
  statistic           = "Average"
  period              = 3600
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 60
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.sns_topic_arn]
  ok_actions          = [var.sns_topic_arn]
  tags                = var.tags
}

# ---------------------------------------------------------------------------
# 2. MEDIAN_SALIENCE_SCORE — distribution shift guard.
#
# Today's observation: ~0.5. Band [0.2, 1.5] is a loose sanity zone.
# No rolling mean yet; replace with ±2σ anomaly detection once 7 days
# of data is live. evaluation_periods=2 — require two trending-bad runs
# before paging so single-run noise doesn't flap. PAGES via SNS.
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "median_salience_low" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count               = var.enable_cascade ? 1 : 0
  alarm_name          = "qgi-v191-median-salience-out-of-band-low"
  alarm_description   = "V1.9.1 MEDIAN_SALIENCE_SCORE below 0.2 for two consecutive runs. Likely score compression or scoring bug."
  namespace           = local.namespace
  metric_name         = "MEDIAN_SALIENCE_SCORE"
  dimensions          = local.dimensions
  statistic           = "Average"
  period              = 3600
  evaluation_periods  = 2
  comparison_operator = "LessThanThreshold"
  threshold           = 0.2
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.sns_topic_arn]
  ok_actions          = [var.sns_topic_arn]
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "median_salience_high" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count               = var.enable_cascade ? 1 : 0
  alarm_name          = "qgi-v191-median-salience-out-of-band-high"
  alarm_description   = "V1.9.1 MEDIAN_SALIENCE_SCORE above 1.5 for two consecutive runs. Likely score inflation or upstream-signal break."
  namespace           = local.namespace
  metric_name         = "MEDIAN_SALIENCE_SCORE"
  dimensions          = local.dimensions
  statistic           = "Average"
  period              = 3600
  evaluation_periods  = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = 1.5
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.sns_topic_arn]
  ok_actions          = [var.sns_topic_arn]
  tags                = var.tags
}

# ---------------------------------------------------------------------------
# 3. COUNTRY_RISKS_BYTES — payload-size sanity guard.
#
# Today's observation: ~684 KB. Band [200 KB, 2 MB] catches catastrophic
# shrink (schema break, empty payload) or bloat (runaway data).
# Per ticket #381: ALARM ONLY — do NOT page. State is visible in console.
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "country_risks_bytes_low" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count               = var.enable_cascade ? 1 : 0
  alarm_name          = "qgi-v191-country-risks-bytes-out-of-band-low"
  alarm_description   = "V1.9.1 COUNTRY_RISKS_BYTES dropped below 200 KB. Likely schema break or empty payload. ALARM-ONLY (no page)."
  namespace           = local.namespace
  metric_name         = "COUNTRY_RISKS_BYTES"
  dimensions          = local.dimensions
  statistic           = "Average"
  period              = 3600
  evaluation_periods  = 1
  comparison_operator = "LessThanThreshold"
  threshold           = 200000
  treat_missing_data  = "notBreaching"
  alarm_actions       = []
  ok_actions          = []
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "country_risks_bytes_high" {
  # Cascade/SCDI-exclusive. Omitted when enable_cascade = false.
  count               = var.enable_cascade ? 1 : 0
  alarm_name          = "qgi-v191-country-risks-bytes-out-of-band-high"
  alarm_description   = "V1.9.1 COUNTRY_RISKS_BYTES exceeded 2 MB. Likely runaway payload or serialization regression. ALARM-ONLY (no page)."
  namespace           = local.namespace
  metric_name         = "COUNTRY_RISKS_BYTES"
  dimensions          = local.dimensions
  statistic           = "Average"
  period              = 3600
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 2000000
  treat_missing_data  = "notBreaching"
  alarm_actions       = []
  ok_actions          = []
  tags                = var.tags
}

# ---------------------------------------------------------------------------
# #409 — Silent-failure observability (CaughtExceptionCount)
#
# Lambdas emit a count each time they catch-and-continue an exception
# in a non-critical-looking code path. Dimensions:
#   - Lambda   (function name, e.g. qgi-pipeline-recipe-engine-finalize)
#   - Location (logical context key, e.g. write_country_risks_json)
#
# Driven by the 2026-04-22 incident: country-risks.json silently stopped
# regenerating for 2 days because a signature-mismatch exception was
# caught, logged, and the finalize Lambda still returned 200 to Step
# Functions. We don't want to turn catch-and-continue into strict-raise
# (the surrounding steps are genuinely best-effort) — we want an alarm
# that pages when ANY Lambda's catch rate spikes above zero.
#
# This is a single one-alarm-catches-all pattern: sum across all Lambdas
# and Locations within one hour. Anything >= 1 pages. Pair with CloudWatch
# Logs Insights for `[ERROR]` / `[EXCEPTION]` in the affected Lambda to
# triage specifics.
# ---------------------------------------------------------------------------

# Explicit list of (Lambda, Location) pairs emitting CaughtExceptionCount
# (#409). When a new _emit_caught_exception() call is added to a Lambda,
# add its (Lambda, Location) pair here and re-apply.
#
# CloudWatch metric alarms don't support SEARCH expressions, so each
# dimension pair needs its own alarm. (SEARCH works in dashboards, not
# in PutMetricAlarm.) Keeping the list explicit also means the alarm
# count matches the catch-block count, which is a useful sanity check
# during #373-style audits.
locals {
  caught_exception_targets = {
    "finalize-convergence" = {
      lambda   = "qgi-pipeline-recipe-engine-finalize"
      location = "create_convergence_view"
    }
    "finalize-dashboard" = {
      lambda   = "qgi-pipeline-recipe-engine-finalize"
      location = "write_dashboard_jsons"
    }
    "finalize-country-risks" = {
      lambda   = "qgi-pipeline-recipe-engine-finalize"
      location = "write_country_risks_json"
    }
    # #466 Stage A — V2.0 SRE-readiness alarms (Section A item 1 partial coverage).
    # The Lambda already emits _emit_caught_exception('write_recipes_aggregated_table')
    # and _emit_caught_exception('write_country_recipe_scores') in pipeline-recipe-
    # engine-finalize/lambda_function.py — add the alarms so silent-fail of either
    # writer pages on-call rather than silently emptying the V2.0 tables. Runbook
    # entries 4 + 5 in docs/specs/playbooks/v2-recipe-engine.md.
    "finalize-recipes-aggregated" = {
      lambda   = "qgi-pipeline-recipe-engine-finalize"
      location = "write_recipes_aggregated_table"
    }
    "finalize-country-recipe-scores" = {
      lambda   = "qgi-pipeline-recipe-engine-finalize"
      location = "write_country_recipe_scores"
    }
  }
}

# ---------------------------------------------------------------------------
# Caught-exception alarms for recipe_engine_finalize
# (Cascade/SCDI-exclusive — gated by enable_cascade)
# ---------------------------------------------------------------------------
# moved blocks for all 5 caught_exception alarms (for_each keys)
moved {
  from = aws_cloudwatch_metric_alarm.caught_exception["finalize-convergence"]
  to   = aws_cloudwatch_metric_alarm.caught_exception_cascade["finalize-convergence"]
}
moved {
  from = aws_cloudwatch_metric_alarm.caught_exception["finalize-dashboard"]
  to   = aws_cloudwatch_metric_alarm.caught_exception_cascade["finalize-dashboard"]
}
moved {
  from = aws_cloudwatch_metric_alarm.caught_exception["finalize-country-risks"]
  to   = aws_cloudwatch_metric_alarm.caught_exception_cascade["finalize-country-risks"]
}
moved {
  from = aws_cloudwatch_metric_alarm.caught_exception["finalize-recipes-aggregated"]
  to   = aws_cloudwatch_metric_alarm.caught_exception_cascade["finalize-recipes-aggregated"]
}
moved {
  from = aws_cloudwatch_metric_alarm.caught_exception["finalize-country-recipe-scores"]
  to   = aws_cloudwatch_metric_alarm.caught_exception_cascade["finalize-country-recipe-scores"]
}

resource "aws_cloudwatch_metric_alarm" "caught_exception_cascade" {
  # Cascade/SCDI-exclusive: all caught_exception targets are on
  # recipe_engine_finalize, which only runs in Cascade environments.
  # Omitted when enable_cascade = false.
  for_each = var.enable_cascade ? local.caught_exception_targets : {}

  alarm_name        = "qgi-caught-exception-${each.key}"
  alarm_description = "Lambda ${each.value.lambda} caught-and-continued an exception at Location=${each.value.location} (#409). Driven by 2026-04-22 silent-failure incident (country-risks.json silently stopped regenerating for 2 days). Single-event paging so the same class cannot recur — triage via CloudWatch Logs Insights on the affected Lambda for [EXCEPTION] lines."
  namespace         = local.namespace
  metric_name       = "CaughtExceptionCount"
  dimensions = {
    Lambda   = each.value.lambda
    Location = each.value.location
  }
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.sns_topic_arn]
  ok_actions          = [var.sns_topic_arn]
  tags                = var.tags
}
