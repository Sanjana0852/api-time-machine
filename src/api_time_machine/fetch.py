"""Safe HTTP fetching: the security boundary for every outgoing request.

Every request the tool makes goes through fetch_json(), which enforces the
safety rules S1-S6 from section 4 of docs/api-replay-design.md.
"""

from dataclasses import dataclass

import httpx

from api_time_machine.jsonparse import parse_json
from api_time_machine.models import JsonValue

TIMEOUT_SECONDS = 10.0  # S5
MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # S6: 5 MB
_ALLOWED_SCHEMES = frozenset({"http", "https"})  # S2


class FetchError(Exception):
    """The request failed, the server misbehaved, or the response isn't JSON."""


class BlockedURLError(FetchError):
    """A safety rule refused the URL before any request was sent."""


@dataclass(frozen=True)
class FetchedResponse:
    url: str
    status_code: int
    body: JsonValue


async def fetch_json(
    client: httpx.AsyncClient, url: str, allowed_hosts: frozenset[str]
) -> FetchedResponse:
    """GET `url` and parse its JSON body, enforcing the safety rules.

    Raises BlockedURLError if a rule refuses the URL, and FetchError for
    network failures, oversized responses and bodies that aren't JSON. Non-2xx
    responses with JSON bodies are returned normally.
    """
    check_url_allowed(url, allowed_hosts)
    try:
        # S3: the method is fixed to GET. S4: redirects are never followed.
        # stream() opens the response without downloading the body yet (S6).
        async with client.stream(
            "GET", url, follow_redirects=False, timeout=TIMEOUT_SECONDS
        ) as response:
            data = await _read_limited(response, url)
    except httpx.TimeoutException:
        raise FetchError(f"{url}: no response within {TIMEOUT_SECONDS:g} seconds") from None
    except httpx.ConnectError:
        raise FetchError(f"{url}: could not connect (is the server running?)") from None
    except httpx.HTTPError as error:
        raise FetchError(f"{url}: request failed ({error})") from None

    if response.is_redirect:
        location = response.headers.get("Location", "?")
        raise FetchError(
            f"{url}: HTTP {response.status_code} redirect to {location} was not followed"
        )
    try:
        body = parse_json(data)
    except ValueError:
        raise FetchError(f"{url}: HTTP {response.status_code} response is not valid JSON") from None
    return FetchedResponse(url=url, status_code=response.status_code, body=body)


def check_url_allowed(url: str, allowed_hosts: frozenset[str]) -> None:
    """Raise BlockedURLError unless `url` is http(s) and its host is allowed (S1, S2).

    The URL is parsed with httpx's own parser, the same one that sends the
    request, so the check and the request can never disagree about the host.
    """
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL as error:
        raise BlockedURLError(f"{url!r} is not a valid URL ({error})") from None
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise BlockedURLError(f"{url!r}: only http and https URLs are allowed")
    # .host excludes any "user@" prefix, so http://localhost@evil.example
    # is checked as evil.example.
    host = parsed.host.lower()
    if host not in allowed_hosts:
        allowed = ", ".join(sorted(allowed_hosts)) or "(none)"
        raise BlockedURLError(
            f"{url}: host {host!r} is not in the allowed hosts ({allowed}). "
            "Add it to the ATM_ALLOWED_HOSTS environment variable, but only if you "
            "have permission to send requests to it."
        )


async def _read_limited(response: httpx.Response, url: str) -> bytes:
    # Read chunk by chunk and stop as soon as the limit is passed, so an
    # oversized (or endless) response is never held in memory.
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        size += len(chunk)
        if size > MAX_RESPONSE_BYTES:
            raise FetchError(f"{url}: response is larger than {MAX_RESPONSE_BYTES:,} bytes")
        chunks.append(chunk)
    return b"".join(chunks)
