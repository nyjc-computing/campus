"""Campus Apps service clients.

Provides clean module interfaces for Campus Apps service resources.
"""

from campus.client.apps.admin import AdminResource
from campus.client.apps.circles import CirclesResource
from campus.client.apps.users import UsersResource


__all__ = [
    'AdminResource',
    'CirclesResource',
    'UsersResource',
]
