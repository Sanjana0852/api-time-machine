"""API Time Machine: detect breaking changes between API response versions."""

from importlib.metadata import version

# Read the version from the installed package metadata (set in pyproject.toml),
# so the version number is defined in exactly one place.
__version__: str = version("api-time-machine")
