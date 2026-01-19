terraform {
  required_version = ">= 1.2.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.92"
    }
  }
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "lambda_log_group" {
  name              = "/aws/lambda/${var.lambda_function_name}"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = var.tags
}

# Lambda function
resource "aws_lambda_function" "feed_release" {
  filename      = var.lambda_zip_path
  function_name = var.lambda_function_name
  role          = aws_iam_role.lambda_role.arn
  handler       = "feed_release.handler.lambda_function"
  runtime       = "python3.13"
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory_size

  source_code_hash = var.lambda_source_code_hash

  environment {
    variables = {
      INTERVAL_SECOND = tostring(var.interval_second)
      GITHUB_TOKEN    = var.github_token
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic_execution,
    aws_cloudwatch_log_group.lambda_log_group,
  ]

  tags = var.tags
}

# EventBridge rules for each monitored repository
resource "aws_cloudwatch_event_rule" "release_monitor" {
  for_each = { for repo in var.repositories : repo.name => repo }

  name                = "${var.lambda_function_name}-${each.key}"
  description         = "Monitor ${each.value.monitored_owner}/${each.value.monitored_repo} for new releases"
  schedule_expression = var.schedule_expression

  tags = var.tags
}

# EventBridge targets pointing to Lambda function with repository-specific payloads
resource "aws_cloudwatch_event_target" "lambda_target" {
  for_each = { for repo in var.repositories : repo.name => repo }

  rule      = aws_cloudwatch_event_rule.release_monitor[each.key].name
  target_id = "FeedRelease-${each.key}"
  arn       = aws_lambda_function.feed_release.arn

  input = jsonencode({
    monitored_owner = each.value.monitored_owner
    monitored_repo  = each.value.monitored_repo
    target_owner    = each.value.target_owner
    target_repo     = each.value.target_repo
    event_type      = each.value.event_type
  })
}

# Lambda permissions for EventBridge to invoke
resource "aws_lambda_permission" "allow_eventbridge" {
  for_each = { for repo in var.repositories : repo.name => repo }

  statement_id  = "AllowExecutionFromEventBridge-${each.key}"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.feed_release.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.release_monitor[each.key].arn
}

# IAM role for Lambda function
resource "aws_iam_role" "lambda_role" {
  name = "${var.lambda_function_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

# IAM policy for Lambda basic execution
resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
  role       = aws_iam_role.lambda_role.name
}

# Custom IAM policy for Lambda function
resource "aws_iam_role_policy" "lambda_policy" {
  name = "${var.lambda_function_name}-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:*"
      }
    ]
  })
}

# Resource Groups
resource "aws_resourcegroups_group" "feed_release" {
  name = var.resource_group_name

  resource_query {
    query = jsonencode({
      ResourceTypeFilters = [
        "AWS::Lambda::Function",
        "AWS::Events::Rule",
        "AWS::Logs::LogGroup"
      ]
      TagFilters = [
        {
          Key    = "Project"
          Values = [var.tags.Project]
        }
      ]
    })
  }

  tags = var.tags
}

# Comprehensive resource group (optional)
resource "aws_resourcegroups_group" "feed_release_all" {
  count = var.create_comprehensive_resource_group ? 1 : 0
  name  = "${var.resource_group_name}-all"

  resource_query {
    query = jsonencode({
      ResourceTypeFilters = ["AWS::AllSupported"]
      TagFilters = [
        {
          Key    = "Project"
          Values = [var.tags.Project]
        }
      ]
    })
  }

  tags = var.tags
}
