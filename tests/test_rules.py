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
        (ChangeKind.TYPE_CHANGED, True, 1, Severity.BREAKING),
        (ChangeKind.TYPE_CHANGED, 1, True, Severity.BREAKING),
        # R4: clients that don't null-check crash on the new null.
        (ChangeKind.TYPE_CHANGED, 250, None, Severity.BREAKING),
        (ChangeKind.TYPE_CHANGED, "Asha", None, Severity.BREAKING),
        (ChangeKind.TYPE_CHANGED, {"id": 7}, None, Severity.BREAKING),
        # R5: clients already had to handle the old null.
        (ChangeKind.TYPE_CHANGED, None, 10, Severity.SAFE),
        (ChangeKind.TYPE_CHANGED, None, "Asha", Severity.SAFE),
        (ChangeKind.TYPE_CHANGED, None, {"id": 7}, Severity.SAFE),
        # R6: an int field in a typed client can't hold 250.5.
        (ChangeKind.TYPE_CHANGED, 250, 250.5, Severity.BREAKING),
        (ChangeKind.TYPE_CHANGED, 250, 250.0, Severity.BREAKING),
        # R7: every integer is a valid float.
        (ChangeKind.TYPE_CHANGED, 4.5, 4, Severity.SAFE),
        (ChangeKind.TYPE_CHANGED, 250.0, 250, Severity.SAFE),
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
