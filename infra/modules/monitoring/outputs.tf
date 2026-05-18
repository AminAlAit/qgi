# monitoring module outputs

output "alarm_arns" {
  description = "ARNs of every CloudWatch metric alarm created by this module. Cascade alarms are absent when enable_cascade = false."
  value = concat(
    aws_cloudwatch_metric_alarm.high_country_count_low[*].arn,
    aws_cloudwatch_metric_alarm.high_country_count_high[*].arn,
    aws_cloudwatch_metric_alarm.median_salience_low[*].arn,
    aws_cloudwatch_metric_alarm.median_salience_high[*].arn,
    aws_cloudwatch_metric_alarm.country_risks_bytes_low[*].arn,
    aws_cloudwatch_metric_alarm.country_risks_bytes_high[*].arn,
  )
}

output "alarm_names" {
  description = "Names of every CloudWatch metric alarm created by this module. Cascade alarms are absent when enable_cascade = false."
  value = concat(
    aws_cloudwatch_metric_alarm.high_country_count_low[*].alarm_name,
    aws_cloudwatch_metric_alarm.high_country_count_high[*].alarm_name,
    aws_cloudwatch_metric_alarm.median_salience_low[*].alarm_name,
    aws_cloudwatch_metric_alarm.median_salience_high[*].alarm_name,
    aws_cloudwatch_metric_alarm.country_risks_bytes_low[*].alarm_name,
    aws_cloudwatch_metric_alarm.country_risks_bytes_high[*].alarm_name,
  )
}
