# ruff: noqa: D100
# ruff: noqa: ANN201
# ruff: noqa: D103
# ruff: noqa: S101
# ruff: noqa: PLC2401, N802
from collections.abc import Iterator

import boto3
import pytest
from botocore.stub import Stubber

from feed_release import handler
from feed_release.handler import get_github_token

PARAMETER_NAME = "/app/test/gh-token"


@pytest.fixture(autouse=True)
def setup_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("GITHUB_TOKEN_PARAMETER_NAME", PARAMETER_NAME)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
    get_github_token.cache_clear()
    yield
    get_github_token.cache_clear()


@pytest.fixture
def ssm_stub(monkeypatch: pytest.MonkeyPatch) -> Iterator[Stubber]:
    client = boto3.client("ssm")
    monkeypatch.setattr(handler.boto3, "client", lambda _: client)
    with Stubber(client) as stubber:
        yield stubber
        stubber.assert_no_pending_responses()


def _response(value: str) -> dict:
    return {"Parameter": {"Name": PARAMETER_NAME, "Type": "SecureString", "Value": value}}


def test_SSMのパラメータを復号して取得すること(ssm_stub: Stubber):
    ssm_stub.add_response(
        "get_parameter",
        _response("ssm-token"),
        {"Name": PARAMETER_NAME, "WithDecryption": True},
    )

    assert get_github_token() == "ssm-token"


def test_2回目以降はSSMに取りに行かないこと(ssm_stub: Stubber):
    # レスポンスは 1 回分だけ。2 回目に取りに行くと Stubber がエラーにする
    ssm_stub.add_response(
        "get_parameter",
        _response("ssm-token"),
        {"Name": PARAMETER_NAME, "WithDecryption": True},
    )

    assert get_github_token() == "ssm-token"
    assert get_github_token() == "ssm-token"


def test_パラメータが無いときはエラーとなること(ssm_stub: Stubber):
    ssm_stub.add_client_error("get_parameter", service_error_code="ParameterNotFound")

    with pytest.raises(handler.boto3.client("ssm").exceptions.ParameterNotFound):
        get_github_token()
