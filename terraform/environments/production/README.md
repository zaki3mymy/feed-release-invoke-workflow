# Production Environment

Feed Release アプリケーションの本番環境デプロイメント設定です。

## デプロイメント手順

### 1. 事前準備

#### S3バックエンドの設定

Terraformの状態管理用S3バケットを作成してください：

```bash
# S3バケット作成（バケット名は一意である必要があります）
aws s3 mb s3://your-terraform-state-bucket --region ap-northeast-1

# バージョニング有効化
aws s3api put-bucket-versioning \
  --bucket your-terraform-state-bucket \
  --versioning-configuration Status=Enabled

# 暗号化有効化
aws s3api put-bucket-encryption \
  --bucket your-terraform-state-bucket \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'
```

### 2. 環境固有設定

#### terraform.tfvars の作成

`terraform.tfvars`ファイルを作成し、以下の値を設定してください：

```hcl
# GitHub API設定
github_token = "ghp_xxxxxxxxxxxx"  # GitHub Personal Access Token

# リリース判定設定
interval_second = 3600  # 1時間以内のリリースを「最新」と判定

# 監視対象リポジトリ
repositories = [
  {
    name            = "claude-code"
    monitored_owner = "anthropics"
    monitored_repo  = "claude-code"
    target_owner    = "my-org"
    target_repo     = "my-app"
    event_type      = "claude-code-release"
  },
  {
    name            = "terraform"
    monitored_owner = "hashicorp"
    monitored_repo  = "terraform"
    target_owner    = "my-org"
    target_repo     = "infra"
    event_type      = "terraform-release"
  }
]

# Lambda設定
lambda_function_name = "feed-release"

# スケジュール設定（デフォルト：1時間ごと）
schedule_expression = "rate(1 hour)"

# リソースタグ
tags = {
  Environment = "production"
  ManagedBy   = "terraform"
  Project     = "feed-release"
}
```

### 3. デプロイ実行

```bash
cd terraform/environments/production

# Terraform初期化
terraform init \
  -backend-config="bucket=your-terraform-state-bucket" \
  -backend-config="key=feed-release/production.tfstate" \
  -backend-config="region=ap-northeast-1"

# プラン確認
terraform plan

# デプロイ実行
terraform apply
```

## 設定値の取得方法

### GitHub Personal Access Token

1. [GitHub Settings > Developer settings > Personal access tokens](https://github.com/settings/tokens) にアクセス
2. 「Generate new token (classic)」で新しいトークンを作成
3. 必要なスコープ: `repo` (Repository Dispatchに必要)
4. 生成されたトークンをコピー

### repositories 変数の構造

| フィールド | 説明 |
|------------|------|
| `name` | 識別名（EventBridgeルール名に使用） |
| `monitored_owner` | 監視対象リポジトリのオーナー |
| `monitored_repo` | 監視対象リポジトリ名 |
| `target_owner` | ワークフロー実行先のオーナー |
| `target_repo` | ワークフロー実行先のリポジトリ名 |
| `event_type` | GitHub Actionsのイベントタイプ |

## デプロイ後の確認

### リソースの確認

```bash
# 作成されたリソースの出力値確認
terraform output

# Lambda関数の確認
aws lambda get-function --function-name feed-release

# EventBridgeルールの確認
aws events list-rules --name-prefix feed-release
```

### 動作テスト

```bash
# Lambda関数の手動実行（特定リポジトリ）
aws lambda invoke \
  --function-name feed-release \
  --payload '{"monitored_owner":"anthropics","monitored_repo":"claude-code","target_owner":"my-org","target_repo":"my-app","event_type":"claude-code-release"}' \
  response.json

# レスポンス確認
cat response.json

# CloudWatchログの確認
aws logs tail /aws/lambda/feed-release --follow
```

### リソースグループでの管理

```bash
# プロジェクトリソース一覧
aws resource-groups list-group-resources --group-name feed-release-resources

# AWS コンソールでの確認
# https://console.aws.amazon.com/resource-groups/
```

## メンテナンス

### ログの確認

```bash
# 最新のログを表示
aws logs tail /aws/lambda/feed-release --follow

# エラーログのみフィルタリング
aws logs filter-log-events \
  --log-group-name /aws/lambda/feed-release \
  --filter-pattern "ERROR"
```

### コードの更新

```bash
# terraform applyを実行すると自動的にzipが更新される
cd terraform/environments/production
terraform apply
```

### 監視対象リポジトリの追加

`terraform.tfvars`の`repositories`リストに新しいエントリを追加してください：

```hcl
repositories = [
  # 既存のエントリ...
  {
    name            = "new-repo"
    monitored_owner = "owner"
    monitored_repo  = "repo-name"
    target_owner    = "my-org"
    target_repo     = "my-app"
    event_type      = "new-repo-release"
  }
]
```

### 実行スケジュールの変更

`terraform.tfvars`の`schedule_expression`を変更してください：

```hcl
# 30分ごとに変更する場合
schedule_expression = "rate(30 minutes)"

# 毎日JST 9:00に変更する場合
schedule_expression = "cron(0 0 * * ? *)"  # UTC 00:00 = JST 09:00
```

## トラブルシューティング

### よくある問題

1. **Lambda関数が実行されない**
   - EventBridgeルールが有効か確認
   - IAMロールの権限を確認

2. **GitHub API エラー**
   - GitHub Tokenが正しいか確認
   - トークンに`repo`スコープがあるか確認
   - リポジトリ名/オーナー名が正しいか確認

3. **デプロイエラー**
   - S3バックエンドのアクセス権限を確認
   - AWSクレデンシャルが設定されているか確認

### ログレベル設定

開発時のデバッグ用に、Lambdaの環境変数でログレベルを設定できます：

```hcl
# main.tf内のLambda関数設定で追加
environment {
  variables = {
    LOG_LEVEL = "DEBUG"  # INFO, DEBUG, ERROR
  }
}
```

## セキュリティ考慮事項

- GitHub Tokenは`sensitive = true`でマークされ、ログに出力されません
- IAMロールは最小権限の原則に従い、必要な権限のみ付与
- S3バックエンドは暗号化とバージョニングを有効化
- CloudWatch Logsは14日間の保持期間を設定

<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.2.0 |
| <a name="requirement_archive"></a> [archive](#requirement\_archive) | ~> 2.7 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | ~> 5.92 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_archive"></a> [archive](#provider\_archive) | 2.7.1 |

## Modules

| Name | Source | Version |
|------|--------|---------|
| <a name="module_feed_release"></a> [feed\_release](#module\_feed\_release) | ../../modules/feed-release | n/a |

## Resources

| Name | Type |
|------|------|
| [archive_file.lambda_zip](https://registry.terraform.io/providers/hashicorp/archive/latest/docs/data-sources/file) | data source |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_cloudwatch_log_retention_days"></a> [cloudwatch\_log\_retention\_days](#input\_cloudwatch\_log\_retention\_days) | CloudWatch log retention period in days | `number` | `14` | no |
| <a name="input_create_comprehensive_resource_group"></a> [create\_comprehensive\_resource\_group](#input\_create\_comprehensive\_resource\_group) | Whether to create a comprehensive resource group that includes all AWS resources | `bool` | `false` | no |
| <a name="input_github_token"></a> [github\_token](#input\_github\_token) | GitHub API token for triggering workflow dispatch | `string` | n/a | yes |
| <a name="input_interval_second"></a> [interval\_second](#input\_interval\_second) | Time window in seconds to consider a release as 'latest' | `number` | `3600` | no |
| <a name="input_lambda_function_name"></a> [lambda\_function\_name](#input\_lambda\_function\_name) | Name of the Lambda function | `string` | `"feed-release"` | no |
| <a name="input_lambda_memory_size"></a> [lambda\_memory\_size](#input\_lambda\_memory\_size) | Lambda function memory size in MB | `number` | `128` | no |
| <a name="input_lambda_timeout"></a> [lambda\_timeout](#input\_lambda\_timeout) | Lambda function timeout in seconds | `number` | `30` | no |
| <a name="input_output_zip_path"></a> [output\_zip\_path](#input\_output\_zip\_path) | Path where the Lambda deployment zip file will be created | `string` | `"../../../dist/lambda_function.zip"` | no |
| <a name="input_repositories"></a> [repositories](#input\_repositories) | List of repositories to monitor for releases. If not provided, reads from repositories.json | <pre>list(object({<br/>    name            = string<br/>    monitored_owner = string<br/>    monitored_repo  = string<br/>    target_owner    = string<br/>    target_repo     = string<br/>    event_type      = string<br/>  }))</pre> | `null` | no |
| <a name="input_repositories_file"></a> [repositories\_file](#input\_repositories\_file) | Path to JSON file containing repository configurations | `string` | `"repositories.json"` | no |
| <a name="input_resource_group_name"></a> [resource\_group\_name](#input\_resource\_group\_name) | Name of the AWS Resource Group | `string` | `"feed-release-resources"` | no |
| <a name="input_schedule_expression"></a> [schedule\_expression](#input\_schedule\_expression) | EventBridge schedule expression for checking releases | `string` | `"rate(1 hour)"` | no |
| <a name="input_source_dir"></a> [source\_dir](#input\_source\_dir) | Path to the source directory containing Lambda function code | `string` | `"../../../src/feed_release"` | no |
| <a name="input_tags"></a> [tags](#input\_tags) | Tags to apply to all resources | `map(string)` | <pre>{<br/>  "Environment": "production",<br/>  "ManagedBy": "terraform",<br/>  "Project": "feed-release"<br/>}</pre> | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_cloudwatch_log_group_name"></a> [cloudwatch\_log\_group\_name](#output\_cloudwatch\_log\_group\_name) | Name of the CloudWatch log group |
| <a name="output_comprehensive_resource_group_arn"></a> [comprehensive\_resource\_group\_arn](#output\_comprehensive\_resource\_group\_arn) | ARN of the comprehensive resource group (if created) |
| <a name="output_comprehensive_resource_group_name"></a> [comprehensive\_resource\_group\_name](#output\_comprehensive\_resource\_group\_name) | Name of the comprehensive resource group (if created) |
| <a name="output_eventbridge_rule_arns"></a> [eventbridge\_rule\_arns](#output\_eventbridge\_rule\_arns) | ARNs of the EventBridge rules |
| <a name="output_eventbridge_rule_names"></a> [eventbridge\_rule\_names](#output\_eventbridge\_rule\_names) | Names of the EventBridge rules |
| <a name="output_iam_role_arn"></a> [iam\_role\_arn](#output\_iam\_role\_arn) | ARN of the IAM role used by Lambda |
| <a name="output_lambda_function_arn"></a> [lambda\_function\_arn](#output\_lambda\_function\_arn) | ARN of the Lambda function |
| <a name="output_lambda_function_name"></a> [lambda\_function\_name](#output\_lambda\_function\_name) | Name of the Lambda function |
| <a name="output_resource_group_arn"></a> [resource\_group\_arn](#output\_resource\_group\_arn) | ARN of the main resource group |
| <a name="output_resource_group_name"></a> [resource\_group\_name](#output\_resource\_group\_name) | Name of the main resource group |
| <a name="output_schedule_expression"></a> [schedule\_expression](#output\_schedule\_expression) | EventBridge schedule expression used |
<!-- END_TF_DOCS -->
