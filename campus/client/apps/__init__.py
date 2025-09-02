"""Campus Apps service clients.

Provides clean module interfaces for Campus Apps service resources.
"""

from .admin import AdminResource
from .circles import CirclesResource
from .users import UsersResource


__all__ = [
    'AdminResource',
    'CirclesResource',
    'UsersResource',
]
