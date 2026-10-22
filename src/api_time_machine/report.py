"""Turn a list of changes into a human-readable text report.

Pure: builds and returns strings, never prints. Output is ASCII-only (e.g. "->"
rather than an arrow character) so it can't fail on Windows consoles or files
that use a legacy encoding.
"""

import json
from typing import assert_never

from api_time_machine.models import Change, ChangeKind, JsonValue, Severity, json_type

# Values longer than this (e.g. whole objects) are cut short with "...".
_MAX_VALUE_WIDTH = 40
# Wide enough for the longest severity label, "BREAKING".
_SEVERITY_WIDTH = max(len(severity) for severity in Severity)


def describe(change: Change) -> str:
    """Return a one-line description of a change, without its path or severity."""
    old, new = change.old_value, change.new_value
    match change.kind:
        case ChangeKind.FIELD_ADDED:
            return f"field added ({json_type(new)})"
        case ChangeKind.FIELD_REMOVED:
            return "field removed"
        case ChangeKind.TYPE_CHANGED:
            return (
                f"type changed: {json_type(old)} -> {json_type(new)}"
                f"  ({_format_value(old)} -> {_format_value(new)})"
            )
        case ChangeKind.VALUE_CHANGED:
            return f"value changed: {_format_value(old)} -> {_format_value(new)}"
        case ChangeKind.ITEM_ADDED:
            return f"item added ({json_type(new)})"
        case ChangeKind.ITEM_REMOVED:
            return "item removed"
        case _:
            assert_never(change.kind)


def format_report(changes: list[Change]) -> str:
    """Return the full report: one aligned line per change, then a summary."""
    if not changes:
        return "No changes."

    path_width = max(len(change.path) for change in changes)
    lines = [
        f"{change.severity.upper():<{_SEVERITY_WIDTH}}  "
        f"{change.path:<{path_width}}  {describe(change)}"
        for change in changes
    ]
    return "\n".join(lines) + "\n\n" + _summary(changes)


def _summary(changes: list[Change]) -> str:
    counts = {severity: 0 for severity in Severity}
    for change in changes:
        counts[change.severity] += 1

    noun = "change" if len(changes) == 1 else "changes"
    breakdown = ", ".join(f"{count} {severity}" for severity, count in counts.items())
    return f"{len(changes)} {noun}: {breakdown}"


def _format_value(value: JsonValue) -> str:
    # JSON form keeps strings quoted, so 250 -> "250" is visibly a type change.
    text = json.dumps(value)
    if len(text) > _MAX_VALUE_WIDTH:
        return text[: _MAX_VALUE_WIDTH - 3] + "..."
    return text
