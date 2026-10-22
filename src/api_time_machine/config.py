"""Settings read from environment variables, so they live outside the code."""

import os
from collections.abc import Mapping

ALLOWED_HOSTS_VARIABLE = "ATM_ALLOWED_HOSTS"

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
