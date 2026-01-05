"""GitHubの最新リリースを購読し、更新があればGitHub Actionsを実行する"""

import json
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from http.client import HTTPResponse


def fetch_latest_release(owner: str, repo: str) -> HTTPResponse:
    """GitHubリポジトリのリリース情報を取得する"""
    url = f"https://github.com/{owner}/{repo}/releases.atom"
    with urllib.request.urlopen(url) as res:
        return res


def parse_atom_feed(res: HTTPResponse) -> str | None:
    """リリース情報をパースする"""
    ns = "http://www.w3.org/2005/Atom"
    context = ET.iterparse(res, events=("start", "end"))  # noqa: S314 # ソースはgithub.comなので警告無視
    is_entry = False
    for event, elem in context:
        if event == "end":
            elem.clear()
            continue

        # `{}`のエスケープがややこしい
        if event == "start" and elem.tag == f"{{{ns}}}entry":
            is_entry = True
        elif is_entry and elem.tag == f"{{{ns}}}id":
            return elem.text

    return None


def invoke_workflow(owner: str, repo: str, event_type: str, token: str) -> None:
    """GItHub Actionsを実行する"""
    # https://docs.github.com/ja/actions/reference/workflows-and-actions/events-that-trigger-workflows#repository_dispatch
    url = f"https://api.github.com/repos/{owner}/{repo}/dispatches"
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
