# ruff: noqa: D100
# ruff: noqa: ANN201
# ruff: noqa: D103
# ruff: noqa: S101
# ruff: noqa: PLC2401, N802
from collections.abc import Iterator

import boto3
import pytest
from botocore.stub import ANY, Stubber

from feed_release import handler
from feed_release.handler import DynamoDBDispatchState

TABLE = "test-table"


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[DynamoDBDispatchState, Stubber]]:
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
    client = boto3.client("dynamodb")
    monkeypatch.setattr(handler.boto3, "client", lambda _: client)
    state = DynamoDBDispatchState(TABLE)
    with Stubber(client) as stubber:
        yield state, stubber
        stubber.assert_no_pending_responses()


def test_記録があればリリースのIDを返すこと(stub: tuple[DynamoDBDispatchState, Stubber]):
    state, stubber = stub
    stubber.add_response(
        "get_item",
        {"Item": {"name": {"S": "a"}, "release_id": {"S": "release-1"}}},
        {"TableName": TABLE, "Key": {"name": {"S": "a"}}, "ConsistentRead": True},
    )

    assert state.get("a") == "release-1"


def test_記録が無ければNoneを返すこと(stub: tuple[DynamoDBDispatchState, Stubber]):
    state, stubber = stub
    stubber.add_response(
        "get_item",
        {},
        {"TableName": TABLE, "Key": {"name": {"S": "a"}}, "ConsistentRead": True},
    )

    assert state.get("a") is None


def test_リリースのIDと書き換えた時刻を記録すること(stub: tuple[DynamoDBDispatchState, Stubber]):
    state, stubber = stub
    stubber.add_response(
        "put_item",
        {},
        {
            "TableName": TABLE,
            "Item": {"name": {"S": "a"}, "release_id": {"S": "release-1"}, "updated_at": ANY},
        },
    )

    state.put("a", "release-1")
