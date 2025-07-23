"""client

Campus Client Package

Provides unified Campus client interface.
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
]
