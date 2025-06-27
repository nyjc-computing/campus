"""common/auth

This module contains authentication-related functionality.
"""

from . import header
from .clientauth import authenticate_client, client_auth_required

__all__ = [
    "authenticate_client",
    "client_auth_required",
    "header",
]
