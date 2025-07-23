"""client

Campus Client Package

Provides unified Campus client interface and individual service modules.
"""

from .campus import Campus
from .errors import (
    CampusClientError,
    AuthenticationError,
    AccessDeniedError,
    NotFoundError,
    ValidationError,
    NetworkError
)

# Convenience imports to service modules (for backward compatibility)
from .apps import users, circles
from .vault import vault, access, client

__all__ = [
    # Unified interface
    'Campus',
    # Errors
    'CampusClientError',
    'AuthenticationError',
    'AccessDeniedError',
    'NotFoundError',
    'ValidationError',
    'NetworkError',
    # Service modules (backward compatibility)
    'users', 'circles',
    'vault', 'access', 'client'
]
