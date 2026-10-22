"""Tests for the web API (section 7 of docs/api-replay-design.md).

/replay never touches the real network: the HTTP client dependency is
overridden with one that calls the mock API in memory (ASGITransport) or
uses a fake transport.
"""

import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from api_time_machine.api import app, get_allowed_hosts, get_http_client
from api_time_machine.mock_api import app as mock_app

EXAMPLES = Path(__file__).parent.parent / "examples"


def load_example(name: str) -> object:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def use_transport(transport: httpx.AsyncBaseTransport) -> None:
    """Make /replay send its requests through `transport` instead of the network."""

    async def client_for_tests() -> AsyncIterator[httpx.AsyncClient]:
        async with httpx.AsyncClient(transport=transport) as client:
            yield client

    app.dependency_overrides[get_http_client] = client_for_tests


@pytest.fixture
def client() -> Iterator[TestClient]:
    use_transport(httpx.ASGITransport(app=mock_app))
    app.dependency_overrides[get_allowed_hosts] = lambda: frozenset({"localhost"})
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- /health ------------------------------------------------------------------------------


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --- /compare -----------------------------------------------------------------------------


def test_compare_example_documents(client: TestClient) -> None:
    response = client.post(
        "/compare",
        json={"old": load_example("product_v1.json"), "new": load_example("product_v2.json")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "total": 9,
        "breaking": 4,
        "safe": 3,
        "info": 2,
        "has_breaking": True,
    }
    assert body["changes"][0] == {
        "path": "$.price",
        "kind": "type_changed",
        "severity": "breaking",
        "old_value": 250,
        "new_value": "250",
    }


def test_compare_identical_documents(client: TestClient) -> None:
    response = client.post("/compare", json={"old": {"a": 1}, "new": {"a": 1}})

    assert response.json() == {
        "changes": [],
        "summary": {"total": 0, "breaking": 0, "safe": 0, "info": 0, "has_breaking": False},
    }


def test_compare_keeps_bool_and_int_distinct(client: TestClient) -> None:
    # If request validation coerced true into 1, this type change would vanish.
    response = client.post("/compare", json={"old": {"active": True}, "new": {"active": 1}})

    assert response.json()["changes"][0]["kind"] == "type_changed"


def test_compare_keeps_int_and_float_distinct(client: TestClient) -> None:
    response = client.post(
        "/compare",
        content=b'{"old": {"price": 250}, "new": {"price": 250.0}}',
        headers={"Content-Type": "application/json"},
    )

    assert response.json()["changes"][0]["severity"] == "breaking"  # R6


def test_compare_accepts_null_documents(client: TestClient) -> None:
    response = client.post("/compare", json={"old": None, "new": {"a": 1}})

    assert response.status_code == 200
    assert response.json()["changes"][0]["severity"] == "safe"  # R5: null -> value


def test_compare_missing_field_is_rejected(client: TestClient) -> None:
    response = client.post("/compare", json={"old": {"a": 1}})

    assert response.status_code == 422


def test_compare_body_that_is_not_json_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/compare", content=b"not json", headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 422


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_compare_rejects_nan_and_infinity(client: TestClient, constant: str) -> None:
    # Same rule as files and fetched responses: not valid JSON, and NaN != NaN.
    response = client.post(
        "/compare",
        content=f'{{"old": {{"score": {constant}}}, "new": {{}}}}'.encode(),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert "NaN and Infinity are not allowed" in response.text


def test_validation_errors_do_not_echo_the_input(client: TestClient) -> None:
    secret_looking = {"token": "abc123", "big": list(range(1000))}

    response = client.post("/compare", json={"old": secret_looking})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "new"]
    assert "abc123" not in response.text


# --- /replay ------------------------------------------------------------------------------


def test_replay_against_mock_api(client: TestClient) -> None:
    response = client.post(
        "/replay",
        json={
            "old_url": "http://localhost/v1/products/101",
            "new_url": "http://localhost/v2/products/101",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["old"] == {"url": "http://localhost/v1/products/101", "status_code": 200}
    assert body["new"] == {"url": "http://localhost/v2/products/101", "status_code": 200}
    assert body["status_severity"] is None
    assert body["summary"]["total"] == 9
    assert body["summary"]["has_breaking"] is True


def test_replay_status_change_counts_as_breaking(client: TestClient) -> None:
    # 200 -> 404 is breaking even if no single body change were.
    response = client.post(
        "/replay",
        json={
            "old_url": "http://localhost/v1/products/101",
            "new_url": "http://localhost/v1/products/999",
        },
    )

    body = response.json()
    assert body["new"]["status_code"] == 404
    assert body["status_severity"] == "breaking"
    assert body["summary"]["has_breaking"] is True


def test_replay_blocked_host_is_bad_request(client: TestClient) -> None:
    response = client.post(
        "/replay",
        json={"old_url": "http://localhost/v1/products/101", "new_url": "http://169.254.169.254/"},
    )

    assert response.status_code == 400
    assert "not in the allowed hosts" in response.json()["detail"]


def test_replay_unreachable_server_is_bad_gateway(client: TestClient) -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    use_transport(httpx.MockTransport(refused))

    response = client.post(
        "/replay", json={"old_url": "http://localhost/a", "new_url": "http://localhost/b"}
    )

    assert response.status_code == 502
    assert "could not connect" in response.json()["detail"]


def test_replay_non_json_response_is_bad_gateway(client: TestClient) -> None:
    def html(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>hello</html>")

    use_transport(httpx.MockTransport(html))

    response = client.post(
        "/replay", json={"old_url": "http://localhost/a", "new_url": "http://localhost/b"}
    )

    assert response.status_code == 502
    assert "not valid JSON" in response.json()["detail"]


def test_replay_missing_url_is_rejected(client: TestClient) -> None:
    response = client.post("/replay", json={"old_url": "http://localhost/a"})

    assert response.status_code == 422


# --- Interactive docs -------------------------------------------------------------------------


def test_openapi_schema_is_generated(client: TestClient) -> None:
    # Recursive types like JsonValue can break schema generation; /docs depends on it.
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert {"/health", "/compare", "/replay"} <= set(response.json()["paths"])
