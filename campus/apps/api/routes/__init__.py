"""campus.apps.api.routes

This is a namespace module for the Campus API routes.
"""

from . import circles, emailotp, users, admin, events

__all__ = [
    "circles",
    "emailotp",
    "users",
    "admin",
    "events"
]
