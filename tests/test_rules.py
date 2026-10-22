"""Tests for classify(): the severity policy (design doc, section 5)."""

import pytest

from api_time_machine.models import ChangeKind, JsonValue, Severity
from api_time_machine.rules import classify


@pytest.mark.parametrize(
    ("kind", "old_value", "new_value", "expected"),
    [
        # R1: removing a field breaks clients that read it.
        (ChangeKind.FIELD_REMOVED, 1, None, Severity.BREAKING),
        # R2: well-behaved clients ignore fields they don't know.
        (ChangeKind.FIELD_ADDED, None, 1, Severity.SAFE),
        # R3: code written for the old type fails on the new one.
        (ChangeKind.TYPE_CHANGED, 250, "250", Severity.BREAKING),
        (ChangeKind.TYPE_CHANGED, {"a": 1}, [1], Severity.BREAKING),
        # R8: same type, different value is a data change, not a structural one.
        (ChangeKind.VALUE_CHANGED, 12, 9, Severity.INFO),
        # R9: list length is data.
        (ChangeKind.ITEM_ADDED, None, 1, Severity.INFO),
        (ChangeKind.ITEM_REMOVED, 1, None, Severity.INFO),
    ],
)
def test_classify(
    kind: ChangeKind, old_value: JsonValue, new_value: JsonValue, expected: Severity
) -> None:
    assert classify(kind, old_value, new_value) is expected
