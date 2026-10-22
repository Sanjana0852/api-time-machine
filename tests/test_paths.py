"""Tests for key_path(): building the path to a key inside an object."""

import pytest

from api_time_machine.diff import key_path


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        # Simple identifier-like keys use dot notation.
        ("price", "$.price"),
        ("_id", "$._id"),
        ("item2", "$.item2"),
        ("firstName", "$.firstName"),
        # Anything else uses bracket notation with the key JSON-quoted.
        ("a.b", '$["a.b"]'),
        ("user-id", '$["user-id"]'),
        ("first name", '$["first name"]'),
        ("2fa", '$["2fa"]'),  # can't start with a digit
        ("", '$[""]'),
        ("$", '$["$"]'),
        ('say "hi"', r'$["say \"hi\""]'),  # quotes are escaped
        ("café", '$["café"]'),  # non-ASCII stays readable
    ],
)
def test_key_path(key: str, expected: str) -> None:
    assert key_path("$", key) == expected


def test_key_path_appends_to_parent_path() -> None:
    assert key_path("$.seller", "id") == "$.seller.id"
    assert key_path("$.seller", "user-id") == '$.seller["user-id"]'
