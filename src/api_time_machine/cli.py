"""Command-line interface: python -m api_time_machine compare OLD NEW

This is the only module that touches files and the terminal; the engine
(diff.py, rules.py) stays pure.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from api_time_machine import __version__
from api_time_machine.diff import compare
from api_time_machine.models import JsonValue, Severity
from api_time_machine.report import format_report

# Exit codes, so scripts and CI can react without parsing the text output.
EXIT_OK = 0  # compared; no breaking changes
EXIT_BREAKING = 1  # compared; at least one breaking change
EXIT_ERROR = 2  # could not compare (bad input or usage); argparse also uses 2


class InputError(Exception):
    """An input file is missing, unreadable, or not valid JSON."""


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return its exit code. `argv` defaults to the real command line."""
    args = _build_parser().parse_args(argv)

    try:
        old = load_json_file(args.old)
        new = load_json_file(args.new)
    except InputError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_ERROR

    changes = compare(old, new)
    print(format_report(changes))
    if any(change.severity is Severity.BREAKING for change in changes):
        return EXIT_BREAKING
    return EXIT_OK


def load_json_file(path: Path) -> JsonValue:
    """Read and parse a JSON file, turning every failure into an InputError."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        raise InputError(f"{path}: file not found") from None
    except OSError as error:
        raise InputError(f"{path}: cannot read file ({error.strerror})") from None

    # Passing bytes (not text) lets the json module detect UTF-8, UTF-8 with a
    # BOM, and UTF-16 (what Windows PowerShell 5.1's `>` writes) by itself.
    try:
        return json.loads(data, parse_constant=_reject_non_standard_constant)
    # Order matters: both of these are subclasses of ValueError, so they must
    # be caught before the general ValueError below.
    except json.JSONDecodeError as error:
        raise InputError(
            f"{path}: invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}"
        ) from None
    except UnicodeDecodeError:
        raise InputError(f"{path}: not valid UTF-8 or UTF-16 text") from None
    except ValueError as error:
        raise InputError(f"{path}: invalid JSON: {error}") from None


def _reject_non_standard_constant(name: str) -> None:
    # Called by json.loads for NaN, Infinity and -Infinity, which Python accepts
    # by default but the JSON standard does not.
    raise ValueError(f"{name} is not allowed in JSON")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m api_time_machine",
        description="Detect breaking changes between two API responses.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    compare_cmd = commands.add_parser(
        "compare",
        help="compare two JSON files",
        description=(
            "Compare two JSON files and report every change. Exit code: 0 = no "
            "breaking changes, 1 = breaking changes found, 2 = error."
        ),
    )
    compare_cmd.add_argument("old", type=Path, help="JSON file with the old response")
    compare_cmd.add_argument("new", type=Path, help="JSON file with the new response")
    return parser
