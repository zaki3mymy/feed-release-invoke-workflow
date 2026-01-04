"""GitHubの最新リリースを購読し、更新があればGitHub Actionsを実行する"""

import urllib.request
from http.client import HTTPResponse


def fetch_latest_release(owner: str, repo: str) -> HTTPResponse:
    """GitHubリポジトリのリリース情報を取得する"""
    url = f"https://github.com/{owner}/{repo}/releases.atom"
    with urllib.request.urlopen(url) as res:
        return res
