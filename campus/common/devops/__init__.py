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


def load_dotenv() -> bool:
    """Load environment variables from a .env file if it exists.

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
            if ENV not in envs:
                raise RuntimeError(
                    f"ENV={ENV}: {func.__name__}() requires {envs} environment."
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator


__all__ = [
    "deploy",
]
