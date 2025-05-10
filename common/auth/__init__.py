"""common/auth

This module contains authentication-related functionality.
"""

from .decorator import authenticate_client, client_auth_required

__all__ = [
    "authenticate_client",
    "client_auth_required",
]
