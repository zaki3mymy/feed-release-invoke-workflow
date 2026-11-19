output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.feed_release.function_name
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = aws_lambda_function.feed_release.arn
}

output "eventbridge_rule_name" {
  description = "Name of the EventBridge rule"
  value       = aws_cloudwatch_event_rule.schedule.name
}

output "eventbridge_rule_arn" {
  description = "ARN of the EventBridge rule"
  value       = aws_cloudwatch_event_rule.schedule.arn
}

output "config_object_key" {
  description = "Key of the repositories config (JSON) in the S3 bucket"
  value       = var.config_object_key
}

output "config_bucket_name" {
  description = "Name of the S3 bucket that holds the repositories config"
  value       = aws_s3_bucket.config.bucket
}

output "config_bucket_arn" {
  description = "ARN of the S3 bucket that holds the repositories config"
  value       = aws_s3_bucket.config.arn
}

output "schedule_expression" {
  description = "EventBridge schedule expression used"
  value       = var.schedule_expression
}

output "cloudwatch_log_group_name" {
  description = "Name of the CloudWatch log group"
  value       = aws_cloudwatch_log_group.lambda_log_group.name
}

output "iam_role_arn" {
  description = "ARN of the IAM role used by Lambda"
  value       = aws_iam_role.lambda_role.arn
}

output "resource_group_name" {
  description = "Name of the main resource group"
  value       = aws_resourcegroups_group.feed_release.name
}

output "resource_group_arn" {
  description = "ARN of the main resource group"
  value       = aws_resourcegroups_group.feed_release.arn
}

output "comprehensive_resource_group_name" {
  description = "Name of the comprehensive resource group (if created)"
  value       = var.create_comprehensive_resource_group ? aws_resourcegroups_group.feed_release_all[0].name : null
}

output "comprehensive_resource_group_arn" {
  description = "ARN of the comprehensive resource group (if created)"
  value       = var.create_comprehensive_resource_group ? aws_resourcegroups_group.feed_release_all[0].arn : null
}
