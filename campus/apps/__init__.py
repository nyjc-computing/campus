"""campus.apps

This module contains the main applications for Campus.

## Applications

- api: The API endpoints for the Campus application.
- campusauth: Web endpoints for Campus (OAuth2) authentication.
- integrations: Integrations with third-party platforms and APIs.
- oauth: Campus OAuth2 implementation.
"""

from flask import Blueprint, Flask

from . import api, campusauth, oauth


def init_app(app: Blueprint | Flask) -> None:
    """Initialize the Campus app with all modules."""
    api.init_app(app)
    campusauth.init_app(app)
    oauth.init_app(app)


__all__ = [
    "api",
    "campusauth",
    "oauth",
    "init_app",
]
