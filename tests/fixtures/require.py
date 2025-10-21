"""tests.fixtures.vault

Functions for asserting the existence of test prerequisites.
"""

import campus.common.env as campus_env


def env(env: str) -> None:
    """Raise a RuntimeError if not in the required environment."""
    if (this_env := campus_env.ENV) != env:
        raise RuntimeError(f"ENV != {env} (currently in {this_env})")


def envvar(var: str) -> str:
    """Raise an EnvironmentError if the required environment variable
    is unavailable.
    """
    if getattr(campus_env, var) is None:
        raise EnvironmentError(f"{var} not set")
    return getattr(campus_env, var)
