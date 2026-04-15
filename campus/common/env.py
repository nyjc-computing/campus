"""campus.common.env

An environment proxy module.

The module is expected to be widely imported throughout Campus.
It should be lightweight and have minimal dependencies.

This module provides attribute and function-style access to environment
variables. Use attribute access (env.VAR_NAME) for direct access to
environment variables, or use the get() function for default values.
"""

import os
from typing import Callable, overload

# Expected environment variables (for type checking)

# Codespaces environment variables
CODESPACES: str  # 'true' if running in GitHub Codespaces
CODESPACE_NAME: str  # name of the Codespace
GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN: str  # domain for port forwarding in Codespaces

CLIENT_ID: str
CLIENT_SECRET: str
DEPLOY: str
ENV: str  # deployment environment (development, staging, production)
HOSTNAME: str  # used for generating redirect_uris
PORT: str  # port for running development server
SECRET_KEY: str  # secret key for signing sessions and tokens
VAULTDB_URI: str  # PostgreSQL connection URI for vault service
WORKSPACE_DOMAIN: str  # Google Workspace domain

CAMPUS_OAUTH_REDIRECT_URI: str  # redirect_uri for integration providers

# Type stub for getsecret function
GetSecretFunc = Callable[[str], str]
_getsecret_func: GetSecretFunc | None = None


def register_getsecret(func: GetSecretFunc) -> None:
    """Register a custom getsecret function.

    This allows deployment-specific implementations of getsecret
    without creating tight coupling. For example, campus.auth can
    register its own implementation that uses internal resources
    instead of campus_python.

    The registered function should handle all vault querying logic
    internally, including vault_label selection and access control.

    Args:
        func: A function that takes name (str) and returns the secret value.
              The function should handle vault querying internally.
    """
    global _getsecret_func
    _getsecret_func = func


def getsecret(name: str, vault_label: str | None = None) -> str:
    """Get environment variable by name, falling back to registered getsecret function.

    This function first checks if the environment variable is set. If not,
    it calls the registered getsecret function (if available).

    Args:
        name (str): Name of the environment variable.
        vault_label (str | None): Ignored parameter for backward compatibility.
            Custom getsecret functions should handle vault querying internally.

    Returns:
        str: Value of the environment variable or vault secret.

    Raises:
        OSError: If neither environment variable is set nor getsecret function registered.
    """
    # Check environment variable first
    if name in os.environ:
        return os.environ[name]

    # Use registered getsecret function if available
    if _getsecret_func is not None:
        return _getsecret_func(name)

    raise OSError(f"Secret {name!r} not found")


@overload
def get(name: str) -> str | None: ...

@overload
def get(name: str, default: str) -> str: ...

@overload
def get(name: str, default: str | None) -> str | None: ...

def get(name: str, default: str | None = None) -> str | None:
    """Get environment variable by name.

    Args:
        name (str): Name of the environment variable.
        default (str | None): Default value to return if not set.

    Returns:
        str | None: Value of the environment variable, or default if not set.
        When a non-None default is provided, the return type is str.
    """
    return os.getenv(name, default)


def set(name: str, value: str) -> None:
    """Set environment variable by name.

    Args:
        name (str): Name of the environment variable.
        value (str): Value to set.
    """
    os.environ[name] = value


def delete(name: str) -> None:
    """Delete environment variable by name.

    Args:
        name (str): Name of the environment variable.

    Raises:
        KeyError: If the environment variable is not set.
    """
    if name in os.environ:
        del os.environ[name]
    else:
        raise KeyError(f"Environment variable '{name}' is not set")


def contains(name: str) -> bool:
    """Check if environment variable is set.

    Args:
        name (str): Name of the environment variable.

    Returns:
        bool: True if the environment variable is set, False otherwise.
    """
    return name in os.environ


def keys() -> list[str]:
    """Get a list of all environment variable names.

    Returns:
        list[str]: List of environment variable names.
    """
    return list(os.environ.keys())


def require(*envvars: str) -> None:
    """Require that specified environment variables are set.

    Args:
        *envvars (str): Names of required environment variables.

    Raises:
        OSError: If any required environment variable is not set.
    """
    missing = [var for var in envvars if var not in os.environ]
    if missing:
        raise OSError(
            f"Missing required environment variables: "
            f"{', '.join(missing)}"
        )


# Module-level __getattr__ for attribute-style access
def __getattr__(name: str) -> str:
    """Get environment variable by name via attribute access.

    This enables env.VAR_NAME syntax for accessing environment variables.

    Args:
        name (str): Name of the environment variable.

    Returns:
        str: Value of the environment variable.

    Raises:
        AttributeError: If the environment variable is not set.
    """
    if name in os.environ:
        return os.environ[name]
    raise AttributeError(
        f"module '{__name__}' has no attribute '{name}' "
        f"and environment variable '{name}' is not set"
    )
