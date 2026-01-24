# Lambda deployment package
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = var.source_dir
  output_path = var.output_zip_path
}

# Read repositories from JSON file with schema validation
locals {
  # Read and decode JSON file
  repositories_from_file = jsondecode(file(var.repositories_file))

  # Use variable if provided, otherwise use JSON file
  # The type constraint in the module variable enforces schema validation
  repositories = var.repositories != null ? var.repositories : local.repositories_from_file
}

# Feed Release module
module "feed_release" {
  source = "../../modules/feed-release"

  # GitHub configuration
  github_token    = var.github_token
  interval_second = var.interval_second

  # Repositories to monitor (from JSON file or variable)
  repositories = local.repositories

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
