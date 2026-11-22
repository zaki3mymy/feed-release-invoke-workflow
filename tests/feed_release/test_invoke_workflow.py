# ruff: noqa: D100
# ruff: noqa: ANN201
# ruff: noqa: D103
# ruff: noqa: S101
# ruff: noqa: PLC2401, N802
from datetime import UTC, datetime
from http import HTTPStatus
from urllib.error import HTTPError

import pook
import pytest

from feed_release.handler import Release, TargetRepo, invoke_workflow

RELEASE = Release(
    "tag:github.com,2008:Repository/1/layer-python/0.22.0",
    datetime(2026, 1, 1, tzinfo=UTC),
    tag="layer-python/0.22.0",
    url="https://github.com/m/repo/releases/tag/layer-python%2F0.22.0",
)


def test_API呼び出し成功():
    # prepare
    owner = "owner"
    name = "repo"
    event_type = "test-event"
    token = "test-token"  # noqa: S105
    url = f"https://api.github.com/repos/{owner}/{name}/dispatches"
    repo = TargetRepo(owner, name, event_type)

    # exec / verify
    with pook.api.context():
        (
            pook.post(url)
            .headers(
                {
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            .json(
                {
                    "event_type": event_type,
                    "client_payload": {
                        "tag": "layer-python/0.22.0",
                        "url": "https://github.com/m/repo/releases/tag/layer-python%2F0.22.0",
                    },
                },
            )
            .reply(200)
        )
        invoke_workflow(repo, token, RELEASE)


def test_API呼び出し権限なし():
    # prepare
    owner = "owner"
    name = "repo"
    event_type = "test-event"
    token = "test-token"  # noqa: S105
    url = f"https://api.github.com/repos/{owner}/{name}/dispatches"
    repo = TargetRepo(owner, name, event_type)

    # exec / verify
    with pook.api.context():
        (
            pook.post(url)
            .headers(
                {
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            .json(
                {
                    "event_type": event_type,
                    "client_payload": {
                        "tag": "layer-python/0.22.0",
                        "url": "https://github.com/m/repo/releases/tag/layer-python%2F0.22.0",
                    },
                },
            )
            .reply(403)
        )
        with pytest.raises(HTTPError) as e:
            invoke_workflow(repo, token, RELEASE)
        assert e.value.code == HTTPStatus.FORBIDDEN.value


def test_API呼び出し失敗():
    # prepare
    owner = "owner"
    name = "repo"
    event_type = "test-event"
    token = "test-token"  # noqa: S105
    url = f"https://api.github.com/repos/{owner}/{name}/dispatches"
    repo = TargetRepo(owner, name, event_type)

    # exec / verify
    with pook.api.context():
        (
            pook.post(url)
            .headers(
                {
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            .json(
                {
                    "event_type": event_type,
                    "client_payload": {
                        "tag": "layer-python/0.22.0",
                        "url": "https://github.com/m/repo/releases/tag/layer-python%2F0.22.0",
                    },
                },
            )
            .reply(500)
        )
        with pytest.raises(HTTPError) as e:
            invoke_workflow(repo, token, RELEASE)
        assert e.value.code == HTTPStatus.INTERNAL_SERVER_ERROR.value
