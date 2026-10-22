"""Tests for json_type(): naming the JSON type of a parsed value."""

import json

import pytest

from api_time_machine.diff import json_type
from api_time_machine.models import JsonType, JsonValue


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"a": 1}, JsonType.OBJECT),
        ({}, JsonType.OBJECT),
        ([1, 2], JsonType.ARRAY),
        ([], JsonType.ARRAY),
        ("250", JsonType.STRING),
        ("", JsonType.STRING),
        (250, JsonType.INTEGER),
        (0, JsonType.INTEGER),
        (-3, JsonType.INTEGER),
        (2.5, JsonType.FLOAT),
        (250.0, JsonType.FLOAT),
        (True, JsonType.BOOLEAN),
        (False, JsonType.BOOLEAN),
        (None, JsonType.NULL),
    ],
)
def test_json_type(value: JsonValue, expected: JsonType) -> None:
    assert json_type(value) is expected


def test_bool_is_not_mistaken_for_integer() -> None:
    # The Python quirk this guards against: bool is a subclass of int.
    assert isinstance(True, int)
    assert json_type(True) is JsonType.BOOLEAN
    assert json_type(False) is JsonType.BOOLEAN


def test_types_of_values_from_real_json_parser() -> None:
    doc = json.loads(
        '{"obj": {}, "arr": [], "str": "250", "int": 250,'
        ' "float": 250.0, "bool": true, "null": null}'
    )

    assert {key: json_type(value) for key, value in doc.items()} == {
        "obj": JsonType.OBJECT,
        "arr": JsonType.ARRAY,
        "str": JsonType.STRING,
        "int": JsonType.INTEGER,
        "float": JsonType.FLOAT,
        "bool": JsonType.BOOLEAN,
        "null": JsonType.NULL,
    }


@pytest.mark.parametrize("value", [(1, 2), {1, 2}, b"bytes", object()])
def test_non_json_value_raises_type_error(value: object) -> None:
    with pytest.raises(TypeError, match="Not a JSON value"):
        json_type(value)  # type: ignore[arg-type]
