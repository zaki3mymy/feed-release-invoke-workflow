# ruff: noqa: D100
# ruff: noqa: ANN201, ANN401
# ruff: noqa: D103
# ruff: noqa: S101
# ruff: noqa: N802, PLC2401
from typing import Any

import pook
import pytest
from freezegun import freeze_time

from feed_release import handler
from feed_release.handler import (
    Entry,
    FeedReleaseError,
    MonitoredRepo,
    TargetRepo,
    lambda_function,
    main,
)

TOKEN = "test-token"  # noqa: S105

NO_RELEASE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <id>tag:github.com,2008:https://github.com/owner/repo/releases</id>
  <updated>2025-12-19T04:08:17+09:00</updated>
</feed>
"""

RELEASE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <id>tag:github.com,2008:https://github.com/owner/repo/releases</id>
  <updated>2025-12-19T04:08:17+09:00</updated>
  <entry>
    <id>test-id</id>
    <updated>2026-01-01T12:34:56+09:00</updated>
    <title>0.1.0</title>
  </entry>
</feed>
"""

# RELEASE_XML のリリースが「新しい」と判定される時刻。INTERVAL_SECOND は 60
NEW = "2026-01-01T12:34:57+09:00"
# RELEASE_XML のリリースが「古い」と判定される時刻
OLD = "2026-01-01T12:35:57+09:00"


@pytest.fixture(autouse=True)
def setup_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INTERVAL_SECOND", "60")
    # SSM には取りに行かず、決まったトークンを返す
    monkeypatch.setattr(handler, "get_github_token", lambda: TOKEN)


def entry(name: str, monitored: str, target: str, event_type: str = "release") -> Entry:
    m_owner, m_repo = monitored.split("/")
    t_owner, t_repo = target.split("/")
    return Entry(name, MonitoredRepo(m_owner, m_repo), TargetRepo(t_owner, t_repo, event_type))


def mock_feed(repo: str, xml: str, status: int = 200) -> Any:
    return pook.get(f"https://github.com/{repo}/releases.atom").times(1).reply(status).xml(xml).mock


def mock_dispatch(repo: str, event_type: str = "release", status: int = 204) -> Any:
    return (
        pook.post(f"https://api.github.com/repos/{repo}/dispatches")
        .header("Authorization", f"Bearer {TOKEN}")
        .json({"event_type": event_type, "client_payload": {}})
        .times(1)
        .reply(status)
        .mock
    )


@freeze_time(NEW)
def test_リリースが無いときはdispatchしないこと():
    with pook.api.context():
        feed = mock_feed("m/repo", NO_RELEASE_XML)
        dispatch = pook.post("https://api.github.com/repos/t/repo/dispatches")

        result = main([entry("a", "m/repo", "t/repo")])

        assert feed.calls == 1
        assert dispatch.calls == 0
        assert result == {"dry_run": False, "entries": 1, "monitored_repos": 1, "dispatched": []}


@freeze_time(OLD)
def test_新しいリリースが無いときはdispatchしないこと():
    with pook.api.context():
        feed = mock_feed("m/repo", RELEASE_XML)
        dispatch = pook.post("https://api.github.com/repos/t/repo/dispatches")

        result = main([entry("a", "m/repo", "t/repo")])

        assert feed.calls == 1
        assert dispatch.calls == 0
        assert result["dispatched"] == []


@freeze_time(NEW)
def test_同じリポジトリを監視するエントリーはフィードの取得を1回にまとめること():
    otel = "open-telemetry/opentelemetry-lambda"
    with pook.api.context():
        feed = mock_feed(otel, RELEASE_XML)
        other_feed = mock_feed("astral-sh/ruff", NO_RELEASE_XML)
        d1 = mock_dispatch("zaki3mymy/anime-schedules", "otel")
        d2 = mock_dispatch("zaki3mymy/nandemo-oshirase", "otel")
        d3 = mock_dispatch("zaki3mymy/shopping-reminder", "otel")
        entries = [
            entry("otel-b", otel, "zaki3mymy/nandemo-oshirase", "otel"),
            entry("otel-a", otel, "zaki3mymy/anime-schedules", "otel"),
            entry("ruff", "astral-sh/ruff", "zaki3mymy/RuffMate"),
            entry("otel-c", otel, "zaki3mymy/shopping-reminder", "otel"),
        ]

        result = main(entries)

        assert feed.calls == 1
        assert other_feed.calls == 1
        assert (d1.calls, d2.calls, d3.calls) == (1, 1, 1)
        assert result == {
            "dry_run": False,
            "entries": 4,
            "monitored_repos": 2,
            "dispatched": ["otel-a", "otel-b", "otel-c"],
        }


@freeze_time(NEW)
def test_dry_runのときはdispatchせずにdispatchするはずだったエントリーを返すこと(
    monkeypatch: pytest.MonkeyPatch,
):
    def _no_token() -> str:
        msg = "dry run ではトークンを取りに行かない"
        raise AssertionError(msg)

    monkeypatch.setattr(handler, "get_github_token", _no_token)
    with pook.api.context():
        mock_feed("m/repo", RELEASE_XML)
        dispatch = pook.post("https://api.github.com/repos/t/repo/dispatches")

        result = main([entry("a", "m/repo", "t/repo")], dry_run=True)

        assert dispatch.calls == 0
        assert result == {
            "dry_run": True,
            "entries": 1,
            "monitored_repos": 1,
            "would_dispatch": ["a"],
        }


@freeze_time(NEW)
def test_フィードの取得に失敗しても残りは続けて最後にエラーにすること():
    with pook.api.context():
        mock_feed("m/missing", "", status=404)
        mock_feed("m/repo", RELEASE_XML)
        dispatch = mock_dispatch("t/repo")
        entries = [entry("missing", "m/missing", "t/other"), entry("ok", "m/repo", "t/repo")]

        with pytest.raises(
            FeedReleaseError,
            match=r"1 件の処理に失敗しました: m/missing: HTTP Error 404",
        ):
            main(entries)

        assert dispatch.calls == 1


@freeze_time(NEW)
def test_dispatchに失敗しても残りは続けて最後にエラーにすること():
    with pook.api.context():
        mock_feed("m/repo", RELEASE_XML)
        ok = mock_dispatch("t/ok")
        mock_dispatch("t/ng", status=403)
        entries = [entry("ng", "m/repo", "t/ng"), entry("ok", "m/repo", "t/ok")]

        with pytest.raises(FeedReleaseError, match=r"ng: HTTP Error 403"):
            main(entries)

        assert ok.calls == 1


@freeze_time(NEW)
def test_lambda_functionは設定を読んで全エントリーを処理すること(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(handler, "load_entries", lambda: [entry("a", "m/repo", "t/repo")])
    with pook.api.context():
        mock_feed("m/repo", RELEASE_XML)
        dispatch = mock_dispatch("t/repo")

        # EventBridge のスケジュールから来るイベント
        event: Any = {"source": "aws.events", "detail-type": "Scheduled Event", "detail": {}}
        result = lambda_function(event, None)

        assert dispatch.calls == 1
        assert result["dispatched"] == ["a"]


@pytest.mark.parametrize(
    ("event", "dry_run"),
    [({"dry_run": True}, True), ({"dry_run": "true"}, False), ({}, False), (None, False)],
)
def test_lambda_functionはdry_runがtrueのときだけdry_runにすること(
    monkeypatch: pytest.MonkeyPatch,
    event: Any,
    *,
    dry_run: bool,
):
    monkeypatch.setattr(handler, "load_entries", list)

    result = lambda_function(event, None)

    assert result["dry_run"] is dry_run
