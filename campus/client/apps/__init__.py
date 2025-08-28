"""Campus Apps service clients.

Provides clean module interfaces for Campus Apps service resources.
"""

from campus.client.apps import users
from campus.client.apps import circles
from campus.client.apps import admin

__all__ = ['users', 'circles', 'admin']
