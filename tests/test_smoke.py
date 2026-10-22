"""Smoke test: proves the package is installed and pytest can find it."""

import api_time_machine


def test_package_exposes_version() -> None:
    assert isinstance(api_time_machine.__version__, str)
    assert api_time_machine.__version__ != ""
