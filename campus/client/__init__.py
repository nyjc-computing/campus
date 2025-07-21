"""client

Campus Client Package

Provides clean service module interfaces for Campus Apps and Vault services,
avoiding circular dependencies while maintaining a clean HTTP-like API.
"""

from .errors import (
    CampusClientError,
    AuthenticationError,
    AccessDeniedError,
    NotFoundError,
    ValidationError,
    NetworkError
)

# Convenience imports to service modules
from .apps import users, circles
from .vault import vault, access, client

__all__ = [
    # Errors
    'CampusClientError',
    'AuthenticationError',
    'AccessDeniedError',
    'NotFoundError',
    'ValidationError',
    'NetworkError',
    # Service modules
    'users', 'circles',
    'vault', 'access', 'client'
]
