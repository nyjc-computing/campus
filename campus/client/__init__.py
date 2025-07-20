"""client

Campus Client Package

Provides individual service clients that can be imported independently,
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

__all__ = [
    'CampusClientError',
    'AuthenticationError', 
    'AccessDeniedError',
    'NotFoundError',
    'ValidationError',
    'NetworkError'
]
