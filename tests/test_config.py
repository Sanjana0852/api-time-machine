"""Tests for settings read from environment variables."""

from api_time_machine.config import DEFAULT_ALLOWED_HOSTS, allowed_hosts_from_env


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
