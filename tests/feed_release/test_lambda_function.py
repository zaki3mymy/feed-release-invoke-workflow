# ruff: noqa: D100
# ruff: noqa: ANN201
# ruff: noqa: D103
# ruff: noqa: S101
# ruff: noqa: E501
# ruff: noqa: N802, PLC2401
import pook
import pytest
from freezegun import freeze_time

from feed_release.handler import Event, lambda_function


@pytest.fixture(autouse=True)
def setup_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INTERVAL_SECOND", "60")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")


@freeze_time("2026-01-01T12:35:56+09:00")
def test_リリースなし():
    with pook.api.context():
        # prepare
        # fetchのモック
        monitored_owner = "m_owner"
        monitored_repo = "m_repo"
        fetch_url = f"https://github.com/{monitored_owner}/{monitored_repo}/releases.atom"
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/" xml:lang="en-US">
          <id>tag:github.com,2008:https://github.com/owner/repo/releases</id>
          <link type="text/html" rel="alternate" href="https://github.com/owner/repo/releases"/>
          <link type="application/atom+xml" rel="self" href="https://github.com/{monitored_owner}/{monitored_repo}/releases.atom"/>
          <title>Release notes from {monitored_repo}</title>
          <updated>2025-12-19T04:08:17+09:00</updated>
        </feed>
        """
        mock_fetch_release = pook.get(fetch_url).times(1).reply(200).xml(xml).mock

        # invokeのモック
        target_owner = "t_owner"
        target_repo = "t_repo"
        event_type = "test-event"
        invoke_url = f"https://api.github.com/repos/{target_owner}/{target_repo}/dispatches"
        mock_invoke = pook.post(invoke_url)

        event: Event = {
            "monitored_owner": monitored_owner,
            "monitored_repo": monitored_repo,
            "target_owner": target_owner,
            "target_repo": target_repo,
            "event_type": event_type,
        }

        # exec
        lambda_function(event, None)

        # verify
        assert mock_fetch_release.calls == 1
        assert mock_invoke.calls == 0


@freeze_time("2026-01-01T12:35:56+09:00")
def test_新しいリリースなし():
    with pook.api.context():
        # prepare
        # fetchのモック
        monitored_owner = "m_owner"
        monitored_repo = "m_repo"
        fetch_url = f"https://github.com/{monitored_owner}/{monitored_repo}/releases.atom"
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/" xml:lang="en-US">
          <id>tag:github.com,2008:https://github.com/owner/repo/releases</id>
          <link type="text/html" rel="alternate" href="https://github.com/owner/repo/releases"/>
          <link type="application/atom+xml" rel="self" href="https://github.com/{monitored_owner}/{monitored_repo}/releases.atom"/>
          <title>Release notes from {monitored_repo}</title>
          <updated>2025-12-19T04:08:17+09:00</updated>
          <entry>
            <id>test-id</id>
            <updated>2026-01-01T12:34:56+09:00</updated>
            <link rel="alternate" type="text/html" href="https://github.com/owner/repo/releases/tag/0.1.0"/>
            <title>0.1.0</title>
            <content type="html">&lt;h2&gt;Release Notes&lt;/h2&gt;</content>
            <author>
              <name>github-actions[bot]</name>
            </author>
          </entry>
        </feed>
        """
        mock_fetch_release = pook.get(fetch_url).times(1).reply(200).xml(xml).mock

        # invokeのモック
        target_owner = "t_owner"
        target_repo = "t_repo"
        event_type = "test-event"
        invoke_url = f"https://api.github.com/repos/{target_owner}/{target_repo}/dispatches"
        mock_invoke = pook.post(invoke_url)

        event: Event = {
            "monitored_owner": monitored_owner,
            "monitored_repo": monitored_repo,
            "target_owner": target_owner,
            "target_repo": target_repo,
            "event_type": event_type,
        }

        # exec
        lambda_function(event, None)

        # verify
        assert mock_fetch_release.calls == 1
        assert mock_invoke.calls == 0


@freeze_time("2026-01-01T12:34:57+09:00")
def test_新しいリリースがありワークフローの呼び出し成功():
    with pook.api.context():
        # prepare
        # fetchのモック
        monitored_owner = "m_owner"
        monitored_repo = "m_repo"
        fetch_url = f"https://github.com/{monitored_owner}/{monitored_repo}/releases.atom"
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/" xml:lang="en-US">
          <id>tag:github.com,2008:https://github.com/owner/repo/releases</id>
          <link type="text/html" rel="alternate" href="https://github.com/owner/repo/releases"/>
          <link type="application/atom+xml" rel="self" href="https://github.com/{monitored_owner}/{monitored_repo}/releases.atom"/>
          <title>Release notes from {monitored_repo}</title>
          <updated>2025-12-19T04:08:17+09:00</updated>
          <entry>
            <id>test-id</id>
            <updated>2026-01-01T12:34:56+09:00</updated>
            <link rel="alternate" type="text/html" href="https://github.com/owner/repo/releases/tag/0.1.0"/>
            <title>0.1.0</title>
            <content type="html">&lt;h2&gt;Release Notes&lt;/h2&gt;</content>
            <author>
              <name>github-actions[bot]</name>
            </author>
          </entry>
        </feed>
        """
        mock_fetch_release = pook.get(fetch_url).times(1).reply(200).xml(xml).mock

        # invokeのモック
        target_owner = "t_owner"
        target_repo = "t_repo"
        event_type = "test-event"
        token = "test-token"  # noqa: S105
        invoke_url = f"https://api.github.com/repos/{target_owner}/{target_repo}/dispatches"
        mock_invoke = (
            pook.post(invoke_url)
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
                    "client_payload": {},
                },
            )
            .times(1)
            .reply(200)
            .mock
        )

        event: Event = {
            "monitored_owner": monitored_owner,
            "monitored_repo": monitored_repo,
            "target_owner": target_owner,
            "target_repo": target_repo,
            "event_type": event_type,
        }

        # exec
        lambda_function(event, None)

        # verify
        assert mock_fetch_release.calls == 1
        assert mock_invoke.calls == 1
