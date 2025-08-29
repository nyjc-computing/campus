"""campus.apps

This module contains the main applications for Campus.

## Applications

- api: The API endpoints for the Campus application.
- campusauth: Web endpoints for Campus (OAuth2) authentication.
- integrations: Integrations with third-party platforms and APIs.
- oauth: Campus OAuth2 implementation.
"""

from flask import Blueprint, Flask

from campus.common import errors

from . import api, campusauth, oauth


def create_app() -> Flask:
    """Create the main Campus app with all modules"""
    from campus.client import VaultClient
    vault = VaultClient()
    app = Flask(__name__)
    app.secret_key = vault["campus"]["SECRET_KEY"].get()
    init_app(app)
    errors.init_app(app)
    return app


def init_app(app: Blueprint | Flask) -> None:
    """Initialize the Campus app with all modules."""
    api.init_app(app)
    campusauth.init_app(app)
    oauth.init_app(app)


__all__ = [
    "api",
    "campusauth",
    "oauth",
    "create_app",
    "init_app",
]
