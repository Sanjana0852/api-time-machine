"""Severity policy: how likely each kind of change is to break API clients.

Rule numbers refer to section 5 of docs/comparison-engine-design.md.
Detection (diff.py) decides WHAT changed; this module decides HOW BAD it is.
"""

from typing import assert_never

from api_time_machine.models import ChangeKind, JsonValue, Severity


def classify(kind: ChangeKind, old_value: JsonValue, new_value: JsonValue) -> Severity:
    """Return the severity of one change.

    old_value and new_value are not used yet; the null and number rules
    (R4-R7) will need them.
    """
    match kind:
        case ChangeKind.FIELD_REMOVED:
            return Severity.BREAKING  # R1
        case ChangeKind.FIELD_ADDED:
            return Severity.SAFE  # R2
        case ChangeKind.TYPE_CHANGED:
            return Severity.BREAKING  # R3
        case ChangeKind.VALUE_CHANGED:
            return Severity.INFO  # R8
        case ChangeKind.ITEM_ADDED | ChangeKind.ITEM_REMOVED:
            return Severity.INFO  # R9
        case _:
            # Unreachable while every ChangeKind has a case above. If a new kind
            # is added without a rule, type checkers flag this line, and at
            # runtime it raises instead of silently returning None.
            assert_never(kind)
