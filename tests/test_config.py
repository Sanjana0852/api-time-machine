"""Tests for settings read from environment variables."""

import pytest

from api_time_machine.config import (
    DEFAULT_ALLOWED_HOSTS,
    allowed_hosts_from_env,
    database_url_for_tests_from_env,
    database_url_from_env,
)


def test_default_allows_only_this_machine() -> None:
    assert allowed_hosts_from_env({}) == DEFAULT_ALLOWED_HOSTS == {"localhost", "127.0.0.1"}


def test_hosts_are_read_from_environment_variable() -> None:
    environ = {"ATM_ALLOWED_HOSTS": "localhost, API.Staging.Example.com ,127.0.0.1"}

    # Spaces are trimmed and hosts are lowercased (host names are case-insensitive).
    assert allowed_hosts_from_env(environ) == {
        "localhost",
        "api.staging.example.com",
        "127.0.0.1",
    }


def test_empty_variable_allows_nothing() -> None:
    # Fail safe: a blank setting must not mean "allow everything".
    assert allowed_hosts_from_env({"ATM_ALLOWED_HOSTS": ""}) == frozenset()
    assert allowed_hosts_from_env({"ATM_ALLOWED_HOSTS": " , "}) == frozenset()


# --- Database URLs -------------------------------------------------------------------

URL = "postgresql+psycopg://atm:secret@localhost:5432/api_time_machine"


@pytest.mark.parametrize(
    ("read", "variable"),
    [
        (database_url_from_env, "ATM_DATABASE_URL"),
        (database_url_for_tests_from_env, "ATM_TEST_DATABASE_URL"),
    ],
)
def test_database_url_is_read_from_its_variable(read, variable: str) -> None:  # type: ignore[no-untyped-def]
    assert read({variable: URL}) == URL
    assert read({variable: f"  {URL}  "}) == URL  # stray spaces from a .env file


@pytest.mark.parametrize("read", [database_url_from_env, database_url_for_tests_from_env])
def test_missing_or_blank_database_url_means_not_configured(read) -> None:  # type: ignore[no-untyped-def]
    # History is optional: no URL means "off", not an error.
    assert read({}) is None
    assert read({"ATM_DATABASE_URL": "", "ATM_TEST_DATABASE_URL": "   "}) is None


def test_test_database_is_never_the_real_database() -> None:
    # A test run must not be able to roll back or pollute real history.
    environ = {"ATM_DATABASE_URL": URL, "ATM_TEST_DATABASE_URL": URL}

    with pytest.raises(ValueError, match="must be different"):
        database_url_for_tests_from_env(environ)
