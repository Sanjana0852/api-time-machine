"""Tests for the comparison engine's data model."""

import dataclasses

import pytest

from api_time_machine.models import Change, ChangeKind, Severity


def make_change() -> Change:
    return Change(
        path="$.price",
        kind=ChangeKind.TYPE_CHANGED,
        severity=Severity.BREAKING,
        old_value=250,
        new_value="250",
    )


def test_change_is_immutable() -> None:
    change = make_change()

    with pytest.raises(dataclasses.FrozenInstanceError):
        change.severity = Severity.SAFE  # type: ignore[misc]


def test_changes_with_same_fields_are_equal() -> None:
    assert make_change() == make_change()


def test_enums_compare_equal_to_their_string_values() -> None:
    # Matters later: enums are stored in the database and sent as JSON as plain strings.
    assert Severity.BREAKING == "breaking"
    assert ChangeKind.FIELD_REMOVED == "field_removed"
