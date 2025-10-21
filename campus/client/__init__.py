"""campus.client

Campus Client Package

Provides unified Campus client interface.
"""

__all__ = [
    'AdminResource',
    'Campus',
    'CirclesResource',
    'UsersResource',
    'VaultResource',
]

from .core import Campus

# Namespace imports
from .apps import AdminResource, CirclesResource, UsersResource
from .vault import VaultResource
