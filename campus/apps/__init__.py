"""apps

This module contains the main applications for Campus.

## Applications

- api: The API endpoints for the Campus application.
- campusauth: Web endpoints for Campus (OAuth2) authentication.
- integrations: Integrations with third-party platforms and APIs.
- oauth: Campus OAuth2 implementation.
"""

from . import api, campusauth, oauth
from .campusauth import ctx
from .factory import create_app_from_modules

__all__ = [
    "api",
    "campusauth",
    "oauth",
    "create_app_from_modules",
    "ctx",
]
