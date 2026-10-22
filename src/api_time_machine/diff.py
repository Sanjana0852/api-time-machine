"""Detect differences between two JSON documents.

The algorithm is described in section 6 of docs/comparison-engine-design.md.
"""

from api_time_machine.models import Change, ChangeKind, JsonType, JsonValue
from api_time_machine.rules import classify


def compare(old: JsonValue, new: JsonValue) -> list[Change]:
    """Return every difference between two parsed JSON documents.

    Pure and deterministic: the inputs are not modified, and the same inputs
    always produce the same changes in the same order.
    """
    changes: list[Change] = []
    _compare_at("$", old, new, changes)
    return changes


def json_type(value: JsonValue) -> JsonType:
    """Return the JSON type of a value produced by the `json` module.

    Raises TypeError for Python values that JSON cannot represent (tuples,
    sets, bytes, ...), so bad input fails loudly instead of being misclassified.
    """
    if value is None:
        return JsonType.NULL
    # bool must be checked before int: in Python, bool is a subclass of int,
    # so isinstance(True, int) is True.
    if isinstance(value, bool):
        return JsonType.BOOLEAN
    if isinstance(value, int):
        return JsonType.INTEGER
    if isinstance(value, float):
        return JsonType.FLOAT
    if isinstance(value, str):
        return JsonType.STRING
    if isinstance(value, list):
        return JsonType.ARRAY
    if isinstance(value, dict):
        return JsonType.OBJECT
    raise TypeError(f"Not a JSON value: {type(value).__name__}")


def _compare_at(path: str, old: JsonValue, new: JsonValue, changes: list[Change]) -> None:
    """Compare the values found at `path` in both documents, appending to `changes`."""
    # Check types first: comparing values of different types is meaningless,
    # and `True == 1` in Python would hide a boolean -> integer change.
    if json_type(old) != json_type(new):
        changes.append(_make_change(path, ChangeKind.TYPE_CHANGED, old, new))
    elif isinstance(old, dict) and isinstance(new, dict):
        _compare_objects(path, old, new, changes)
    elif old != new:
        changes.append(_make_change(path, ChangeKind.VALUE_CHANGED, old, new))


def _compare_objects(
    path: str, old: dict[str, JsonValue], new: dict[str, JsonValue], changes: list[Change]
) -> None:
    # Keys in old: either removed, or present in both and compared.
    for key, old_value in old.items():
        child_path = f"{path}.{key}"
        if key not in new:
            changes.append(_make_change(child_path, ChangeKind.FIELD_REMOVED, old_value, None))
        else:
            _compare_at(child_path, old_value, new[key], changes)

    # Keys only in new: added. Checked second so results follow old's key order.
    for key, new_value in new.items():
        if key not in old:
            changes.append(_make_change(f"{path}.{key}", ChangeKind.FIELD_ADDED, None, new_value))


def _make_change(
    path: str, kind: ChangeKind, old_value: JsonValue, new_value: JsonValue
) -> Change:
    return Change(path, kind, classify(kind, old_value, new_value), old_value, new_value)
