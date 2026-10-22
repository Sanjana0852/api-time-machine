"""Command-line interface.

    python -m api_time_machine compare OLD_FILE NEW_FILE
    python -m api_time_machine replay OLD_URL NEW_URL

This module handles files, the terminal and exit codes; the engine (diff.py,
rules.py) stays pure.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import httpx

from api_time_machine import __version__
from api_time_machine.config import allowed_hosts_from_env
from api_time_machine.diff import compare
from api_time_machine.fetch import FetchError
from api_time_machine.jsonparse import parse_json
from api_time_machine.models import JsonValue, Severity
from api_time_machine.replay import ReplayResult, replay
from api_time_machine.report import format_replay_report, format_report

# Exit codes, so scripts and CI can react without parsing the text output.
EXIT_OK = 0  # compared; no breaking changes
EXIT_BREAKING = 1  # compared; at least one breaking change
EXIT_ERROR = 2  # could not compare (bad input or usage); argparse also uses 2


class InputError(Exception):
    """An input file is missing, unreadable, or not valid JSON."""


def main(
    argv: Sequence[str] | None = None, *, transport: httpx.AsyncBaseTransport | None = None
) -> int:
    """Run the CLI and return its exit code.

    `argv` defaults to the real command line. `transport` is for tests: it
    replaces the network, e.g. with httpx.ASGITransport(app=...).
    """
    args = _build_parser().parse_args(argv)
    if args.command == "replay":
        return _run_replay(args.old_url, args.new_url, transport)
    return _run_compare(args.old, args.new)


def _run_compare(old_path: Path, new_path: Path) -> int:
    try:
        old = load_json_file(old_path)
        new = load_json_file(new_path)
    except InputError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_ERROR

    changes = compare(old, new)
    print(format_report(changes))
    if any(change.severity is Severity.BREAKING for change in changes):
        return EXIT_BREAKING
    return EXIT_OK


def _run_replay(old_url: str, new_url: str, transport: httpx.AsyncBaseTransport | None) -> int:
    try:
        result = asyncio.run(_replay(old_url, new_url, transport))
    except FetchError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_ERROR

    print(format_replay_report(result))
    return EXIT_BREAKING if result.has_breaking else EXIT_OK


async def _replay(
    old_url: str, new_url: str, transport: httpx.AsyncBaseTransport | None
) -> ReplayResult:
    # `async with` closes the client's network connections when we're done.
    async with httpx.AsyncClient(transport=transport) as client:
        return await replay(client, old_url, new_url, allowed_hosts_from_env())


def load_json_file(path: Path) -> JsonValue:
    """Read and parse a JSON file, turning every failure into an InputError."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        raise InputError(f"{path}: file not found") from None
    except OSError as error:
        raise InputError(f"{path}: cannot read file ({error.strerror})") from None

    try:
        return parse_json(data)
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

    replay_cmd = commands.add_parser(
        "replay",
        help="fetch two URLs and compare the responses",
        description=(
            "Send a GET request to both URLs and compare the responses, including "
            "status codes. Only hosts listed in the ATM_ALLOWED_HOSTS environment "
            "variable can be contacted (default: localhost, 127.0.0.1). Exit code: "
            "0 = no breaking changes, 1 = breaking changes found, 2 = error."
        ),
    )
    replay_cmd.add_argument("old_url", help="URL of the old API version")
    replay_cmd.add_argument("new_url", help="URL of the new API version")
    return parser
