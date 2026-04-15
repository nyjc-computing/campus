"""tests.fixtures.require

Functions for asserting the existence of test prerequisites.
"""

from campus.common import env


def env(env_name: str) -> None:
    """Raise a RuntimeError if not in the required environment."""
    if (this_env := env.ENV) != env_name:
        raise RuntimeError(f"ENV != {env_name} (currently in {this_env})")


def envvar(var: str) -> str:
    """Raise an EnvironmentError if the required environment variable
    is unavailable.
    """
    if getattr(env, var) is None:
        raise EnvironmentError(f"{var} not set")
    return getattr(env, var)
