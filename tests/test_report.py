"""Tests for the text report."""

import pytest

from api_time_machine.models import Change, ChangeKind, Severity
from api_time_machine.report import describe, format_report

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
