"""Tests for the text report."""

import pytest

from api_time_machine.fetch import FetchedResponse
from api_time_machine.models import Change, ChangeKind, Severity
from api_time_machine.replay import ReplayResult
from api_time_machine.report import describe, format_replay_report, format_report

PRICE_TYPE_CHANGE = Change("$.price", ChangeKind.TYPE_CHANGED, Severity.BREAKING, 250, "250")
SELLER_ID_REMOVED = Change("$.seller.id", ChangeKind.FIELD_REMOVED, Severity.BREAKING, 7, None)
DISCOUNT_ADDED = Change("$.discount", ChangeKind.FIELD_ADDED, Severity.SAFE, None, 10)
STOCK_CHANGED = Change("$.stock", ChangeKind.VALUE_CHANGED, Severity.INFO, 12, 9)


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (PRICE_TYPE_CHANGE, 'type changed: integer -> string  (250 -> "250")'),
        (SELLER_ID_REMOVED, "field removed"),
        (DISCOUNT_ADDED, "field added (integer)"),
        (STOCK_CHANGED, "value changed: 12 -> 9"),
        (
            Change("$.tags[2]", ChangeKind.ITEM_ADDED, Severity.INFO, None, "x"),
            "item added (string)",
        ),
        (
            Change("$.tags[1]", ChangeKind.ITEM_REMOVED, Severity.INFO, "b", None),
            "item removed",
        ),
        (
            Change("$.name", ChangeKind.TYPE_CHANGED, Severity.BREAKING, "Asha", None),
            'type changed: string -> null  ("Asha" -> null)',
        ),
    ],
)
def test_describe(change: Change, expected: str) -> None:
    assert describe(change) == expected


def test_strings_keep_their_quotes_so_type_changes_are_visible() -> None:
    # Without quotes this would read "250 -> 250" and look like nothing changed.
    assert '(250 -> "250")' in describe(PRICE_TYPE_CHANGE)


def test_long_values_are_truncated() -> None:
    change = Change("$.bio", ChangeKind.VALUE_CHANGED, Severity.INFO, "x" * 100, "short")

    text = describe(change)

    assert "..." in text
    assert len(text) < 100


def test_report_with_no_changes() -> None:
    assert format_report([]) == "No changes."


def test_full_report_is_aligned_and_ends_with_summary() -> None:
    changes = [PRICE_TYPE_CHANGE, SELLER_ID_REMOVED, DISCOUNT_ADDED, STOCK_CHANGED]

    assert format_report(changes) == (
        'BREAKING  $.price      type changed: integer -> string  (250 -> "250")\n'
        "BREAKING  $.seller.id  field removed\n"
        "SAFE      $.discount   field added (integer)\n"
        "INFO      $.stock      value changed: 12 -> 9\n"
        "\n"
        "4 changes: 2 breaking, 1 safe, 1 info"
    )


def test_summary_uses_singular_for_one_change() -> None:
    assert format_report([STOCK_CHANGED]).endswith("1 change: 0 breaking, 0 safe, 1 info")


# --- Replay report -----------------------------------------------------------------


def make_replay_result(
    old_status: int, new_status: int, status_severity: Severity | None, changes: list[Change]
) -> ReplayResult:
    return ReplayResult(
        old=FetchedResponse("http://localhost/v1/p", old_status, {}),
        new=FetchedResponse("http://localhost/v2/p", new_status, {}),
        status_severity=status_severity,
        changes=changes,
    )


def test_replay_report_shows_both_requests_then_the_changes() -> None:
    result = make_replay_result(200, 200, None, [STOCK_CHANGED])

    assert format_replay_report(result) == (
        "Old: HTTP 200  http://localhost/v1/p\n"
        "New: HTTP 200  http://localhost/v2/p\n"
        "\n"
        "INFO      $.stock  value changed: 12 -> 9\n"
        "\n"
        "1 change: 0 breaking, 0 safe, 1 info"
    )


def test_replay_report_shows_status_change_with_its_severity() -> None:
    result = make_replay_result(200, 404, Severity.BREAKING, [])

    assert format_replay_report(result) == (
        "Old: HTTP 200  http://localhost/v1/p\n"
        "New: HTTP 404  http://localhost/v2/p\n"
        "BREAKING  status code changed: 200 -> 404\n"
        "\n"
        "No changes."
    )
