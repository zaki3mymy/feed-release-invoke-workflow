"""``feed-release`` コマンド: 監視するリポジトリの設定(S3 の repositories.json)を管理する

設定は S3 にだけ置き、このリポジトリには置かない。書き込みは読んだときの ETag を使った
条件付きの書き込み(If-Match)にして、同時に書き換えても上書きし合わないようにする。
"""

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from typing import Any, cast

from botocore.exceptions import BotoCoreError, ClientError

DEFAULT_BUCKET = "prod-feed-release-invoke-workflow"
DEFAULT_KEY = "repositories.json"
DEFAULT_REGION = "ap-northeast-1"

_NAME_PATTERN = re.compile(r"^[0-9A-Za-z_.-]{1,64}$")
# GitHub のオーナー名・リポジトリ名に使える文字
_REPO_PART_PATTERN = re.compile(r"^[0-9A-Za-z_.-]{1,100}$")
# repository_dispatch の event_type は 100 文字まで
_EVENT_TYPE_MAX_LENGTH = 100

_FIELDS = (
    "name",
    "monitored_owner",
    "monitored_repo",
    "target_owner",
    "target_repo",
    "event_type",
)


class CliError(Exception):
    """利用者に見せるエラー"""


@dataclass(frozen=True)
class Entry:
    """監視するリポジトリの設定の 1 件"""

    name: str
    monitored_owner: str
    monitored_repo: str
    target_owner: str
    target_repo: str
    event_type: str

    @classmethod
    def from_dict(cls, data: object, index: int) -> Entry:
        """JSON の 1 件から作る。形が違うときは CliError にする"""
        if not isinstance(data, dict):
            msg = f"{index} 件目がオブジェクトではありません"
            raise CliError(msg)
        obj = cast("dict[str, object]", data)
        values: dict[str, str] = {}
        missing: list[str] = []
        for field in _FIELDS:
            value = obj.get(field)
            if isinstance(value, str) and value:
                values[field] = value
            else:
                missing.append(field)
        if missing:
            msg = f"{index} 件目に {', '.join(missing)} がありません(文字列で指定してください)"
            raise CliError(msg)
        return cls(**values)

    def to_dict(self) -> dict[str, str]:
        """JSON に書く形にする"""
        return asdict(self)


def validate_name(name: str) -> str:
    """エントリーの名前を確かめる"""
    if not _NAME_PATTERN.match(name):
        msg = f"名前は英数字と - _ . だけ、64 文字以内で指定してください: {name!r}"
        raise CliError(msg)
    return name


def parse_repo(value: str, option: str) -> tuple[str, str]:
    """``owner/repo`` の形の文字列をオーナー名とリポジトリ名に分ける"""
    parts = value.split("/")
    if len(parts) != 2 or not all(_REPO_PART_PATTERN.match(p) for p in parts):  # noqa: PLR2004
        msg = f"{option} は <owner>/<repo> の形で指定してください: {value!r}"
        raise CliError(msg)
    return parts[0], parts[1]


def validate_event_type(event_type: str) -> str:
    """repository_dispatch の event_type を確かめる"""
    if not event_type.strip() or len(event_type) > _EVENT_TYPE_MAX_LENGTH:
        msg = f"--event は 1〜{_EVENT_TYPE_MAX_LENGTH} 文字で指定してください: {event_type!r}"
        raise CliError(msg)
    return event_type


def parse_entries(body: bytes) -> list[Entry]:
    """設定の JSON を読む"""
    try:
        data = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        msg = f"設定の JSON が壊れています: {e}"
        raise CliError(msg) from e
    if not isinstance(data, list):
        msg = "設定の JSON は配列にしてください"
        raise CliError(msg)
    entries = [Entry.from_dict(d, i) for i, d in enumerate(data, start=1)]
    names = [e.name for e in entries]
    duplicated = sorted({n for n in names if names.count(n) > 1})
    if duplicated:
        msg = f"設定の name が重複しています: {', '.join(duplicated)}"
        raise CliError(msg)
    return entries


def dump_entries(entries: list[Entry]) -> bytes:
    """設定を JSON にする"""
    text = json.dumps([e.to_dict() for e in entries], ensure_ascii=False, indent=2)
    return (text + "\n").encode("utf-8")


class ConfigStore:
    """S3 に置いた設定を読み書きする"""

    def __init__(self, s3: Any, bucket: str, key: str) -> None:  # noqa: ANN401
        """設定を置くバケットとキーを指定する"""
        self.s3 = s3
        self.bucket = bucket
        self.key = key

    @property
    def location(self) -> str:
        """設定の場所(表示用)"""
        return f"s3://{self.bucket}/{self.key}"

    def load(self) -> tuple[list[Entry], str | None]:
        """設定と ETag を読む。設定がまだ無いときは空の設定と None を返す"""
        try:
            res = self.s3.get_object(Bucket=self.bucket, Key=self.key)
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return [], None
            raise
        return parse_entries(res["Body"].read()), res["ETag"]

    def save(self, entries: list[Entry], etag: str | None) -> None:
        """読んだときから書き換えられていないときだけ、設定を書き込む"""
        params: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": self.key,
            "Body": dump_entries(entries),
            "ContentType": "application/json",
        }
        # 読んだときに無かったら、まだ無いときだけ作る
        if etag is None:
            params["IfNoneMatch"] = "*"
        else:
            params["IfMatch"] = etag
        try:
            self.s3.put_object(**params)
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code in ("PreconditionFailed", "ConditionalRequestConflict"):
                msg = "読み込んだあとに設定が書き換えられました。もう一度実行してください"
                raise CliError(msg) from e
            raise


def format_entry(entry: Entry) -> str:
    """1 件を表示する形にする"""
    return (
        f"{entry.name}  {entry.monitored_owner}/{entry.monitored_repo}"
        f" -> {entry.target_owner}/{entry.target_repo}  ({entry.event_type})"
    )


def build_parser() -> argparse.ArgumentParser:
    """引数のパーサーを作る"""
    parser = argparse.ArgumentParser(
        prog="feed-release",
        description="監視するリポジトリの設定(S3 の repositories.json)を管理する",
    )
    parser.add_argument(
        "--bucket",
        default=os.environ.get("FEED_RELEASE_BUCKET", DEFAULT_BUCKET),
        help=f"設定を置く S3 バケット(既定: {DEFAULT_BUCKET}、環境変数 FEED_RELEASE_BUCKET)",
    )
    parser.add_argument("--key", default=DEFAULT_KEY, help=f"設定のキー(既定: {DEFAULT_KEY})")
    parser.add_argument("--profile", help="AWS のプロファイル名")
    parser.add_argument("--region", default=DEFAULT_REGION, help="AWS のリージョン")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    sub.add_parser("list", help="設定を一覧する")

    p = sub.add_parser("add", help="エントリーを足す")
    p.add_argument("name", help="名前(英数字と - _ .、重複不可)")
    p.add_argument("--monitor", required=True, metavar="OWNER/REPO", help="リリースを監視する")
    p.add_argument(
        "--target",
        required=True,
        metavar="OWNER/REPO",
        help="repository_dispatch を送る",
    )
    p.add_argument("--event", required=True, metavar="EVENT_TYPE", help="送る event_type")

    p = sub.add_parser("remove", help="エントリーを消す")
    p.add_argument("name")

    return parser


def run(args: argparse.Namespace, store: ConfigStore) -> str:
    """コマンドを実行し、表示する文字列を返す"""
    if args.command == "list":
        entries, _ = store.load()
        if not entries:
            return f"監視するリポジトリは登録されていません({store.location})"
        return "\n".join(format_entry(e) for e in entries)

    name = validate_name(args.name)

    if args.command == "add":
        monitored_owner, monitored_repo = parse_repo(args.monitor, "--monitor")
        target_owner, target_repo = parse_repo(args.target, "--target")
        entry = Entry(
            name=name,
            monitored_owner=monitored_owner,
            monitored_repo=monitored_repo,
            target_owner=target_owner,
            target_repo=target_repo,
            event_type=validate_event_type(args.event),
        )
        entries, etag = store.load()
        if any(e.name == name for e in entries):
            msg = f"{name!r} は既に登録されています"
            raise CliError(msg)
        store.save([*entries, entry], etag)
        return "追加しました: " + format_entry(entry)

    # remove
    entries, etag = store.load()
    remaining = [e for e in entries if e.name != name]
    if len(remaining) == len(entries):
        msg = f"{name!r} は登録されていません"
        raise CliError(msg)
    store.save(remaining, etag)
    return f"削除しました: {name}"


def create_store(args: argparse.Namespace) -> ConfigStore:  # pragma: no cover
    """AWS の認証情報から ConfigStore を作る"""
    import boto3  # noqa: PLC0415

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    return ConfigStore(session.client("s3"), args.bucket, args.key)


def main(argv: list[str] | None = None, store: ConfigStore | None = None) -> int:
    """CLI のエントリーポイント"""
    args = build_parser().parse_args(argv)
    try:
        print(run(args, store or create_store(args)))  # noqa: T201
    except CliError as e:
        print(f"エラー: {e}", file=sys.stderr)  # noqa: T201
        return 1
    except ClientError as e:
        err = e.response["Error"]
        print(f"AWS のエラー: {err.get('Code')}: {err.get('Message')}", file=sys.stderr)  # noqa: T201
        return 1
    except BotoCoreError as e:
        print(f"AWS のエラー: {e}(認証情報や --profile を確認してください)", file=sys.stderr)  # noqa: T201
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
