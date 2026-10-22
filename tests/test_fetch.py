"""Tests for fetch_json(): the safety rules for every outgoing request.

No real network: httpx.MockTransport answers requests with a Python function.
Rule numbers (S1-S6) refer to section 4 of docs/api-replay-design.md.
"""

import asyncio
from collections.abc import AsyncIterator, Callable

import httpx
import pytest

from api_time_machine.fetch import (
    MAX_RESPONSE_BYTES,
    BlockedURLError,
    FetchedResponse,
    FetchError,
    fetch_json,
)

ALLOWED = frozenset({"localhost", "127.0.0.1"})

Handler = Callable[[httpx.Request], httpx.Response]


def fetch(handler: Handler, url: str) -> FetchedResponse:
    """Run fetch_json against a fake server whose responses come from `handler`."""

    async def run() -> FetchedResponse:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_json(client, url, ALLOWED)

    return asyncio.run(run())


def json_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"id": 1, "price": 250})


def must_not_be_called(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"request should have been blocked: {request.url}")


# --- Successful requests --------------------------------------------------------------


def test_returns_status_and_parsed_body() -> None:
    result = fetch(json_handler, "http://localhost:8001/v1/products/1")

    assert result == FetchedResponse(
        url="http://localhost:8001/v1/products/1",
        status_code=200,
        body={"id": 1, "price": 250},
    )


def test_error_status_with_json_body_is_returned_not_raised() -> None:
    # A 404 is a valid answer to compare (replay decides its severity).
    def not_found(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Product 999 not found"})

    result = fetch(not_found, "http://localhost/v1/products/999")

    assert result.status_code == 404
    assert result.body == {"detail": "Product 999 not found"}


def test_only_get_requests_are_sent() -> None:
    # S3: replay must be read-only.
    methods: list[str] = []

    def record(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return json_handler(request)

    fetch(record, "http://localhost/")

    assert methods == ["GET"]


# --- S1: host allowlist ------------------------------------------------------------------


def test_host_not_in_allowlist_is_blocked_before_any_request() -> None:
    with pytest.raises(BlockedURLError, match="not in the allowed hosts"):
        fetch(must_not_be_called, "https://example.com/api")


def test_cloud_metadata_address_is_blocked() -> None:
    # The classic SSRF target: cloud servers expose credentials here.
    with pytest.raises(BlockedURLError):
        fetch(must_not_be_called, "http://169.254.169.254/latest/meta-data/")


def test_username_trick_does_not_bypass_allowlist() -> None:
    # "localhost" here is a username; the real host is evil.example.
    with pytest.raises(BlockedURLError, match="evil.example"):
        fetch(must_not_be_called, "http://localhost@evil.example/")


def test_host_matching_ignores_case_and_port() -> None:
    assert fetch(json_handler, "http://LOCALHOST:8001/x").status_code == 200


# --- S2: http and https only --------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    ["file:///C:/Windows/win.ini", "ftp://localhost/data.json", "localhost/no-scheme", ""],
)
def test_non_http_urls_are_blocked(url: str) -> None:
    with pytest.raises(BlockedURLError):
        fetch(must_not_be_called, url)


# --- S4: redirects are not followed --------------------------------------------------------


def test_redirect_is_reported_not_followed() -> None:
    calls: list[str] = []

    def redirect(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://evil.example/"})

    with pytest.raises(FetchError, match="redirect to http://evil.example/ was not followed"):
        fetch(redirect, "http://localhost/old")

    assert calls == ["http://localhost/old"]


# --- S5 and network failures ---------------------------------------------------------------


def test_timeout() -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(FetchError, match="no response within 10 seconds"):
        fetch(slow, "http://localhost/slow")


def test_connection_refused_suggests_checking_the_server() -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(FetchError, match="could not connect"):
        fetch(refused, "http://localhost:8001/v1/products/101")


# --- S6: response size limit ----------------------------------------------------------------


def test_response_over_size_limit_is_rejected() -> None:
    def huge(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b" " * (MAX_RESPONSE_BYTES + 1))

    with pytest.raises(FetchError, match="larger than"):
        fetch(huge, "http://localhost/huge")


def test_download_stops_as_soon_as_limit_is_passed() -> None:
    # An endless response must not be read to the end (it has no end).
    chunk = b" " * (1024 * 1024)
    chunks_sent = 0

    async def endless() -> AsyncIterator[bytes]:
        nonlocal chunks_sent
        while True:
            chunks_sent += 1
            yield chunk

    def stream_forever(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=endless())

    with pytest.raises(FetchError, match="larger than"):
        fetch(stream_forever, "http://localhost/endless")

    assert chunks_sent <= MAX_RESPONSE_BYTES // len(chunk) + 1


# --- Bodies that aren't JSON -------------------------------------------------------------------


def test_html_body_is_not_json() -> None:
    def html(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>Bad Gateway</html>")

    with pytest.raises(FetchError, match="HTTP 502 response is not valid JSON"):
        fetch(html, "http://localhost/")


def test_nan_in_body_is_rejected() -> None:
    def nan(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text='{"score": NaN}')

    with pytest.raises(FetchError, match="not valid JSON"):
        fetch(nan, "http://localhost/")


def test_blocked_url_error_is_a_fetch_error() -> None:
    # Callers that don't care why fetching failed can catch FetchError alone.
    assert issubclass(BlockedURLError, FetchError)
