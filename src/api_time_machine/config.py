"""Settings read from environment variables, so they live outside the code.

Variables can also be put in a .env file in the folder you run from; see
load_env_file() and .env.example.
"""

import os
from collections.abc import Mapping

from dotenv import find_dotenv, load_dotenv

ALLOWED_HOSTS_VARIABLE = "ATM_ALLOWED_HOSTS"
DATABASE_URL_VARIABLE = "ATM_DATABASE_URL"
TEST_DATABASE_URL_VARIABLE = "ATM_TEST_DATABASE_URL"

# Only this machine, unless configured otherwise.
DEFAULT_ALLOWED_HOSTS = frozenset({"localhost", "127.0.0.1"})


def allowed_hosts_from_env(environ: Mapping[str, str] = os.environ) -> frozenset[str]:
    """Return the hosts that replay may contact (design doc, rule S1).

    ATM_ALLOWED_HOSTS is a comma-separated list, e.g. "localhost,api.staging.example.com".
    Unset means DEFAULT_ALLOWED_HOSTS. Set but empty means no hosts at all: a
    blank setting must never mean "allow everything".
    """
    raw = environ.get(ALLOWED_HOSTS_VARIABLE)
    if raw is None:
        return DEFAULT_ALLOWED_HOSTS
    # Host names are case-insensitive, so compare them in lowercase.
    return frozenset(host.strip().lower() for host in raw.split(",") if host.strip())


def database_url_from_env(environ: Mapping[str, str] = os.environ) -> str | None:
    """Return the history database URL, or None if history isn't configured."""
    return _non_blank(environ.get(DATABASE_URL_VARIABLE))


def database_url_for_tests_from_env(environ: Mapping[str, str] = os.environ) -> str | None:
    """Return the test database URL, or None if database tests should be skipped.

    Raises ValueError if it is the same as the real database URL: tests create
    and roll back rows, so they must never run against real history.
    """
    url = _non_blank(environ.get(TEST_DATABASE_URL_VARIABLE))
    if url is not None and url == database_url_from_env(environ):
        raise ValueError(
            f"{TEST_DATABASE_URL_VARIABLE} and {DATABASE_URL_VARIABLE} must be different databases"
        )
    return url


def load_env_file() -> None:
    """Load variables from a .env file in the current folder (or a parent folder).

    Variables already set in the environment win over the file, so a value set
    in the terminal always takes precedence.
    """
    load_dotenv(find_dotenv(usecwd=True))


def _non_blank(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value.strip()
