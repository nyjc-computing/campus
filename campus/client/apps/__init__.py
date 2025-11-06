"""Campus Apps service clients.

Provides clean module interfaces for Campus Apps service resources.
"""

__all__ = [
    'CirclesResource',
    'UsersResource',
]

from .circles import CirclesResource
from .users import UsersResource
