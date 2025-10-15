"""campus.apps.api.routes

This is a namespace module for the Campus API routes.
"""

__all__ = [
    "admin",
    "circles",
    "emailotp",
    "users",
]

from . import circles, emailotp, users, admin
