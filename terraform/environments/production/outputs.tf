output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = module.feed_release.lambda_function_name
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = module.feed_release.lambda_function_arn
}

output "eventbridge_rule_names" {
  description = "Names of the EventBridge rules"
  value       = module.feed_release.eventbridge_rule_names
}

output "eventbridge_rule_arns" {
  description = "ARNs of the EventBridge rules"
  value       = module.feed_release.eventbridge_rule_arns
}

output "schedule_expression" {
  description = "EventBridge schedule expression used"
  value       = module.feed_release.schedule_expression
}

output "cloudwatch_log_group_name" {
  description = "Name of the CloudWatch log group"
  value       = module.feed_release.cloudwatch_log_group_name
}

output "iam_role_arn" {
  description = "ARN of the IAM role used by Lambda"
  value       = module.feed_release.iam_role_arn
}

output "resource_group_name" {
  description = "Name of the main resource group"
  value       = module.feed_release.resource_group_name
}

output "resource_group_arn" {
  description = "ARN of the main resource group"
  value       = module.feed_release.resource_group_arn
}

output "comprehensive_resource_group_name" {
  description = "Name of the comprehensive resource group (if created)"
  value       = module.feed_release.comprehensive_resource_group_name
}

output "comprehensive_resource_group_arn" {
  description = "ARN of the comprehensive resource group (if created)"
  value       = module.feed_release.comprehensive_resource_group_arn
}
