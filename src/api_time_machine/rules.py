"""Severity policy: how likely each kind of change is to break API clients.

Rules R1-R9 are in section 5 of docs/comparison-engine-design.md; R10-R12
(status codes) are in section 5 of docs/api-replay-design.md.
Detection (diff.py) decides WHAT changed; this module decides HOW BAD it is.
"""

from typing import assert_never

from api_time_machine.models import ChangeKind, JsonType, JsonValue, Severity, json_type


def classify(kind: ChangeKind, old_value: JsonValue, new_value: JsonValue) -> Severity:
    """Return the severity of one change."""
    match kind:
        case ChangeKind.FIELD_REMOVED:
            return Severity.BREAKING  # R1
        case ChangeKind.FIELD_ADDED:
            return Severity.SAFE  # R2
        case ChangeKind.TYPE_CHANGED:
            return _classify_type_change(json_type(old_value), json_type(new_value))
        case ChangeKind.VALUE_CHANGED:
            return Severity.INFO  # R8
        case ChangeKind.ITEM_ADDED | ChangeKind.ITEM_REMOVED:
            return Severity.INFO  # R9
        case _:
            # Unreachable while every ChangeKind has a case above. If a new kind
            # is added without a rule, type checkers flag this line, and at
            # runtime it raises instead of silently returning None.
            assert_never(kind)


def classify_status_change(old_status: int, new_status: int) -> Severity | None:
    """Return the severity of an HTTP status code change, or None if it didn't change."""
    if old_status == new_status:
        return None  # R10
    if _is_success(old_status) and not _is_success(new_status):
        return Severity.BREAKING  # R11: the endpoint used to work and now doesn't
    return Severity.INFO  # R12


def _is_success(status: int) -> bool:
    return 200 <= status < 300


def _classify_type_change(old_type: JsonType, new_type: JsonType) -> Severity:
    # Special cases first; R3 is the fallback for every other type change.
    if new_type is JsonType.NULL:
        return Severity.BREAKING  # R4
    if old_type is JsonType.NULL:
        return Severity.SAFE  # R5
    if old_type is JsonType.INTEGER and new_type is JsonType.FLOAT:
        return Severity.BREAKING  # R6
    if old_type is JsonType.FLOAT and new_type is JsonType.INTEGER:
        return Severity.SAFE  # R7
    return Severity.BREAKING  # R3
