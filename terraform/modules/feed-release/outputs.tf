output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.feed_release.function_name
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = aws_lambda_function.feed_release.arn
}

output "eventbridge_rule_names" {
  description = "Names of the EventBridge rules"
  value       = { for k, v in aws_cloudwatch_event_rule.release_monitor : k => v.name }
}

output "eventbridge_rule_arns" {
  description = "ARNs of the EventBridge rules"
  value       = { for k, v in aws_cloudwatch_event_rule.release_monitor : k => v.arn }
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
