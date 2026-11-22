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
  handler       = "handler.lambda_function"
  runtime       = "python3.13"
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory_size

  source_code_hash = var.lambda_source_code_hash

  environment {
    variables = {
      INTERVAL_SECOND = tostring(var.interval_second)
      # 監視するリポジトリの設定。Lambda が実行のたびに読む
      CONFIG_BUCKET = aws_s3_bucket.config.bucket
      CONFIG_KEY    = var.config_object_key
      # トークンの値は渡さず、Lambda が実行時に SSM Parameter Store から取得する
      GITHUB_TOKEN_PARAMETER_NAME = var.github_token_parameter_name
      # エントリーごとに、最後に dispatch できたリリースを記録するテーブル
      STATE_TABLE_NAME = aws_dynamodb_table.state.name
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic_execution,
    aws_cloudwatch_log_group.lambda_log_group,
  ]

  tags = var.tags
}

# EventBridge rule that invokes the Lambda function on a schedule
# 監視するリポジトリは Lambda が S3 の設定から読むので、ルールは 1 つにまとめる
resource "aws_cloudwatch_event_rule" "schedule" {
  name                = "${var.lambda_function_name}-schedule"
  description         = "Check monitored repositories for new releases"
  schedule_expression = var.schedule_expression

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.schedule.name
  target_id = "FeedRelease"
  arn       = aws_lambda_function.feed_release.arn
}

# Lambda permissions for EventBridge to invoke
resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.feed_release.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule.arn
}

# S3 bucket for the repositories config (repositories.json)
# 監視するリポジトリの設定を置く。バージョニングを有効にして、前の設定に戻せるようにする
resource "aws_s3_bucket" "config" {
  bucket = var.config_bucket_name

  tags = var.tags
}

resource "aws_s3_bucket_versioning" "config" {
  bucket = aws_s3_bucket.config.id

  versioning_configuration {
    status = "Enabled"
  }
}

# 古いバージョンが溜まらないよう、新しいものから config_noncurrent_versions_to_keep 個だけ残す
resource "aws_s3_bucket_lifecycle_configuration" "config" {
  bucket = aws_s3_bucket.config.id

  rule {
    id     = "keep-recent-noncurrent-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      # 最新でなくなってから 1 日たったバージョンのうち、新しい方から指定した数を残して消す
      noncurrent_days           = 1
      newer_noncurrent_versions = var.config_noncurrent_versions_to_keep
    }
  }

  # バージョニングを有効にしてからルールを設定する
  depends_on = [aws_s3_bucket_versioning.config]
}

resource "aws_s3_bucket_public_access_block" "config" {
  bucket = aws_s3_bucket.config.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# DynamoDB table for the dispatch state
# エントリーごとに、最後に dispatch できたリリースの ID を記録する（キーはエントリーの name）。
# 時間ではなくこの記録と比べて判定するので、dispatch に失敗したエントリーは次の実行でやり直される。
# 設定（repositories.json）とは別に置く（CLI が ETag を条件に設定を書き込むときと衝突させない）
resource "aws_dynamodb_table" "state" {
  name         = var.state_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "name"

  attribute {
    name = "name"
    type = "S"
  }

  tags = var.tags
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
      },
      {
        # GitHub のトークンを読む。SecureString は AWS 管理キー（aws/ssm）で暗号化しているので kms:Decrypt は要らない
        Effect   = "Allow"
        Action   = "ssm:GetParameter"
        Resource = "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${var.github_token_parameter_name}"
      },
      {
        # 監視するリポジトリの設定を読む
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.config.arn}/${var.config_object_key}"
      },
      {
        # エントリーごとの記録を読み、dispatch に成功したら書き換える
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem"]
        Resource = aws_dynamodb_table.state.arn
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
        "AWS::Logs::LogGroup",
        "AWS::S3::Bucket",
        "AWS::DynamoDB::Table"
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
