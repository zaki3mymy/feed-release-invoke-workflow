"""GitHubの最新リリースを購読し、更新があればGitHub Actionsを実行する"""

import json
import os
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass
class MonitoredRepo:
    """リリース監視対象のリポジトリ"""

    owner: str
    name: str


@dataclass
class TargetRepo:
    """GitHub Actionsを実行するリポジトリ"""

    owner: str
    name: str
    event_type: str


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
