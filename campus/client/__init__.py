"""campus.client

Campus Client Package

Provides unified Campus client interface.
"""

from .core import Campus

# Namespace imports
from .apps import AdminResource, CirclesResource, UsersResource
from .vault import VaultResource

__all__ = [
    'Campus',
    'AdminResource',
    'CirclesResource',
    'UsersResource',
    'VaultResource',
]
