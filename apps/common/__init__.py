"""apps.common

This module contains common functions and classes used across multiple
applications.

Modules:

- errors: Contains error definitions and handling for API errors.
- webauth: Contains web authentication models and configurations.
"""

from . import errors, models

circles = models.circle.Circle()
users = models.user.User()
# venues = models.venue.Venue()
emailotp = models.emailotp.EmailOTPAuth()


__all__ = [
    "errors",
    "models",
    "circles",
    "users",
    # "venues",
    "emailotp",
]
