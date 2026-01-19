# Lambda deployment package
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = var.source_dir
  output_path = var.output_zip_path
}

# Feed Release module
module "feed_release" {
  source = "../../modules/feed-release"

  # GitHub configuration
  github_token    = var.github_token
  interval_second = var.interval_second

  # Repositories to monitor
  repositories = var.repositories

  # Lambda configuration
  lambda_function_name    = var.lambda_function_name
  lambda_zip_path         = data.archive_file.lambda_zip.output_path
  lambda_source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  lambda_timeout          = var.lambda_timeout
  lambda_memory_size      = var.lambda_memory_size

  # EventBridge configuration
  schedule_expression = var.schedule_expression

  # CloudWatch configuration
  cloudwatch_log_retention_days = var.cloudwatch_log_retention_days

  # Resource management
  resource_group_name                 = var.resource_group_name
  create_comprehensive_resource_group = var.create_comprehensive_resource_group

  # Tags
  tags = var.tags
}
