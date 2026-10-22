"""Entry point for `python -m api_time_machine`."""

import sys

from api_time_machine.cli import main
from api_time_machine.config import load_env_file

if __name__ == "__main__":
    # Loaded here, not in cli.py, so importing cli in tests has no side effects.
    load_env_file()
    sys.exit(main())
