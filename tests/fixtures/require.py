"""tests.fixtures.vault

Functions for asserting the existence of test prerequisites.
"""

import os

def env(env: str) -> None:
    """Raise a RuntimeError if not in the required environment."""
    if (this_env := os.environ.get("ENV")) != env:
        raise RuntimeError(f"ENV != {env} (currently in {this_env})")

def envvar(var: str) -> str:
    """Raise an EnvironmentError if the required environment variable
    is unavailable.
    """
    if var not in os.environ:
        raise EnvironmentError(f"{var} not set")
    return os.environ[var]
