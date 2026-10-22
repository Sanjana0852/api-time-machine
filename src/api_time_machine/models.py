"""The comparison engine's vocabulary: data types, plus json_type() to tell JSON types apart.

Every other module depends on this one, and it depends on none of them, so it
can never be part of a circular import.
"""

from dataclasses import dataclass
from enum import StrEnum

# Any value that can appear in a parsed JSON document. The alias refers to
# itself because objects and arrays can contain any JSON value, including more
# objects and arrays.
type JsonValue = dict[str, JsonValue] | list[JsonValue] | str | int | float | bool | None


class JsonType(StrEnum):
    """The type of a JSON value. Integer and float are separate (see design doc)."""

    OBJECT = "object"
    ARRAY = "array"
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    NULL = "null"


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


class ChangeKind(StrEnum):
    """What kind of difference was found at a path."""

    FIELD_ADDED = "field_added"  # object key only in new
    FIELD_REMOVED = "field_removed"  # object key only in old
    TYPE_CHANGED = "type_changed"  # same location, different JsonType
    VALUE_CHANGED = "value_changed"  # same location, same type, different value
    ITEM_ADDED = "item_added"  # array is longer in new
    ITEM_REMOVED = "item_removed"  # array is shorter in new


class Severity(StrEnum):
    """How likely a change is to break existing API clients."""

    BREAKING = "breaking"  # likely to break existing clients
    SAFE = "safe"  # structural change that well-behaved clients tolerate
    INFO = "info"  # data changed, structure did not


@dataclass(frozen=True)
class Change:
    """One difference between an old and a new JSON document.

    For FIELD_ADDED and ITEM_ADDED, old_value is None; for FIELD_REMOVED and
    ITEM_REMOVED, new_value is None. Use `kind` to tell these apart from a
    real JSON null.
    """

    path: str
    kind: ChangeKind
    severity: Severity
    old_value: JsonValue
    new_value: JsonValue
