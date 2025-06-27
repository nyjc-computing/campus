"""common/devops

This module contains the DevOps-related functionality for the Campus project.
"""

import os
from functools import wraps
from typing import Literal


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


def require_env(*envs: str):
    """Decorator to enforce the current environment matches the required
    environment before calling the decorated function.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if ENV not in envs:
                raise RuntimeError(
                    f"ENV={ENV}: A {envs} environment is required."
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator
