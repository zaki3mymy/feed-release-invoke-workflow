variable "github_token_parameter_name" {
  description = "Name of the SSM parameter (SecureString) holding the GitHub API token for triggering workflow dispatch"
  type        = string
  default     = "/app/feed-release-invoke-workflow/gh-token-for-dispatch"

  validation {
    condition     = substr(var.github_token_parameter_name, 0, 1) == "/"
    error_message = "github_token_parameter_name must start with \"/\"."
  }
}

variable "interval_second" {
  description = "Time window in seconds to consider a release as 'latest'"
  type        = number
  default     = 3600
}

variable "repositories" {
  description = "List of repositories to monitor for releases"
  type = list(object({
    name            = string
    monitored_owner = string
    monitored_repo  = string
    target_owner    = string
    target_repo     = string
    event_type      = string
  }))
}

variable "config_bucket_name" {
  description = "Name of the S3 bucket that holds the repositories config"
  type        = string
  default     = "prod-feed-release-invoke-workflow"
}

variable "config_noncurrent_versions_to_keep" {
  description = "Number of noncurrent versions of the repositories config to keep in the S3 bucket"
  type        = number
  default     = 10
}

variable "lambda_function_name" {
  description = "Name of the Lambda function"
  type        = string
  default     = "feed-release"
}

variable "lambda_zip_path" {
  description = "Path to the Lambda deployment zip file"
  type        = string
}

variable "lambda_source_code_hash" {
  description = "Base64 encoded hash of the Lambda zip file"
  type        = string
}

variable "schedule_expression" {
  description = "EventBridge schedule expression for checking releases"
  type        = string
  default     = "rate(1 hour)"
}

variable "lambda_timeout" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 30
}

variable "lambda_memory_size" {
  description = "Lambda function memory size in MB"
  type        = number
  default     = 128
}

variable "cloudwatch_log_retention_days" {
  description = "CloudWatch log retention period in days"
  type        = number
  default     = 14
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    Project   = "feed-release"
    ManagedBy = "terraform"
  }
}

variable "resource_group_name" {
  description = "Name of the AWS Resource Group"
  type        = string
  default     = "feed-release-resources"
}

variable "create_comprehensive_resource_group" {
  description = "Whether to create a comprehensive resource group that includes all AWS resources"
  type        = bool
  default     = false
}
