# ruff: noqa: D100
# ruff: noqa: ANN201
# ruff: noqa: D103
# ruff: noqa: S101
# ruff: noqa: PLC2401, N802
import io
import json
from collections.abc import Iterator

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.response import StreamingBody
from botocore.stub import Stubber

from feed_release import handler
from feed_release.handler import (
    ConfigError,
    Entry,
    MonitoredRepo,
    TargetRepo,
    load_entries,
    parse_entries,
)

BUCKET = "test-bucket"
KEY = "repositories.json"
LOCATION = f"s3://{BUCKET}/{KEY}"

RUFF = {
    "name": "ruff",
    "monitored_owner": "astral-sh",
    "monitored_repo": "ruff",
    "target_owner": "zaki3mymy",
    "target_repo": "RuffMate",
    "event_type": "ruff-release",
}
RUFF_ENTRY = Entry(
    "ruff",
    MonitoredRepo("astral-sh", "ruff"),
    TargetRepo("zaki3mymy", "RuffMate", "ruff-release"),
)


@pytest.fixture
def s3_stub(monkeypatch: pytest.MonkeyPatch) -> Iterator[Stubber]:
    monkeypatch.setenv("CONFIG_BUCKET", BUCKET)
    monkeypatch.setenv("CONFIG_KEY", KEY)
    client = boto3.client(
        "s3",
        region_name="ap-northeast-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",  # noqa: S106
    )
    monkeypatch.setattr(handler.boto3, "client", lambda _: client)
    with Stubber(client) as stubber:
        yield stubber
        stubber.assert_no_pending_responses()


def test_S3の設定を読むこと(s3_stub: Stubber):
    data = json.dumps([RUFF]).encode("utf-8")
    s3_stub.add_response(
        "get_object",
        {"Body": StreamingBody(io.BytesIO(data), len(data))},
        {"Bucket": BUCKET, "Key": KEY},
    )

    assert load_entries() == [RUFF_ENTRY]


def test_設定が無いときは分かるメッセージでエラーにすること(s3_stub: Stubber):
    s3_stub.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)

    with pytest.raises(ConfigError, match=f"設定 {LOCATION} がありません"):
        load_entries()


def test_S3のそのほかのエラーはそのまま投げること(s3_stub: Stubber):
    s3_stub.add_client_error("get_object", service_error_code="AccessDenied", http_status_code=403)

    with pytest.raises(ClientError):
        load_entries()


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"{", "JSON が壊れています"),
        (b"\xff", "JSON が壊れています"),
        (b"{}", "配列にしてください"),
        (b"[1]", "1 件目がオブジェクトではありません"),
        (b'[{"name": "a", "monitored_owner": ""}]', "monitored_owner, monitored_repo"),
        (json.dumps([RUFF, RUFF]).encode(), "name が重複しています: ruff"),
    ],
)
def test_設定が壊れているときは分かるメッセージでエラーにすること(body: bytes, message: str):
    with pytest.raises(ConfigError, match=message):
        parse_entries(body, LOCATION)


def test_空の設定は空のリストになること():
    assert parse_entries(b"[]", LOCATION) == []
