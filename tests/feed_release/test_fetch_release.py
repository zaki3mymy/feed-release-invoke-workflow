# ruff: noqa: D100
# ruff: noqa: S101
# ruff: noqa: D103
# ruff: noqa: PLC2401, N802
from http import HTTPStatus
from urllib.error import HTTPError

import pook
import pytest

from feed_release.handler import MonitoredRepo, fetch_releases


def test_正常にレスポンスが返ること() -> None:
    # prepare
    owner = "owner"
    name = "repo"
    url = f"https://github.com/{owner}/{name}/releases.atom"
    repo = MonitoredRepo(owner, name)

    # exec
    with pook.api.context():
        exp_res = '<?xml version="1.0" encoding="UTF-8">'
        pook.get(url, reply=200, response_type="xml", response_body=exp_res)
        gen = fetch_releases(repo)

        # verify
        act = next(gen)
        assert exp_res == act.read().decode("utf-8")


def test_リポジトリが存在しないときにエラーとなること() -> None:
    # prepare
    owner = "owner"
    name = "non_exist"
    url = f"https://github.com/{owner}/{name}/releases.atom"
    repo = MonitoredRepo(owner, name)

    # exec
    with pook.api.context():
        exp_res = '<?xml version="1.0" encoding="UTF-8">'
        pook.get(url, reply=404, response_type="xml", response_body=exp_res)
        with pytest.raises(HTTPError) as e:
            next(fetch_releases(repo))
        assert e.value.code == HTTPStatus.NOT_FOUND.value
