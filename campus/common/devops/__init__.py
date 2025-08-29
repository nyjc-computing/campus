"""campus.common.devops

This module contains the DevOps-related functionality for the Campus project.
"""

import os
from functools import wraps
import logging
from typing import Literal
from warnings import warn

# Namespace exports
from . import deploy

# typing stub
Env = Literal["development", "testing", "staging", "production"]

# ENV enums
DEVELOPMENT = "development"
TESTING = "testing"
STAGING = "staging"
PRODUCTION = "production"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# If not defined, assume development environment
ENV = os.getenv("ENV", "development")
assert ENV in (
    DEVELOPMENT,
    TESTING,
    STAGING,
    PRODUCTION,
), f"Invalid environment: {ENV}"


def block_env(*envs: str):
    """Decorator to block function execution in specified environments.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if ENV in envs:
                raise RuntimeError(
                    f"ENV={ENV}: {func.__name__}() cannot be called in {envs} environment."
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
            if ENV in envs:
                warn(f"Calling {func.__name__}() in {ENV} environment.", stacklevel=2)
                if input(prompt).lower() == 'y':
                    return func(*args, **kwargs)
                else:
                    logger.info("Action cancelled.")
                    return None
            else:
                return func(*args, **kwargs)
        return wrapper
    return decorator


def require_env(*envs: str):
    """Decorator to require specified environments for function execution.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if ENV not in envs:
                raise RuntimeError(
                    f"ENV={ENV}: {func.__name__}() requires {envs} environment."
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator


def load_credentials_from_env() -> tuple[str, str] | str:
    """
    Load client credentials from environment variables.

    Attempts to load ACCESS_TOKEN (for bearer auth) or CLIENT_ID and
    CLIENT_SECRET (for basic auth) from environment variables.

    Raises:
        AuthenticationError: If required environment variables are absent.
    """
    if (value := os.getenv("ACCESS_TOKEN")):
        return value
    id_, secret = os.getenv("CLIENT_ID"), os.getenv("CLIENT_SECRET")
    if id_ and secret:
        return id_, secret
    raise EnvironmentError(
        f"Missing credentials {'CLIENT_ID' if not id_ else 'CLIENT_SECRET'}"
    )
