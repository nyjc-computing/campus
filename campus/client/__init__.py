"""client

Campus Client Package

Provides unified Campus client interface.
"""

from campus.client.core import Campus
from campus.client.errors import (
    CampusClientError,
    AuthenticationError,
    AccessDeniedError,
    NotFoundError,
    ValidationError,
    NetworkError
)

__all__ = [
    'Campus',
    'CampusClientError',
    'AuthenticationError',
    'AccessDeniedError',
    'NotFoundError',
    'ValidationError',
    'NetworkError',
]
