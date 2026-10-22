"""Strict JSON parsing, shared by every way JSON enters the tool (files and HTTP)."""

import json

from api_time_machine.models import JsonValue


def parse_json(data: bytes) -> JsonValue:
    """Parse JSON from raw bytes.

    Passing bytes (not text) lets the json module detect UTF-8, UTF-8 with a
    BOM, and UTF-16 (what Windows PowerShell 5.1's `>` writes) by itself.

    Raises ValueError for anything that isn't valid JSON, including NaN and
    Infinity, which Python accepts by default but the JSON standard does not.
    More specific subclasses: json.JSONDecodeError (bad syntax) and
    UnicodeDecodeError (not text).
    """
    return json.loads(data, parse_constant=_reject_non_standard_constant)


def _reject_non_standard_constant(name: str) -> None:
    # Called by json.loads for NaN, Infinity and -Infinity.
    raise ValueError(f"{name} is not allowed in JSON")
