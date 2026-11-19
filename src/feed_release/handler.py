"""GitHubの最新リリースを購読し、更新があればGitHub Actionsを実行する

監視するリポジトリの設定は S3 の JSON(環境変数 CONFIG_BUCKET・CONFIG_KEY)に置き、
実行のたびに読む。同じリポジトリを監視するエントリーは、フィードの取得を 1 回にまとめる。
"""

import json
import logging
import os
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import cast

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
log_handler = logging.StreamHandler()
log_handler.setLevel(logging.DEBUG)
logger.addHandler(log_handler)
logger.setLevel(logging.DEBUG)

# フィードの取得と dispatch を並列で行うときのスレッド数
MAX_WORKERS = 8

_ENTRY_FIELDS = (
    "name",
    "monitored_owner",
    "monitored_repo",
    "target_owner",
    "target_repo",
    "event_type",
)


class ConfigError(Exception):
    """設定が無い、または壊れている"""


class FeedReleaseError(Exception):
    """一部のリポジトリの処理に失敗した"""


@dataclass(frozen=True)
class MonitoredRepo:
    """リリース監視対象のリポジトリ"""

    owner: str
    name: str


@dataclass(frozen=True)
class TargetRepo:
    """GitHub Actionsを実行するリポジトリ"""

    owner: str
    name: str
    event_type: str


@dataclass(frozen=True)
class Entry:
    """監視するリポジトリの設定の 1 件"""

    name: str
    monitored: MonitoredRepo
    target: TargetRepo


@dataclass
class Release:
    """GitHubリポジトリのリリース情報"""

    id: str
    updated: datetime


def fetch_releases(repo: MonitoredRepo) -> bytes:
    """GitHubリポジトリのリリース情報を取得する"""
    owner = repo.owner
    name = repo.name
    url = f"https://github.com/{owner}/{name}/releases.atom"
    with urllib.request.urlopen(url) as res:
        return res.read()


def parse_atom_feed(xml: bytes) -> Release | None:
    """リリース情報をパースして最新のリリース情報を取得する"""
    ns = "http://www.w3.org/2005/Atom"
    parser = ET.XMLPullParser(["start", "end"])
    parser.feed(xml)
    is_entry = False
    release_id = None
    release_date = None
    for event, elem in parser.read_events():  # ty:ignore[invalid-assignment]
        # `{}`のエスケープがややこしい
        if event == "start" and elem.tag == f"{{{ns}}}entry":  # ty:ignore[possibly-missing-attribute]
            is_entry = True
        elif is_entry and elem.tag == f"{{{ns}}}id":
            release_id = elem.text
        elif is_entry and elem.tag == f"{{{ns}}}updated":
            release_date = elem.text

        if release_id is not None and release_date is not None:
            return Release(release_id, datetime.fromisoformat(release_date))

    return None


def is_latest_release(release: Release) -> bool:
    """最新のリリースであるかどうかを判定する"""
    interval = int(os.environ["INTERVAL_SECOND"])
    now = datetime.now(tz=UTC)
    return (now - timedelta(seconds=interval)) < release.updated


@cache
def get_github_token() -> str:
    """GitHub のトークンを SSM Parameter Store から取得する

    同じ実行環境で呼ばれたときは、取得済みの値を使う。コールドスタートのときだけ取りに行く
    """
    parameter_name = os.environ["GITHUB_TOKEN_PARAMETER_NAME"]
    ssm = boto3.client("ssm")
    res = ssm.get_parameter(Name=parameter_name, WithDecryption=True)
    return res["Parameter"]["Value"]


def invoke_workflow(repo: TargetRepo, token: str) -> None:
    """GItHub Actionsを実行する"""
    # https://docs.github.com/ja/rest/actions/workflow-runs?apiVersion=2022-11-28
    owner = repo.owner
    name = repo.name
    event_type = repo.event_type
    url = f"https://api.github.com/repos/{owner}/{name}/dispatches"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body = {
        "event_type": event_type,
        "client_payload": {},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as res:
            return res.read()
    except urllib.error.HTTPError:  # noqa: TRY203
        raise


def parse_entries(body: bytes, location: str) -> list[Entry]:
    """設定の JSON を読む。形が違うときは ConfigError にする"""
    try:
        data = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        msg = f"設定 {location} の JSON が壊れています: {e}"
        raise ConfigError(msg) from e
    if not isinstance(data, list):
        msg = f"設定 {location} は配列にしてください"
        raise ConfigError(msg)

    entries: list[Entry] = []
    for index, item in enumerate(cast("list[object]", data), start=1):
        if not isinstance(item, dict):
            msg = f"設定 {location} の {index} 件目がオブジェクトではありません"
            raise ConfigError(msg)
        obj = cast("dict[str, object]", item)
        values = {f: v for f in _ENTRY_FIELDS if isinstance(v := obj.get(f), str) and v}
        missing = [f for f in _ENTRY_FIELDS if f not in values]
        if missing:
            msg = f"設定 {location} の {index} 件目に {', '.join(missing)} がありません"
            raise ConfigError(msg)
        entries.append(
            Entry(
                name=values["name"],
                monitored=MonitoredRepo(values["monitored_owner"], values["monitored_repo"]),
                target=TargetRepo(
                    values["target_owner"],
                    values["target_repo"],
                    values["event_type"],
                ),
            ),
        )

    names = [e.name for e in entries]
    duplicated = sorted({n for n in names if names.count(n) > 1})
    if duplicated:
        msg = f"設定 {location} の name が重複しています: {', '.join(duplicated)}"
        raise ConfigError(msg)
    return entries


def load_entries() -> list[Entry]:
    """S3 から監視するリポジトリの設定を読む"""
    bucket = os.environ["CONFIG_BUCKET"]
    key = os.environ["CONFIG_KEY"]
    location = f"s3://{bucket}/{key}"
    s3 = boto3.client("s3")
    try:
        res = s3.get_object(Bucket=bucket, Key=key)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "NoSuchKey":
            msg = f"設定 {location} がありません"
            raise ConfigError(msg) from e
        raise
    return parse_entries(res["Body"].read(), location)


def check_latest_release(repo: MonitoredRepo) -> bool:
    """リポジトリに新しいリリースがあるかを調べる"""
    logger.info('fetch release: "%s/%s"', repo.owner, repo.name)
    release = parse_atom_feed(fetch_releases(repo))
    logger.info(release)
    if release is None:
        logger.info('No release: "%s/%s"', repo.owner, repo.name)
        return False
    latest = is_latest_release(release)
    if not latest:
        logger.info('No latest release: "%s/%s"', repo.owner, repo.name)
    return latest


def _run_parallel[K, V](items: list[K], func: Callable[[K], V]) -> dict[K, V | Exception]:
    """並列で items ごとに func を呼び、結果か例外を返す"""
    results: dict[K, V | Exception] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(func, item): item for item in items}
        for future in as_completed(futures):
            item = futures[future]
            try:
                results[item] = future.result()
            except Exception as e:  # noqa: BLE001  1 件が失敗しても残りは続ける
                results[item] = e
    return results


def main(entries: list[Entry], *, dry_run: bool = False) -> dict[str, object]:
    """全エントリーのリリースを調べ、新しいリリースがあれば GitHub Actions を実行する

    1 件が失敗しても残りは続け、最後に失敗をまとめて FeedReleaseError にする。
    dry_run のときは dispatch せず、dispatch するはずだったエントリーを返す。
    """
    groups: dict[MonitoredRepo, list[Entry]] = {}
    for entry in entries:
        groups.setdefault(entry.monitored, []).append(entry)

    errors: list[str] = []
    to_dispatch: list[Entry] = []
    for repo, checked in _run_parallel(list(groups), check_latest_release).items():
        if isinstance(checked, Exception):
            logger.error('Failed to check release: "%s/%s": %s', repo.owner, repo.name, checked)
            errors.append(f"{repo.owner}/{repo.name}: {checked}")
        elif checked:
            to_dispatch.extend(groups[repo])
    to_dispatch.sort(key=lambda e: e.name)

    dispatched: list[str] = []
    if to_dispatch and not dry_run:
        token = get_github_token()
        results = _run_parallel(to_dispatch, lambda e: invoke_workflow(e.target, token))
        for entry in to_dispatch:
            result = results[entry]
            target = entry.target
            if isinstance(result, Exception):
                logger.error('Failed to invoke workflow: "%s": %s', entry.name, result)
                errors.append(f"{entry.name}: {result}")
            else:
                logger.info(
                    'Invoke workflow: "%s/%s(%s)"',
                    target.owner,
                    target.name,
                    target.event_type,
                )
                dispatched.append(entry.name)

    summary: dict[str, object] = {
        "dry_run": dry_run,
        "entries": len(entries),
        "monitored_repos": len(groups),
    }
    if dry_run:
        summary["would_dispatch"] = [e.name for e in to_dispatch]
    else:
        summary["dispatched"] = dispatched
    logger.info(json.dumps(summary, ensure_ascii=False))

    if errors:
        msg = f"{len(errors)} 件の処理に失敗しました: " + "; ".join(sorted(errors))
        raise FeedReleaseError(msg)
    return summary


def lambda_function(event: Mapping[str, object] | None, _) -> dict[str, object]:  # noqa: ANN001
    """Lambda関数のエントリーポイント

    EventBridge のスケジュールからは決まった形のイベントが来るが、使うのは dry_run だけ。
    {"dry_run": true} のときは、設定の読み込み・フィードの取得・dispatch するかの判断までを行う
    """
    dry_run = isinstance(event, dict) and event.get("dry_run") is True
    return main(load_entries(), dry_run=dry_run)
