"""Data types shared by the comparison engine. Data only, no logic."""

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
