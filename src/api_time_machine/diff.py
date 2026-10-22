"""Detect differences between two JSON documents."""

from api_time_machine.models import JsonType, JsonValue


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
