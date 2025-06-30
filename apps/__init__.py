"""apps

This module contains the main applications for Campus.

## Applications

- api: The API endpoints for the Campus application.
- campusauth: Web endpoints for Campus (OAuth2) authentication.
- integrations: Integrations with third-party platforms and APIs.
- oauth: Campus OAuth2 implementation.

## Common app modules
- errors: Common error handling for Campus apps.
- webauth: Web authentication models.
"""

from .common import errors, webauth
from . import api, campusauth, integrations, oauth

__all__ = [
    "api",
    "campusauth",
    "integrations",
    "oauth",
    "errors",
    "webauth",
]
