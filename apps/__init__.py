"""apps

This module contains the main applications for Campus.

## Applications

- api: The API endpoints for the Campus application.
- campusauth: Web endpoints for Campus (OAuth2) authentication.
- integrations: Integrations with third-party platforms and APIs.
- oauth: Campus OAuth2 implementation.
"""

from . import api, campusauth, config, oauth

__all__ = [
    "api",
    "campusauth",
    "config",
    "oauth",
]
