"""GitHubの最新リリースを購読し、更新があればGitHub Actionsを実行する"""

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
