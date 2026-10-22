"""Tests for compare(): finding the differences between two JSON documents."""

import copy

from api_time_machine.diff import compare
from api_time_machine.models import Change, ChangeKind, Severity


# --- No changes ---------------------------------------------------------------


def test_identical_documents_have_no_changes() -> None:
    doc = {"id": 1, "name": "Pen", "price": 250, "in_stock": True, "discount": None}

    assert compare(doc, copy.deepcopy(doc)) == []


def test_empty_objects_have_no_changes() -> None:
    assert compare({}, {}) == []


def test_key_order_does_not_matter() -> None:
    # JSON objects are unordered, so reordering keys is not a change.
    assert compare({"a": 1, "b": 2}, {"b": 2, "a": 1}) == []


# --- One change of each kind ---------------------------------------------------


def test_field_removed_is_breaking() -> None:
    assert compare({"id": 1, "seller_id": 7}, {"id": 1}) == [
        Change("$.seller_id", ChangeKind.FIELD_REMOVED, Severity.BREAKING, 7, None),
    ]


def test_field_added_is_safe() -> None:
    assert compare({"id": 1}, {"id": 1, "discount": 10}) == [
        Change("$.discount", ChangeKind.FIELD_ADDED, Severity.SAFE, None, 10),
    ]


def test_number_becoming_string_is_breaking() -> None:
    # The motivating example: still HTTP 200, but `price * qty` now breaks.
    assert compare({"price": 250}, {"price": "250"}) == [
        Change("$.price", ChangeKind.TYPE_CHANGED, Severity.BREAKING, 250, "250"),
    ]


def test_value_changed_is_info() -> None:
    assert compare({"stock": 12}, {"stock": 9}) == [
        Change("$.stock", ChangeKind.VALUE_CHANGED, Severity.INFO, 12, 9),
    ]


def test_bool_to_integer_is_a_type_change() -> None:
    # True == 1 in Python, so a plain `!=` check would miss this entirely.
    assert compare({"active": True}, {"active": 1}) == [
        Change("$.active", ChangeKind.TYPE_CHANGED, Severity.BREAKING, True, 1),
    ]


# --- Absent vs. null (design doc, decision 3) ----------------------------------


def test_null_field_removed_is_reported_as_removed() -> None:
    # The key existed (with value null) and now doesn't exist at all.
    assert compare({"discount": None}, {}) == [
        Change("$.discount", ChangeKind.FIELD_REMOVED, Severity.BREAKING, None, None),
    ]


def test_null_field_added_is_reported_as_added() -> None:
    assert compare({}, {"discount": None}) == [
        Change("$.discount", ChangeKind.FIELD_ADDED, Severity.SAFE, None, None),
    ]


# --- Several changes at once ---------------------------------------------------


def test_multiple_changes_follow_old_key_order_then_added_keys() -> None:
    old = {"id": 1, "price": 250, "seller_id": 7, "stock": 12}
    new = {"discount": 10, "id": 1, "price": "250", "stock": 9}

    changes = compare(old, new)

    assert [(c.path, c.kind) for c in changes] == [
        ("$.price", ChangeKind.TYPE_CHANGED),
        ("$.seller_id", ChangeKind.FIELD_REMOVED),
        ("$.stock", ChangeKind.VALUE_CHANGED),
        ("$.discount", ChangeKind.FIELD_ADDED),
    ]


def test_same_input_always_gives_same_output() -> None:
    old = {"a": 1, "b": "x", "c": None}
    new = {"a": "1", "c": 3, "d": False}

    assert compare(old, new) == compare(old, new)


# --- Top level (path "$") --------------------------------------------------------


def test_whole_document_changing_type() -> None:
    assert compare({"id": 1}, [1]) == [
        Change("$", ChangeKind.TYPE_CHANGED, Severity.BREAKING, {"id": 1}, [1]),
    ]


def test_top_level_scalars() -> None:
    assert compare(1, 2) == [
        Change("$", ChangeKind.VALUE_CHANGED, Severity.INFO, 1, 2),
    ]


# --- Nested objects --------------------------------------------------------------


def test_change_deep_inside_nested_objects() -> None:
    assert compare({"a": {"b": {"c": 1}}}, {"a": {"b": {"c": "1"}}}) == [
        Change("$.a.b.c", ChangeKind.TYPE_CHANGED, Severity.BREAKING, 1, "1"),
    ]


def test_field_removed_and_added_inside_nested_object() -> None:
    old = {"seller": {"id": 7, "name": "Asha"}}
    new = {"seller": {"name": "Asha", "rating": 4}}

    assert compare(old, new) == [
        Change("$.seller.id", ChangeKind.FIELD_REMOVED, Severity.BREAKING, 7, None),
        Change("$.seller.rating", ChangeKind.FIELD_ADDED, Severity.SAFE, None, 4),
    ]


def test_removed_nested_object_is_one_change_not_one_per_field() -> None:
    seller = {"id": 7, "name": "Asha"}

    assert compare({"id": 1, "seller": seller}, {"id": 1}) == [
        Change("$.seller", ChangeKind.FIELD_REMOVED, Severity.BREAKING, seller, None),
    ]


def test_nested_object_becoming_null_is_a_type_change() -> None:
    # Type check comes first, so the engine doesn't look inside the old object.
    seller = {"id": 7}

    assert compare({"seller": seller}, {"seller": None}) == [
        Change("$.seller", ChangeKind.TYPE_CHANGED, Severity.BREAKING, seller, None),
    ]


def test_changes_are_reported_depth_first() -> None:
    # Everything inside "a" is reported before moving on to "b".
    old = {"a": {"x": 1, "y": 1}, "b": 1}
    new = {"a": {"x": 2, "y": 2}, "b": 2}

    assert [c.path for c in compare(old, new)] == ["$.a.x", "$.a.y", "$.b"]


def test_deeply_nested_document() -> None:
    # Real APIs rarely nest beyond ~10 levels; 100 leaves a wide margin.
    depth = 100
    old: dict = {"leaf": 1}
    new: dict = {"leaf": 2}
    for _ in range(depth):
        old, new = {"n": old}, {"n": new}

    changes = compare(old, new)

    assert len(changes) == 1
    assert changes[0].path == "$" + ".n" * depth + ".leaf"


# --- Paths for keys that aren't simple names -------------------------------------


def test_key_containing_a_dot_uses_bracket_notation() -> None:
    assert compare({"a.b": 1}, {"a.b": 2}) == [
        Change('$["a.b"]', ChangeKind.VALUE_CHANGED, Severity.INFO, 1, 2),
    ]


def test_dotted_key_and_nested_key_get_different_paths() -> None:
    # Without bracket notation, both of these would be reported as "$.a.b".
    flat = compare({"a.b": 1}, {"a.b": 2})
    nested = compare({"a": {"b": 1}}, {"a": {"b": 2}})

    assert flat[0].path != nested[0].path


def test_hyphenated_key_inside_nested_object() -> None:
    assert compare({"user": {"user-id": 1}}, {"user": {}}) == [
        Change('$.user["user-id"]', ChangeKind.FIELD_REMOVED, Severity.BREAKING, 1, None),
    ]


# --- Purity --------------------------------------------------------------------


def test_inputs_are_not_modified() -> None:
    old = {"id": 1, "price": 250, "seller_id": 7}
    new = {"id": 1, "price": "250", "discount": 10}
    old_before, new_before = copy.deepcopy(old), copy.deepcopy(new)

    compare(old, new)

    assert old == old_before
    assert new == new_before
