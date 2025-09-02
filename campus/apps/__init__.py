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
    """Initialize the Campus app with all modules.

    This function sets up all Campus apps components including API,
    authentication, and OAuth modules.

    Note: For creating new Flask applications, use the recommended pattern:
        from campus.common.devops.deploy import create_app
        import campus.apps
        app = create_app(campus.apps)

    This ensures proper error handling and deployment configuration.
    """
    api.init_app(app)
    campusauth.init_app(app)
    oauth.init_app(app)
    # Use vault client to retrieve secret key since campus.apps deployment
    # does not have VAULTDB_URI env var
    if isinstance(app, Flask):
        from campus.client.vault import get_vault
        vault = get_vault()
        app.secret_key = vault["campus"]["SECRET_KEY"].get()["value"]


__all__ = [
    "api",
    "campusauth",
    "oauth",
    "init_app",
]
