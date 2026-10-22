"""Tests for replay(): fetch two URLs and compare bodies and status codes.

Most tests run against the real mock API through httpx.ASGITransport, which
calls the FastAPI app in memory: realistic, but no server and no network.
"""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from api_time_machine.diff import compare
from api_time_machine.fetch import BlockedURLError
from api_time_machine.mock_api import app as mock_app
from api_time_machine.models import Severity
from api_time_machine.replay import ReplayResult, replay

ALLOWED = frozenset({"localhost"})
EXAMPLES = Path(__file__).parent.parent / "examples"


def run_replay(
    old_url: str, new_url: str, transport: httpx.AsyncBaseTransport | None = None
) -> ReplayResult:
    async def run() -> ReplayResult:
        async with httpx.AsyncClient(
            transport=transport or httpx.ASGITransport(app=mock_app)
        ) as client:
            return await replay(client, old_url, new_url, ALLOWED)

    return asyncio.run(run())


def test_replay_v1_against_v2_matches_comparing_the_example_files() -> None:
    result = run_replay(
        "http://localhost/v1/products/101", "http://localhost/v2/products/101"
    )

    old_file = json.loads((EXAMPLES / "product_v1.json").read_text(encoding="utf-8"))
    new_file = json.loads((EXAMPLES / "product_v2.json").read_text(encoding="utf-8"))
    assert (result.old.status_code, result.new.status_code) == (200, 200)
    assert result.status_severity is None
    assert result.changes == compare(old_file, new_file)
    assert result.has_breaking


def test_replaying_the_same_url_finds_no_changes() -> None:
    url = "http://localhost/v1/products/102"

    result = run_replay(url, url)

    assert result.changes == []
    assert result.status_severity is None
    assert not result.has_breaking


def test_endpoint_that_stops_working_is_breaking() -> None:
    # 200 -> 404 (R11), even though the body comparison alone isn't breaking.
    result = run_replay(
        "http://localhost/v1/products/101", "http://localhost/v1/products/999"
    )

    assert (result.old.status_code, result.new.status_code) == (200, 404)
    assert result.status_severity is Severity.BREAKING
    assert result.has_breaking


def test_only_info_changes_are_not_breaking() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        stock = 12 if request.url.path == "/old" else 9
        return httpx.Response(200, json={"stock": stock})

    result = run_replay(
        "http://localhost/old", "http://localhost/new", httpx.MockTransport(handler)
    )

    assert [change.severity for change in result.changes] == [Severity.INFO]
    assert not result.has_breaking


def test_blocked_url_is_refused() -> None:
    with pytest.raises(BlockedURLError):
        run_replay("http://localhost/v1/products/101", "https://example.com/")


def test_both_urls_are_fetched_at_the_same_time() -> None:
    # Each request waits until both have started. Fetching one after the other
    # would make the first request wait forever (here: fail after 1 second).
    started = 0
    both_started = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal started
        started += 1
        if started == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=1)
        return httpx.Response(200, json={})

    result = run_replay(
        "http://localhost/old", "http://localhost/new", httpx.MockTransport(handler)
    )

    assert started == 2
    assert result.changes == []
