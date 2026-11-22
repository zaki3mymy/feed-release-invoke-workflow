# Feed Release

GitHubリポジトリのリリースを監視し、更新があったらGitHub Actionsを実行する。

- [ワークフローの実行](https://docs.github.com/ja/rest/actions/workflow-runs?apiVersion=2022-11-28)
- [GitHubのRSSフィード](https://www.reddit.com/r/rss/comments/1cqmwsn/github_rss_feeds/?tl=ja)

## 監視するリポジトリの設定

監視するリポジトリの設定は、S3 の `s3://prod-feed-release-invoke-workflow/repositories.json` に置く。
追加・削除・一覧は `feed-release` コマンドで行う。ローカルの AWS の認証情報で S3 を読み書きする。

```shell
# 一覧
uv run feed-release list

# 追加（name は重複不可）
uv run feed-release add otel-lambda-anime-schedules \
  --monitor open-telemetry/opentelemetry-lambda \
  --target zaki3mymy/anime-schedules \
  --event otel-lambda-release

# 削除
uv run feed-release remove otel-lambda-anime-schedules
```

- `--profile` で AWS のプロファイル、`--bucket`（環境変数 `FEED_RELEASE_BUCKET`）でバケットを指定できる。
- 書き込みは、読んだときの ETag を条件にする（`If-Match`）。同時に書き換えられていたら、エラーにして書き込まない。
- バケットはバージョニングを有効にしているので、前の設定に戻せる（古いバージョンは 10 個まで残る）。
- 追加したエントリーは、次の実行で今の最新リリースを記録するだけで、dispatch はしない。それより後に出たリリースから dispatch する。
  記録の詳しい動きは `terraform/environments/production/README.md` の「dispatch の記録」を参照。

## 起動される側の workflow

`repository_dispatch` の `event_type` に設定の `event_type` を、`client_payload` にリリースのタグと URL を入れて送る。

```yaml
on:
  repository_dispatch:
    types: [otel-lambda-release]

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - env:
          # 例: layer-python/0.22.0
          TAG: ${{ github.event.client_payload.tag }}
          # 例: https://github.com/open-telemetry/opentelemetry-lambda/releases/tag/layer-python%2F0.22.0
          URL: ${{ github.event.client_payload.url }}
        run: echo "$TAG $URL"
```

- タグは監視先のリポジトリが決める値なので、`run` に `${{ }}` で直接埋め込まず、環境変数を通して使う（スクリプトインジェクションを防ぐ）。

- タグの `/` は URL では `%2F` になるが、`tag` には元のタグ（`/` のまま）が入る。
- まれに、dispatch はできたが記録の書き換えに失敗すると、同じリリースでもう一度 dispatch される。二重に動いても問題ないようにしておく。
