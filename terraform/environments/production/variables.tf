variable "github_token" {
  description = "GitHub API token for triggering workflow dispatch"
  type        = string
  sensitive   = true
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

variable "lambda_function_name" {
  description = "Name of the Lambda function"
  type        = string
  default     = "feed-release"
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
    Project     = "feed-release"
    Environment = "production"
    ManagedBy   = "terraform"
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

variable "source_dir" {
  description = "Path to the source directory containing Lambda function code"
  type        = string
  default     = "../../../src/feed_release"
}

variable "output_zip_path" {
  description = "Path where the Lambda deployment zip file will be created"
  type        = string
  default     = "../../../dist/lambda_function.zip"
}
