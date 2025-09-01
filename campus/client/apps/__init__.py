"""Campus Apps service clients.

Provides clean module interfaces for Campus Apps service resources.
"""

from .admin import AdminClient
from .circles import CirclesClient
from .users import UsersClient


__all__ = [
    'AdminClient',
    'CirclesClient',
    'UsersClient',
]
