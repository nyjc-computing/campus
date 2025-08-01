"""campus.common.devops

This module contains the DevOps-related functionality for the Campus project.
"""

import os
from functools import wraps
from typing import Literal
from warnings import warn

# typing stub
Env = Literal["development", "testing", "staging", "production"]

# ENV enums
DEVELOPMENT = "development"
TESTING = "testing"
STAGING = "staging"
PRODUCTION = "production"

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
                    print("Action cancelled.")
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
