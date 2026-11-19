# ruff: noqa: D100
# ruff: noqa: D103
# ruff: noqa: S101
# ruff: noqa: PLC2401, N802
import io
import json
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from botocore.exceptions import NoCredentialsError
from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber

from feed_release_cli.main import ConfigStore, main

BUCKET = "test-bucket"
KEY = "repositories.json"
ETAG = '"etag-1"'

RUFF = {
    "name": "ruff",
    "monitored_owner": "astral-sh",
    "monitored_repo": "ruff",
    "target_owner": "zaki3mymy",
    "target_repo": "RuffMate",
    "event_type": "ruff-release",
}
OTEL = {
    "name": "otel-lambda-anime-schedules",
    "monitored_owner": "open-telemetry",
    "monitored_repo": "opentelemetry-lambda",
    "target_owner": "zaki3mymy",
    "target_repo": "anime-schedules",
    "event_type": "otel-lambda-release",
}


@pytest.fixture
def s3() -> Iterator[tuple[ConfigStore, Stubber]]:
    client = boto3.client(
        "s3",
        region_name="ap-northeast-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",  # noqa: S106
    )
    with Stubber(client) as stubber:
        yield ConfigStore(client, BUCKET, KEY), stubber
        stubber.assert_no_pending_responses()


def _body(data: bytes) -> StreamingBody:
    return StreamingBody(io.BytesIO(data), len(data))


def expect_get(stubber: Stubber, entries: list[dict[str, str]]) -> None:
    data = json.dumps(entries).encode("utf-8")
    stubber.add_response(
        "get_object",
        {"Body": _body(data), "ETag": ETAG},
        {"Bucket": BUCKET, "Key": KEY},
    )


def expect_get_raw(stubber: Stubber, data: bytes) -> None:
    stubber.add_response(
        "get_object",
        {"Body": _body(data), "ETag": ETAG},
        {"Bucket": BUCKET, "Key": KEY},
    )


def expect_no_such_key(stubber: Stubber) -> None:
    stubber.add_client_error(
        "get_object",
        service_error_code="NoSuchKey",
        http_status_code=404,
        expected_params={"Bucket": BUCKET, "Key": KEY},
    )


def expect_put(stubber: Stubber, condition: dict[str, str]) -> None:
    stubber.add_response(
        "put_object",
        {"ETag": '"etag-2"'},
        {
            "Bucket": BUCKET,
            "Key": KEY,
            "Body": ANY,
            "ContentType": "application/json",
            **condition,
        },
    )


def run(argv: list[str], store: ConfigStore) -> int:
    return main(argv, store)


class _Capture:
    """put_object の Body を記録する(Stubber は Body を ANY で受けるので、中身はここで見る)"""

    def __init__(self, store: ConfigStore) -> None:
        self.bodies: list[bytes] = []
        store.s3.meta.events.register("before-parameter-build.s3.PutObject", self._record)

    def _record(self, params: dict[str, Any], **_: object) -> None:
        self.bodies.append(params["Body"])

    def last(self) -> list[dict[str, str]]:
        return json.loads(self.bodies[-1])


# list


def test_listで設定を一覧すること(
    s3: tuple[ConfigStore, Stubber],
    capsys: pytest.CaptureFixture[str],
) -> None:
    store, stubber = s3
    expect_get(stubber, [RUFF, OTEL])

    assert run(["list"], store) == 0

    out = capsys.readouterr().out
    assert "ruff  astral-sh/ruff -> zaki3mymy/RuffMate  (ruff-release)" in out
    assert "otel-lambda-anime-schedules  open-telemetry/opentelemetry-lambda" in out


def test_listで設定が無いときはその旨を表示すること(
    s3: tuple[ConfigStore, Stubber],
    capsys: pytest.CaptureFixture[str],
) -> None:
    store, stubber = s3
    expect_no_such_key(stubber)

    assert run(["list"], store) == 0

    assert "登録されていません" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"{", "JSON が壊れています"),
        (b"{}", "配列にしてください"),
        (b"[1]", "1 件目がオブジェクトではありません"),
        (b'[{"name": "a"}]', "monitored_owner"),
        (json.dumps([RUFF, RUFF]).encode(), "name が重複しています: ruff"),
    ],
)
def test_listで設定が壊れているときはエラーになること(
    s3: tuple[ConfigStore, Stubber],
    capsys: pytest.CaptureFixture[str],
    data: bytes,
    message: str,
) -> None:
    store, stubber = s3
    expect_get_raw(stubber, data)

    assert run(["list"], store) == 1

    assert message in capsys.readouterr().err


# add


def test_addでETagを条件にエントリーを足すこと(
    s3: tuple[ConfigStore, Stubber],
    capsys: pytest.CaptureFixture[str],
) -> None:
    store, stubber = s3
    capture = _Capture(store)
    expect_get(stubber, [RUFF])
    expect_put(stubber, {"IfMatch": ETAG})

    argv = [
        "add",
        "otel-lambda-anime-schedules",
        "--monitor",
        "open-telemetry/opentelemetry-lambda",
        "--target",
        "zaki3mymy/anime-schedules",
        "--event",
        "otel-lambda-release",
    ]
    assert run(argv, store) == 0

    assert capture.last() == [RUFF, OTEL]
    assert "追加しました" in capsys.readouterr().out


def test_addで設定が無いときはまだ無いときだけ作ること(s3: tuple[ConfigStore, Stubber]) -> None:
    store, stubber = s3
    capture = _Capture(store)
    expect_no_such_key(stubber)
    expect_put(stubber, {"IfNoneMatch": "*"})

    argv = ["add", "ruff", "--monitor", "astral-sh/ruff", "--target", "zaki3mymy/RuffMate"]
    assert run([*argv, "--event", "ruff-release"], store) == 0

    assert capture.last() == [RUFF]


def test_addで名前が重複するときはエラーになること(
    s3: tuple[ConfigStore, Stubber],
    capsys: pytest.CaptureFixture[str],
) -> None:
    store, stubber = s3
    expect_get(stubber, [RUFF])

    argv = ["add", "ruff", "--monitor", "a/b", "--target", "c/d", "--event", "e"]
    assert run(argv, store) == 1

    assert "既に登録されています" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["add", "bad name", "--monitor", "a/b", "--target", "c/d", "--event", "e"], "名前は"),
        (["add", "n", "--monitor", "a", "--target", "c/d", "--event", "e"], "--monitor"),
        (["add", "n", "--monitor", "a/b", "--target", "c/d/e", "--event", "e"], "--target"),
        (["add", "n", "--monitor", "a/b", "--target", "c/d", "--event", " "], "--event"),
        (["add", "n", "--monitor", "a/b", "--target", "c/d", "--event", "x" * 101], "--event"),
    ],
)
def test_addで引数が正しくないときはS3に触らずエラーになること(
    s3: tuple[ConfigStore, Stubber],
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    message: str,
) -> None:
    store, _ = s3

    assert run(argv, store) == 1

    assert message in capsys.readouterr().err


@pytest.mark.parametrize("code", ["PreconditionFailed", "ConditionalRequestConflict"])
def test_addで読んだあとに書き換えられていたらエラーになること(
    s3: tuple[ConfigStore, Stubber],
    capsys: pytest.CaptureFixture[str],
    code: str,
) -> None:
    store, stubber = s3
    expect_get(stubber, [])
    stubber.add_client_error("put_object", service_error_code=code, http_status_code=412)

    argv = ["add", "ruff", "--monitor", "astral-sh/ruff", "--target", "zaki3mymy/RuffMate"]
    assert run([*argv, "--event", "ruff-release"], store) == 1

    assert "もう一度実行してください" in capsys.readouterr().err


# remove


def test_removeでETagを条件にエントリーを消すこと(
    s3: tuple[ConfigStore, Stubber],
    capsys: pytest.CaptureFixture[str],
) -> None:
    store, stubber = s3
    capture = _Capture(store)
    expect_get(stubber, [RUFF, OTEL])
    expect_put(stubber, {"IfMatch": ETAG})

    assert run(["remove", "ruff"], store) == 0

    assert capture.last() == [OTEL]
    assert "削除しました: ruff" in capsys.readouterr().out


def test_removeで登録されていない名前はエラーになること(
    s3: tuple[ConfigStore, Stubber],
    capsys: pytest.CaptureFixture[str],
) -> None:
    store, stubber = s3
    expect_get(stubber, [RUFF])

    assert run(["remove", "nothing"], store) == 1

    assert "登録されていません" in capsys.readouterr().err


# AWS のエラー


def test_AWSのエラーはコードとメッセージを表示すること(
    s3: tuple[ConfigStore, Stubber],
    capsys: pytest.CaptureFixture[str],
) -> None:
    store, stubber = s3
    stubber.add_client_error(
        "get_object",
        service_error_code="AccessDenied",
        service_message="denied",
    )

    assert run(["list"], store) == 1

    assert "AWS のエラー: AccessDenied: denied" in capsys.readouterr().err


def test_書き込みのAWSのエラーはそのまま表示すること(
    s3: tuple[ConfigStore, Stubber],
    capsys: pytest.CaptureFixture[str],
) -> None:
    store, stubber = s3
    expect_get(stubber, [RUFF])
    stubber.add_client_error("put_object", service_error_code="AccessDenied")

    assert run(["remove", "ruff"], store) == 1

    assert "AWS のエラー: AccessDenied" in capsys.readouterr().err


def test_認証情報が無いときは確認を促すこと(
    s3: tuple[ConfigStore, Stubber],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, _ = s3

    def _raise() -> None:
        raise NoCredentialsError

    monkeypatch.setattr(store, "load", _raise)

    assert run(["list"], store) == 1

    assert "認証情報や --profile を確認してください" in capsys.readouterr().err
