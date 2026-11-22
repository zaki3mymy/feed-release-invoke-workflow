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
4. 生成されたトークンを SSM Parameter Store に SecureString で登録する（Lambda が実行時に取得する）

```bash
aws ssm put-parameter --region ap-northeast-1 \
  --name /app/feed-release-invoke-workflow/gh-token-for-dispatch --type SecureString \
  --value "ghp_xxxxxxxxxxxx" --overwrite
```

### 監視するリポジトリの設定

監視するリポジトリは Terraform では持たず、S3 の `s3://prod-feed-release-invoke-workflow/repositories.json` に置きます。
Lambda が実行のたびに読むので、書き換えれば次の実行から反映されます。追加・削除・一覧はリポジトリのルートの `README.md` にある `feed-release` コマンドで行います。

| フィールド | 説明 |
|------------|------|
| `name` | 識別名（重複不可） |
| `monitored_owner` | 監視対象リポジトリのオーナー |
| `monitored_repo` | 監視対象リポジトリ名 |
| `target_owner` | ワークフロー実行先のオーナー |
| `target_repo` | ワークフロー実行先のリポジトリ名 |
| `event_type` | GitHub Actionsのイベントタイプ |

### dispatch の記録

エントリーごとに、最後に dispatch できたリリースの ID を DynamoDB のテーブル `prod-feed-release-invoke-workflow-state` に記録します（キーはエントリーの `name`）。
Lambda は最新のリリースの ID を記録と比べて、次のように判定します。

| 記録 | 動き |
|------|------|
| 無い（追加した直後のエントリー） | 今の最新のリリースを記録するだけで、dispatch はしない。リリースが 1 つも無ければ、リリースが無いこと（空文字）を記録する |
| 最新のリリースと違う | dispatch し、成功したときだけ記録を最新のリリースに書き換える |
| 最新のリリースと同じ | 何もしない |

- dispatch に失敗したエントリーは記録が変わらないので、次の実行でやり直されます
- dispatch はできたが記録の書き換えに失敗した場合は、次の実行でもう一度 dispatch されます
- dry run（`{"dry_run": true}`）では記録を読むだけで、書き込みません
- `feed-release remove` でエントリーを消しても記録は残ります。同じ `name` で追加し直すと、前の記録と比べます
- 記録を消したエントリーは、追加した直後と同じ扱い（記録するだけ）になります

```bash
# 記録の一覧
aws dynamodb scan --table-name prod-feed-release-invoke-workflow-state
```

## デプロイ後の確認

### リソースの確認

```bash
# 作成されたリソースの出力値確認
terraform output

# Lambda関数の確認
aws lambda get-function --function-name feed-release

# EventBridgeルールの確認（ルールは1つ）
aws events list-rules --name-prefix feed-release
```

### 動作テスト

```bash
# Lambda関数の dry run（設定の読み込み・フィードの取得・dispatch するかの判断までを行い、dispatch はしない）
aws lambda invoke \
  --function-name feed-release \
  --payload '{"dry_run": true}' --cli-binary-format raw-in-base64-out \
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

`feed-release` コマンドで S3 の設定に追加してください（Terraform の実行は不要です）：

```bash
uv run feed-release add new-repo \
  --monitor owner/repo-name \
  --target my-org/my-app \
  --event new-repo-release
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
   - S3 の設定（`repositories.json`）があり、JSON が壊れていないか確認（`uv run feed-release list`）

2. **GitHub API エラー**
   - SSM パラメータのGitHub Tokenが正しいか確認
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

- GitHub TokenはSSM Parameter Store（SecureString）に置き、Lambdaが実行時に取得します。Terraformの変数・state・Lambdaの環境変数には入りません
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
| <a name="input_config_bucket_name"></a> [config\_bucket\_name](#input\_config\_bucket\_name) | Name of the S3 bucket that holds the repositories config | `string` | `"prod-feed-release-invoke-workflow"` | no |
| <a name="input_create_comprehensive_resource_group"></a> [create\_comprehensive\_resource\_group](#input\_create\_comprehensive\_resource\_group) | Whether to create a comprehensive resource group that includes all AWS resources | `bool` | `false` | no |
| <a name="input_lambda_function_name"></a> [lambda\_function\_name](#input\_lambda\_function\_name) | Name of the Lambda function | `string` | `"feed-release"` | no |
| <a name="input_lambda_memory_size"></a> [lambda\_memory\_size](#input\_lambda\_memory\_size) | Lambda function memory size in MB | `number` | `128` | no |
| <a name="input_lambda_timeout"></a> [lambda\_timeout](#input\_lambda\_timeout) | Lambda function timeout in seconds | `number` | `60` | no |
| <a name="input_output_zip_path"></a> [output\_zip\_path](#input\_output\_zip\_path) | Path where the Lambda deployment zip file will be created | `string` | `"../../../dist/lambda_function.zip"` | no |
| <a name="input_resource_group_name"></a> [resource\_group\_name](#input\_resource\_group\_name) | Name of the AWS Resource Group | `string` | `"feed-release-resources"` | no |
| <a name="input_schedule_expression"></a> [schedule\_expression](#input\_schedule\_expression) | EventBridge schedule expression for checking releases | `string` | `"rate(1 hour)"` | no |
| <a name="input_source_dir"></a> [source\_dir](#input\_source\_dir) | Path to the source directory containing Lambda function code | `string` | `"../../../src/feed_release"` | no |
| <a name="input_state_table_name"></a> [state\_table\_name](#input\_state\_table\_name) | Name of the DynamoDB table that records the last dispatched release for each entry | `string` | `"prod-feed-release-invoke-workflow-state"` | no |
| <a name="input_tags"></a> [tags](#input\_tags) | Tags to apply to all resources | `map(string)` | <pre>{<br/>  "Environment": "production",<br/>  "ManagedBy": "terraform",<br/>  "Project": "feed-release"<br/>}</pre> | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_cloudwatch_log_group_name"></a> [cloudwatch\_log\_group\_name](#output\_cloudwatch\_log\_group\_name) | Name of the CloudWatch log group |
| <a name="output_comprehensive_resource_group_arn"></a> [comprehensive\_resource\_group\_arn](#output\_comprehensive\_resource\_group\_arn) | ARN of the comprehensive resource group (if created) |
| <a name="output_comprehensive_resource_group_name"></a> [comprehensive\_resource\_group\_name](#output\_comprehensive\_resource\_group\_name) | Name of the comprehensive resource group (if created) |
| <a name="output_config_bucket_arn"></a> [config\_bucket\_arn](#output\_config\_bucket\_arn) | ARN of the S3 bucket that holds the repositories config |
| <a name="output_config_bucket_name"></a> [config\_bucket\_name](#output\_config\_bucket\_name) | Name of the S3 bucket that holds the repositories config |
| <a name="output_config_object_key"></a> [config\_object\_key](#output\_config\_object\_key) | Key of the repositories config (JSON) in the S3 bucket |
| <a name="output_eventbridge_rule_arn"></a> [eventbridge\_rule\_arn](#output\_eventbridge\_rule\_arn) | ARN of the EventBridge rule |
| <a name="output_eventbridge_rule_name"></a> [eventbridge\_rule\_name](#output\_eventbridge\_rule\_name) | Name of the EventBridge rule |
| <a name="output_iam_role_arn"></a> [iam\_role\_arn](#output\_iam\_role\_arn) | ARN of the IAM role used by Lambda |
| <a name="output_lambda_function_arn"></a> [lambda\_function\_arn](#output\_lambda\_function\_arn) | ARN of the Lambda function |
| <a name="output_lambda_function_name"></a> [lambda\_function\_name](#output\_lambda\_function\_name) | Name of the Lambda function |
| <a name="output_resource_group_arn"></a> [resource\_group\_arn](#output\_resource\_group\_arn) | ARN of the main resource group |
| <a name="output_resource_group_name"></a> [resource\_group\_name](#output\_resource\_group\_name) | Name of the main resource group |
| <a name="output_schedule_expression"></a> [schedule\_expression](#output\_schedule\_expression) | EventBridge schedule expression used |
| <a name="output_state_table_arn"></a> [state\_table\_arn](#output\_state\_table\_arn) | ARN of the DynamoDB table that records the last dispatched release for each entry |
| <a name="output_state_table_name"></a> [state\_table\_name](#output\_state\_table\_name) | Name of the DynamoDB table that records the last dispatched release for each entry |
<!-- END_TF_DOCS -->
