"""Tests for the command-line interface: files in, report and exit code out."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from api_time_machine.cli import EXIT_BREAKING, EXIT_ERROR, EXIT_OK, main


def write_json(folder: Path, name: str, data: object) -> Path:
    path = folder / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# --- Exit codes ----------------------------------------------------------------


def test_identical_files_exit_ok(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    old = write_json(tmp_path, "old.json", {"price": 250})
    new = write_json(tmp_path, "new.json", {"price": 250})

    assert main(["compare", str(old), str(new)]) == EXIT_OK
    assert capsys.readouterr().out == "No changes.\n"


def test_breaking_change_exits_with_breaking_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old = write_json(tmp_path, "old.json", {"price": 250})
    new = write_json(tmp_path, "new.json", {"price": "250"})

    assert main(["compare", str(old), str(new)]) == EXIT_BREAKING
    out = capsys.readouterr().out
    assert "BREAKING" in out
    assert "$.price" in out


def test_only_safe_and_info_changes_exit_ok(tmp_path: Path) -> None:
    old = write_json(tmp_path, "old.json", {"stock": 12})
    new = write_json(tmp_path, "new.json", {"stock": 9, "discount": 10})

    assert main(["compare", str(old), str(new)]) == EXIT_OK


# --- Input errors: exit 2, message on stderr, nothing on stdout ----------------------


def test_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    new = write_json(tmp_path, "new.json", {})

    assert main(["compare", str(tmp_path / "nope.json"), str(new)]) == EXIT_ERROR
    captured = capsys.readouterr()
    assert "file not found" in captured.err
    assert "nope.json" in captured.err
    assert captured.out == ""


def test_directory_instead_of_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    new = write_json(tmp_path, "new.json", {})

    assert main(["compare", str(tmp_path), str(new)]) == EXIT_ERROR
    assert "cannot read" in capsys.readouterr().err


def test_invalid_json_reports_line_and_column(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.json"
    # Missing comma after 250. (Not a trailing comma: where Python reports
    # that error differs between versions, which would make this test fragile.)
    bad.write_text('{\n  "price": 250\n  "stock": 9\n}', encoding="utf-8")
    new = write_json(tmp_path, "new.json", {})

    assert main(["compare", str(bad), str(new)]) == EXIT_ERROR
    err = capsys.readouterr().err
    assert "invalid JSON" in err
    assert "line 3" in err


def test_empty_file_is_invalid_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    empty = tmp_path / "empty.json"
    empty.write_bytes(b"")
    new = write_json(tmp_path, "new.json", {})

    assert main(["compare", str(empty), str(new)]) == EXIT_ERROR
    assert "invalid JSON" in capsys.readouterr().err


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_nan_and_infinity_are_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], constant: str
) -> None:
    # Python's json module accepts these by default, but they aren't valid JSON,
    # and NaN != NaN would create fake value changes.
    bad = tmp_path / "bad.json"
    bad.write_text(f'{{"score": {constant}}}', encoding="utf-8")
    new = write_json(tmp_path, "new.json", {})

    assert main(["compare", str(bad), str(new)]) == EXIT_ERROR
    assert constant in capsys.readouterr().err


def test_bytes_that_are_not_text(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    binary = tmp_path / "image.json"
    binary.write_bytes(b"\xff\xfe\xfd\x00\x80")
    new = write_json(tmp_path, "new.json", {})

    assert main(["compare", str(binary), str(new)]) == EXIT_ERROR
    assert "not valid" in capsys.readouterr().err


def test_missing_arguments_exit_with_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    # argparse handles usage errors itself, by exiting with code 2.
    with pytest.raises(SystemExit) as exit_info:
        main(["compare"])

    assert exit_info.value.code == EXIT_ERROR
    assert "usage:" in capsys.readouterr().err


# --- Windows text encodings ------------------------------------------------------


def test_utf8_file_with_bom(tmp_path: Path) -> None:
    # Notepad and some PowerShell commands add a byte order mark (BOM).
    old = tmp_path / "old.json"
    old.write_text('{"price": 250}', encoding="utf-8-sig")
    new = write_json(tmp_path, "new.json", {"price": 250})

    assert main(["compare", str(old), str(new)]) == EXIT_OK


def test_utf16_file(tmp_path: Path) -> None:
    # Windows PowerShell 5.1's `>` redirect writes UTF-16.
    old = tmp_path / "old.json"
    old.write_text('{"price": 250}', encoding="utf-16")
    new = write_json(tmp_path, "new.json", {"price": 250})

    assert main(["compare", str(old), str(new)]) == EXIT_OK


# --- Example files (shown in the README) -------------------------------------------

EXAMPLES = Path(__file__).parent.parent / "examples"


def test_example_files_cover_every_severity(capsys: pytest.CaptureFixture[str]) -> None:
    old, new = EXAMPLES / "product_v1.json", EXAMPLES / "product_v2.json"

    assert main(["compare", str(old), str(new)]) == EXIT_BREAKING
    assert capsys.readouterr().out.endswith("9 changes: 4 breaking, 3 safe, 2 info\n")


# --- Running as `python -m api_time_machine` ---------------------------------------


def test_runs_as_a_module(tmp_path: Path) -> None:
    old = write_json(tmp_path, "old.json", {"price": 250})
    new = write_json(tmp_path, "new.json", {"price": "250"})

    result = subprocess.run(
        [sys.executable, "-m", "api_time_machine", "compare", str(old), str(new)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == EXIT_BREAKING
    assert "$.price" in result.stdout
