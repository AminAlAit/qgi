output "bucket_name" {
  value = aws_s3_bucket.data_lake.bucket
}

output "bucket_arn" {
  value = aws_s3_bucket.data_lake.arn
}

output "queue_a_main_url" { value = aws_sqs_queue.a_main.url }
output "queue_a_main_arn" { value = aws_sqs_queue.a_main.arn }
output "queue_a_dlq_url" { value = aws_sqs_queue.a_dlq.url }
output "queue_a_dlq_arn" { value = aws_sqs_queue.a_dlq.arn }

# Cascade/SCDI-exclusive queues — empty string when enable_cascade = false.
# Pipeline module variables for B/C queue urls/arns have default = "" so
# environments can omit these when enable_cascade = false.
output "queue_b_main_url" { value = one(aws_sqs_queue.b_main[*].url) != null ? one(aws_sqs_queue.b_main[*].url) : "" }
output "queue_b_main_arn" { value = one(aws_sqs_queue.b_main[*].arn) != null ? one(aws_sqs_queue.b_main[*].arn) : "" }
output "queue_b_dlq_url" { value = one(aws_sqs_queue.b_dlq[*].url) != null ? one(aws_sqs_queue.b_dlq[*].url) : "" }
output "queue_b_dlq_arn" { value = one(aws_sqs_queue.b_dlq[*].arn) != null ? one(aws_sqs_queue.b_dlq[*].arn) : "" }

output "queue_c_main_url" { value = one(aws_sqs_queue.c_main[*].url) != null ? one(aws_sqs_queue.c_main[*].url) : "" }
output "queue_c_main_arn" { value = one(aws_sqs_queue.c_main[*].arn) != null ? one(aws_sqs_queue.c_main[*].arn) : "" }
output "queue_c_dlq_url" { value = one(aws_sqs_queue.c_dlq[*].url) != null ? one(aws_sqs_queue.c_dlq[*].url) : "" }
output "queue_c_dlq_arn" { value = one(aws_sqs_queue.c_dlq[*].arn) != null ? one(aws_sqs_queue.c_dlq[*].arn) : "" }

# all_queue_arns: always includes Phase A queues; Phase B/C queues are
# included only when enable_cascade = true. The IAM module's
# lambda_execution_role uses this for SQS permissions.
output "all_queue_arns" {
  value = concat(
    [aws_sqs_queue.a_main.arn, aws_sqs_queue.a_dlq.arn],
    aws_sqs_queue.b_main[*].arn,
    aws_sqs_queue.b_dlq[*].arn,
    aws_sqs_queue.c_main[*].arn,
    aws_sqs_queue.c_dlq[*].arn,
  )
}

output "indicator_table_name" { value = aws_dynamodb_table.indicator_updates.name }
output "indicator_table_arn" { value = aws_dynamodb_table.indicator_updates.arn }

output "completion_table_name" { value = aws_dynamodb_table.completion_counters.name }
output "completion_table_arn" { value = aws_dynamodb_table.completion_counters.arn }

# #148: indicator values DDB table
output "indicator_values_table_name" { value = aws_dynamodb_table.indicator_values.name }
output "indicator_values_table_arn" { value = aws_dynamodb_table.indicator_values.arn }
output "user_settings_table_name" { value = length(aws_dynamodb_table.user_settings) > 0 ? aws_dynamodb_table.user_settings[0].name : "" }
output "user_settings_table_arn" { value = length(aws_dynamodb_table.user_settings) > 0 ? aws_dynamodb_table.user_settings[0].arn : "" }

# #FAR-1: Phase 1 Fargate Spot dispatch counter
output "pipeline_a_counter_table_name" { value = aws_dynamodb_table.pipeline_a_counter.name }
output "pipeline_a_counter_table_arn" { value = aws_dynamodb_table.pipeline_a_counter.arn }

output "sns_topic_arn" { value = aws_sns_topic.pipeline_notifications.arn }

# Cost-guard SNS topic — pages the QGI ops inbox when a budget/alarm breaches.
# Consumed by the live-pulse module's budget + DLQ alarm (live-pulse track).
output "cost_alerts_topic_arn" { value = aws_sns_topic.cost_alerts.arn }

output "glue_database_name" { value = aws_glue_catalog_database.qgi_data.name }
output "athena_workgroup_name" { value = aws_athena_workgroup.qgi.name }
