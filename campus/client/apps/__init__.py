"""Campus Apps service clients.

Provides clean module interfaces for Campus Apps service resources.
"""

from . import admin, circles, users
from .admin import AdminClient
from .circles import CirclesClient
from .users import UsersClient


__all__ = [
    'admin',
    'circles',
    'users',
    'AdminClient',
    'CirclesClient',
    'UsersClient',
]
