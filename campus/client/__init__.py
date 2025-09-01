"""campus.client

Campus Client Package

Provides unified Campus client interface.
"""

from .core import Campus
from .errors import (
    CampusClientError,
    AuthenticationError,
    AccessDeniedError,
    NotFoundError,
    ValidationError,
    NetworkError
)
# Namespace imports
from .apps import AdminClient, CirclesClient, UsersClient
from .vault import VaultClient

__all__ = [
    'Campus',
    'CampusClientError',
    'AuthenticationError',
    'AccessDeniedError',
    'NotFoundError',
    'ValidationError',
    'NetworkError',
    'AdminClient',
    'CirclesClient',
    'UsersClient',
    'VaultClient',
]
