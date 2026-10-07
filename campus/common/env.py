"""campus.common.env

An environment proxy module.

The module is expected to be widely imported throughout Campus.
It should be lightweight and have minimal dependencies.

This module provides attribute and function-style access to environment
variables. Use attribute access (env.VAR_NAME) for direct access to
environment variables, or use the get() function for default values.

It also hosts the deployment-environment helpers (the Env constants,
ENV, the block_env/confirm_action_in_env/require_env decorators and
load_dotenv), folded in from campus.common.devops so that common code
can gate on the environment without pulling in campus.deploy.
"""

import os
from functools import wraps
from logging import getLogger
from typing import Any, Callable, Literal, cast, overload
from warnings import warn

# Deployment environments
Env = Literal["development", "testing", "staging", "production"]
DEVELOPMENT = "development"
TESTING = "testing"
STAGING = "staging"
PRODUCTION = "production"

# Expected environment variables (for type checking)
# `bool` type env vars accept only a "0" or "1".
# OSError raised for invalid value

# Codespaces environment variables
CODESPACES: str  # 'true' if running in GitHub Codespaces
CODESPACE_NAME: str  # name of the Codespace
GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN: str  # domain for port forwarding in Codespaces

# Deployment environment variables
CLIENT_ID: str  # Campus client ID
CLIENT_SECRET: str  # Campus client secret
DEPLOY: str  # Campus deployment, (campus.auth, campus.api, campus.audit)
ENV: str  # deployment environment (Env); defaults to DEVELOPMENT when unset
HOSTNAME: str  # dev-server bind host / Codespaces URL derivation; NOT used for URL generation
PUBLIC_URL: str  # required canonical public origin (scheme://host[:port]) for absolute URL generation
PORT: str  # port for running development server
SECRET_KEY: str  # secret key for signing sessions and tokens
WORKSPACE_DOMAIN: str  # Google Workspace domain

# Database environment variables
MONGODB_URI: str
POSTGRESDB_URI: str
SQLITE_URI: str

# OAuth environment variables
CAMPUS_OAUTH_REDIRECT_URI: str  # redirect_uri for integration providers

# Audit tracing middleware
AUDIT_API_KEY: str  # campus.audit API key (audit_v1_...) for span ingestion
AUDIT_EVENTS_ENABLED: bool  # Trace campus.audit internal API calls
AUDIT_TRACING_ENABLED: bool  # Enable audit tracing middleware ("1" or "0")

# Test modes
STORAGE_MODE: str  # "1" if using test storage backend, "0" if using deployment

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

def get(name: str, default: str | None = None) -> Any:
    """Get environment variable by name.

    Args:
        name (str): Name of the environment variable.
        default (str | None): Default value to return if not set.

    Returns:
        str | None: Value of the environment variable, or default if not set.
        When a non-None default is provided, the return type is str.
    """
    var = os.getenv(name, default)
    annotations = cast(dict, locals().get("__annotations__", {}))
    if not annotations or name not in annotations:
        return var
    # Type-specific handling
    match annotations[name]:
        case bool():
            return get_flag(name)
        case _:
            return var

def get_flag(name: str, default: bool = False) -> bool:
    """Get boolean environment variable.

    Converts string environment variables to boolean values.
    Only accepts "1" (True) or "0"/None (False) for safety.

    Args:
        name: Name of the environment variable.
        default: Default value if not set (defaults to False).

    Returns:
        bool: True if value is "1", False if value is "0"/None/missing.

    Raises:
        OSError: If value is set but not "0" or "1".

    Examples:
        >>> env.get_flag("AUDIT_TRACING_ENABLED")
        False

        >>> env.get_flag("AUDIT_TRACING_ENABLED", True)
        True

        >>> env.set("AUDIT_TRACING_ENABLED", "1")
        >>> env.get_flag("AUDIT_TRACING_ENABLED")
        True
    """
    value = os.getenv(name)

    # Handle unset
    if value is None:
        return default

    # Validate and convert
    if value == "1":
        return True
    elif value == "0":
        return False
    else:
        raise OSError(
            f"Invalid boolean flag value for {name!r}: {value!r}. "
            f"Must be '0' (disabled) or '1' (enabled)."
        )


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


def _current_env() -> str:
    """Return the current deployment environment, read dynamically.

    Resolves in the same order as env.ENV attribute access: an explicit
    module attribute first (e.g. set by tests), then the ENV environment
    variable, defaulting to DEVELOPMENT when unset. The old
    campus.common.devops.ENV froze this value at import time; it is now
    read at call time so env.set("ENV", ...) takes effect immediately.
    """
    if (value := globals().get("ENV")) is not None:
        return value
    return os.getenv("ENV", DEVELOPMENT)


def block_env(*envs: str):
    """Decorator to block function execution in specified environments.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if _current_env() in envs:
                raise RuntimeError(
                    f"ENV={_current_env()}: {func.__name__}() cannot be called in {envs} environment."
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator


def confirm_action_in_env(*envs, prompt: str = "Proceed? (y/N): "):
    """
    Decorator to require user confirmation before executing a function in specified environments.
    If the current environment matches one of the specified envs, prompt the user before running.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if _current_env() in envs:
                warn(f"Calling {func.__name__}() in {_current_env()} environment.", stacklevel=2)
                if input(prompt).lower() == 'y':
                    return func(*args, **kwargs)
                else:
                    getLogger(__name__).info("Action cancelled.")
                    return None
            else:
                return func(*args, **kwargs)
        return wrapper
    return decorator


def load_dotenv() -> bool:
    """Load environment variables from a .env file if it exists.

    Values are written to os.environ so they are visible to env.get(),
    env.contains(), env.require() and attribute access alike.
    Existing environment variables are not overridden.

    Returns True if .env file was found and loaded, False otherwise.
    """
    dotenv_path = os.path.join(os.getcwd(), ".env")
    if os.path.exists(dotenv_path):
        with open(dotenv_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip(" \"\'")
                    os.environ.setdefault(key, value)
        return True
    return False


def require_env(*envs: str):
    """Decorator to require specified environments for function execution.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if _current_env() not in envs:
                raise RuntimeError(
                    f"ENV={_current_env()}: {func.__name__}() requires {envs} environment."
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator


# Module-level __getattr__ for attribute-style access
def __getattr__(name: str) -> str:
    """Get environment variable by name via attribute access.

    This enables env.VAR_NAME syntax for accessing environment variables.

    Args:
        name (str): Name of the environment variable.

    Returns:
        str: Value of the environment variable. env.ENV defaults to
        DEVELOPMENT when the ENV environment variable is unset.

    Raises:
        AttributeError: If the environment variable is not set.
    """
    if name == "ENV":
        # Dynamic, like every other env.ENV read: evaluated at access
        # time, assuming development if not defined.
        return os.getenv("ENV", DEVELOPMENT)
    if contains(name) and (var := get(name)):
        return var
    raise AttributeError(
        f"module '{__name__}' has no attribute '{name}' "
        f"and environment variable '{name}' is not set"
    )
