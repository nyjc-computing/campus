"""campus.apps

This module contains the main applications for Campus.

## Applications

- api: The API endpoints for the Campus application.
- campusauth: Web endpoints for Campus (OAuth2) authentication.
- integrations: Integrations with third-party platforms and APIs.
- oauth: Campus OAuth2 implementation.
"""

from flask import Flask
from campus.client import Campus

from . import api, campusauth, oauth
from .campusauth import ctx


def create_app_from_modules(*modules) -> Flask:
    """Factory function to create the Flask app.

    This is called if api is run as a standalone app.
    """
    app = Flask(__name__)
    for module in modules:
        module.init_app(app)
    campus_client = Campus()
    app.secret_key = campus_client.vault["campus"]["SECRET_KEY"].get()

    # Health check route for deployments
    @app.route('/')
    def health_check():
        return {'status': 'healthy', 'service': 'campus-apps'}, 200

    return app


def create_app() -> Flask:
    """Create the main Campus app with all modules"""
    return create_app_from_modules(api, campusauth, oauth)


__all__ = [
    "api",
    "campusauth",
    "oauth",
    "create_app_from_modules",
    "create_app",
    "ctx",
]
