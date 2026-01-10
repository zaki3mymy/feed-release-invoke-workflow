# ruff: noqa: D100
# ruff: noqa: ANN201
# ruff: noqa: S101
# ruff: noqa: D103
# ruff: noqa: PLC2401, N802
from datetime import UTC, datetime, timedelta

import pytest
from freezegun import freeze_time

from feed_release.handler import Release, is_latest_release


@pytest.fixture(autouse=True)
def setup_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INTERVAL_SECOND", "60")


@freeze_time("2026-01-01 12:34:56")
def test_リリースされた():
    # prepare
    now = datetime(2026, 1, 1, 12, 34, 56, tzinfo=UTC) - timedelta(seconds=59)
    release = Release("test-id", now)

    # exec
    act = is_latest_release(release)

    # prepare
    assert act


@freeze_time("2026-01-01 12:34:56")
def test_リリースされて通知済み1():
    # prepare
    now = datetime(2026, 1, 1, 12, 34, 56, tzinfo=UTC) - timedelta(seconds=60)
    release = Release("test-id", now)

    # exec
    act = is_latest_release(release)

    # prepare
    assert not act


@freeze_time("2026-01-01 12:34:56")
def test_リリースされて通知済み2():
    # prepare
    now = datetime(2026, 1, 1, 12, 34, 56, tzinfo=UTC) - timedelta(seconds=61)
    release = Release("test-id", now)

    # exec
    act = is_latest_release(release)

    # prepare
    assert not act
