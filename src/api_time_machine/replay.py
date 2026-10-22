"""Replay: fetch an old and a new URL and compare the responses.

See section 5 of docs/api-replay-design.md.
"""

import asyncio
from dataclasses import dataclass

import httpx

from api_time_machine.diff import compare
from api_time_machine.fetch import FetchedResponse, fetch_json
from api_time_machine.models import Change, Severity
from api_time_machine.rules import classify_status_change


@dataclass(frozen=True)
class ReplayResult:
    old: FetchedResponse
    new: FetchedResponse
    status_severity: Severity | None  # None if the status codes are equal
    changes: list[Change]  # differences between the two bodies

    @property
    def has_breaking(self) -> bool:
        """True if the status change or any body change would break clients."""
        return self.status_severity is Severity.BREAKING or any(
            change.severity is Severity.BREAKING for change in self.changes
        )


async def replay(
    client: httpx.AsyncClient, old_url: str, new_url: str, allowed_hosts: frozenset[str]
) -> ReplayResult:
    """Fetch both URLs and compare them.

    The client is passed in (dependency injection), so tests can supply one
    with a fake transport. Raises FetchError (or BlockedURLError) if either
    request fails or is refused.
    """
    # gather() runs both requests at the same time, so a replay takes as long
    # as the slower server rather than the sum of both.
    old, new = await asyncio.gather(
        fetch_json(client, old_url, allowed_hosts),
        fetch_json(client, new_url, allowed_hosts),
    )
    return ReplayResult(
        old=old,
        new=new,
        status_severity=classify_status_change(old.status_code, new.status_code),
        changes=compare(old.body, new.body),
    )
