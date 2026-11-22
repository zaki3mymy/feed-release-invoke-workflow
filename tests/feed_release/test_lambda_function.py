# ruff: noqa: D100
# ruff: noqa: ANN201, ANN401
# ruff: noqa: D102, D103, D107
# ruff: noqa: S101
# ruff: noqa: N802, PLC2401
from typing import Any

import pook
import pytest

from feed_release import handler
from feed_release.handler import (
    NO_RELEASE,
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

RELEASE_ID = "tag:github.com,2008:Repository/1/0.2.0"
OLD_RELEASE_ID = "tag:github.com,2008:Repository/1/0.1.0"
RELEASE_URL = "https://github.com/m/repo/releases/tag/0.2.0"

RELEASE_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <id>tag:github.com,2008:https://github.com/owner/repo/releases</id>
  <updated>2025-12-19T04:08:17+09:00</updated>
  <entry>
    <id>{RELEASE_ID}</id>
    <updated>2026-01-01T12:34:56+09:00</updated>
    <link rel="alternate" type="text/html" href="{RELEASE_URL}"/>
    <title>0.2.0</title>
  </entry>
</feed>
"""


class FakeState:
    """メモリに記録する DispatchState。fail_get・fail_put に入れた name は例外にする"""

    def __init__(self, records: dict[str, str] | None = None) -> None:
        self.records = dict(records or {})
        self.puts: list[tuple[str, str]] = []
        self.fail_get: set[str] = set()
        self.fail_put: set[str] = set()

    def get(self, name: str) -> str | None:
        if name in self.fail_get:
            msg = f"get failed: {name}"
            raise RuntimeError(msg)
        return self.records.get(name)

    def put(self, name: str, release_id: str) -> None:
        if name in self.fail_put:
            msg = f"put failed: {name}"
            raise RuntimeError(msg)
        self.records[name] = release_id
        self.puts.append((name, release_id))


@pytest.fixture(autouse=True)
def setup_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONFIG_BUCKET", "test-bucket")
    monkeypatch.setenv("CONFIG_KEY", "repositories.json")
    monkeypatch.setenv("STATE_TABLE_NAME", "test-table")
    # SSM には取りに行かず、決まったトークンを返す
    monkeypatch.setattr(handler, "get_github_token", lambda: TOKEN)


def _no_token() -> str:
    msg = "トークンを取りに行かない"
    raise AssertionError(msg)


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
        .json(
            {
                "event_type": event_type,
                "client_payload": {"tag": "0.2.0", "url": RELEASE_URL},
            },
        )
        .times(1)
        .reply(status)
        .mock
    )


def test_記録と違うリリースがあればdispatchして記録を書き換えること():
    state = FakeState({"a": OLD_RELEASE_ID})
    with pook.api.context():
        feed = mock_feed("m/repo", RELEASE_XML)
        dispatch = mock_dispatch("t/repo")

        result = main([entry("a", "m/repo", "t/repo")], state)

        assert feed.calls == 1
        assert dispatch.calls == 1
        assert state.records == {"a": RELEASE_ID}
        assert result == {
            "dry_run": False,
            "entries": 1,
            "monitored_repos": 1,
            "dispatched": ["a"],
            "initialized": [],
        }


def test_記録と同じリリースのときはdispatchしないこと(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(handler, "get_github_token", _no_token)
    state = FakeState({"a": RELEASE_ID})
    with pook.api.context():
        mock_feed("m/repo", RELEASE_XML)
        dispatch = pook.post("https://api.github.com/repos/t/repo/dispatches")

        result = main([entry("a", "m/repo", "t/repo")], state)

        assert dispatch.calls == 0
        assert state.puts == []
        assert result["dispatched"] == []
        assert result["initialized"] == []


def test_記録が無いエントリーは今のリリースを記録するだけでdispatchしないこと(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(handler, "get_github_token", _no_token)
    state = FakeState()
    with pook.api.context():
        mock_feed("m/repo", RELEASE_XML)
        dispatch = pook.post("https://api.github.com/repos/t/repo/dispatches")

        result = main([entry("a", "m/repo", "t/repo")], state)

        assert dispatch.calls == 0
        assert state.records == {"a": RELEASE_ID}
        assert result["dispatched"] == []
        assert result["initialized"] == ["a"]


def test_リリースが無いリポジトリは記録が無ければリリースが無いことを記録すること(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(handler, "get_github_token", _no_token)
    state = FakeState()
    with pook.api.context():
        mock_feed("m/repo", NO_RELEASE_XML)
        dispatch = pook.post("https://api.github.com/repos/t/repo/dispatches")

        result = main([entry("a", "m/repo", "t/repo")], state)

        assert dispatch.calls == 0
        assert state.records == {"a": NO_RELEASE}
        assert result["initialized"] == ["a"]


def test_リリースが無いことを記録したあとで最初のリリースが出たらdispatchすること():
    state = FakeState({"a": NO_RELEASE})
    with pook.api.context():
        mock_feed("m/repo", RELEASE_XML)
        dispatch = mock_dispatch("t/repo")

        result = main([entry("a", "m/repo", "t/repo")], state)

        assert dispatch.calls == 1
        assert state.records == {"a": RELEASE_ID}
        assert result["dispatched"] == ["a"]


def test_リリースが無くなっても記録があればdispatchも記録の書き換えもしないこと(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(handler, "get_github_token", _no_token)
    state = FakeState({"a": RELEASE_ID})
    with pook.api.context():
        mock_feed("m/repo", NO_RELEASE_XML)

        result = main([entry("a", "m/repo", "t/repo")], state)

        assert state.puts == []
        assert result["dispatched"] == []
        assert result["initialized"] == []


def test_同じリポジトリを監視するエントリーはフィードの取得を1回にまとめること():
    otel = "open-telemetry/opentelemetry-lambda"
    state = FakeState(
        {
            "otel-a": OLD_RELEASE_ID,
            "otel-b": OLD_RELEASE_ID,
            "otel-c": OLD_RELEASE_ID,
            "ruff": NO_RELEASE,
        },
    )
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

        result = main(entries, state)

        assert feed.calls == 1
        assert other_feed.calls == 1
        assert (d1.calls, d2.calls, d3.calls) == (1, 1, 1)
        assert result == {
            "dry_run": False,
            "entries": 4,
            "monitored_repos": 2,
            "dispatched": ["otel-a", "otel-b", "otel-c"],
            "initialized": [],
        }


def test_同じリポジトリを監視していても記録はエントリーごとに比べること():
    # 前の実行で b だけ dispatch に失敗して、記録が古いまま残っている
    state = FakeState({"a": RELEASE_ID, "b": OLD_RELEASE_ID})
    with pook.api.context():
        mock_feed("m/repo", RELEASE_XML)
        da = pook.post("https://api.github.com/repos/t/a/dispatches")
        db = mock_dispatch("t/b")

        result = main([entry("a", "m/repo", "t/a"), entry("b", "m/repo", "t/b")], state)

        assert da.calls == 0
        assert db.calls == 1
        assert result["dispatched"] == ["b"]


def test_dry_runのときはdispatchも記録の書き込みもせずにするはずだったエントリーを返すこと(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(handler, "get_github_token", _no_token)
    state = FakeState({"a": OLD_RELEASE_ID})
    with pook.api.context():
        mock_feed("m/repo", RELEASE_XML)
        dispatch = pook.post("https://api.github.com/repos/t/repo/dispatches")

        result = main(
            [entry("a", "m/repo", "t/repo"), entry("new", "m/repo", "t/new")],
            state,
            dry_run=True,
        )

        assert dispatch.calls == 0
        assert state.puts == []
        assert result == {
            "dry_run": True,
            "entries": 2,
            "monitored_repos": 1,
            "would_dispatch": ["a"],
            "would_initialize": ["new"],
        }


def test_フィードの取得に失敗しても残りは続けて最後にエラーにすること():
    state = FakeState({"missing": OLD_RELEASE_ID, "ok": OLD_RELEASE_ID})
    with pook.api.context():
        mock_feed("m/missing", "", status=404)
        mock_feed("m/repo", RELEASE_XML)
        dispatch = mock_dispatch("t/repo")
        entries = [entry("missing", "m/missing", "t/other"), entry("ok", "m/repo", "t/repo")]

        with pytest.raises(
            FeedReleaseError,
            match=r"1 件の処理に失敗しました: m/missing: HTTP Error 404",
        ):
            main(entries, state)

        assert dispatch.calls == 1
        assert state.records == {"missing": OLD_RELEASE_ID, "ok": RELEASE_ID}


def test_dispatchに失敗したエントリーは記録を書き換えずに次の実行でやり直すこと():
    state = FakeState({"ng": OLD_RELEASE_ID, "ok": OLD_RELEASE_ID})
    entries = [entry("ng", "m/repo", "t/ng"), entry("ok", "m/repo", "t/ok")]
    with pook.api.context():
        mock_feed("m/repo", RELEASE_XML)
        ok = mock_dispatch("t/ok")
        mock_dispatch("t/ng", status=403)

        with pytest.raises(FeedReleaseError, match=r"ng: HTTP Error 403"):
            main(entries, state)

        assert ok.calls == 1
        assert state.records == {"ng": OLD_RELEASE_ID, "ok": RELEASE_ID}

    # 次の実行では、失敗した ng だけを dispatch する
    with pook.api.context():
        mock_feed("m/repo", RELEASE_XML)
        ng = mock_dispatch("t/ng")
        ok_again = pook.post("https://api.github.com/repos/t/ok/dispatches")

        result = main(entries, state)

        assert ng.calls == 1
        assert ok_again.calls == 0
        assert result["dispatched"] == ["ng"]
        assert state.records == {"ng": RELEASE_ID, "ok": RELEASE_ID}


def test_記録の読み込みに失敗しても残りは続けて最後にエラーにすること():
    state = FakeState({"ng": OLD_RELEASE_ID, "ok": OLD_RELEASE_ID})
    state.fail_get.add("ng")
    with pook.api.context():
        mock_feed("m/repo", RELEASE_XML)
        ng = pook.post("https://api.github.com/repos/t/ng/dispatches")
        ok = mock_dispatch("t/ok")

        with pytest.raises(FeedReleaseError, match=r"1 件の処理に失敗しました: ng: get failed"):
            main([entry("ng", "m/repo", "t/ng"), entry("ok", "m/repo", "t/ok")], state)

        assert ng.calls == 0
        assert ok.calls == 1


def test_記録が無いエントリーの記録に失敗したら最後にエラーにすること(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(handler, "get_github_token", _no_token)
    state = FakeState()
    state.fail_put.add("ng")
    with pook.api.context():
        mock_feed("m/repo", RELEASE_XML)

        with pytest.raises(FeedReleaseError, match=r"1 件の処理に失敗しました: ng: put failed"):
            main([entry("ng", "m/repo", "t/ng"), entry("ok", "m/repo", "t/ok")], state)

        assert state.records == {"ok": RELEASE_ID}


def test_dispatchしたあとに記録に失敗したら最後にエラーにすること():
    state = FakeState({"a": OLD_RELEASE_ID})
    state.fail_put.add("a")
    with pook.api.context():
        mock_feed("m/repo", RELEASE_XML)
        dispatch = mock_dispatch("t/repo")

        with pytest.raises(FeedReleaseError, match=r"a: dispatch したが記録できませんでした"):
            main([entry("a", "m/repo", "t/repo")], state)

        assert dispatch.calls == 1
        # 記録は古いままなので、次の実行でもう一度 dispatch される
        assert state.records == {"a": OLD_RELEASE_ID}


def test_lambda_functionは設定と記録を使って全エントリーを処理すること(
    monkeypatch: pytest.MonkeyPatch,
):
    loaded: list[tuple[str, str]] = []
    tables: list[str] = []
    state = FakeState({"a": OLD_RELEASE_ID})

    def _load_entries(bucket: str, key: str) -> list[Entry]:
        loaded.append((bucket, key))
        return [entry("a", "m/repo", "t/repo")]

    def _state(table_name: str) -> FakeState:
        tables.append(table_name)
        return state

    monkeypatch.setattr(handler, "load_entries", _load_entries)
    monkeypatch.setattr(handler, "DynamoDBDispatchState", _state)
    with pook.api.context():
        mock_feed("m/repo", RELEASE_XML)
        dispatch = mock_dispatch("t/repo")

        # EventBridge のスケジュールから来るイベント
        event: Any = {"source": "aws.events", "detail-type": "Scheduled Event", "detail": {}}
        result = lambda_function(event, None)

        assert loaded == [("test-bucket", "repositories.json")]
        assert tables == ["test-table"]
        assert dispatch.calls == 1
        assert result["dispatched"] == ["a"]
        assert state.records == {"a": RELEASE_ID}


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
    monkeypatch.setattr(handler, "load_entries", lambda _bucket, _key: [])
    monkeypatch.setattr(handler, "DynamoDBDispatchState", lambda _table: FakeState())

    result = lambda_function(event, None)

    assert result["dry_run"] is dry_run


@pytest.mark.parametrize("name", ["CONFIG_BUCKET", "CONFIG_KEY", "STATE_TABLE_NAME"])
def test_lambda_functionは環境変数が無いときは設定を読む前にエラーにすること(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
):
    def _load_entries(_bucket: str, _key: str) -> list[Entry]:
        msg = "設定を読みに行かない"
        raise AssertionError(msg)

    monkeypatch.setattr(handler, "load_entries", _load_entries)
    monkeypatch.setattr(handler, "DynamoDBDispatchState", lambda _table: FakeState())
    monkeypatch.delenv(name)

    with pytest.raises(KeyError, match=name):
        lambda_function({}, None)
