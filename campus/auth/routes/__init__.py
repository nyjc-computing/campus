"""campus.auth.routes

Flask blueprint modules for the auth service.

This package contains all HTTP route definitions organized by functionality:
- vault.py: Secret management operations (/vault/*)
- client.py: Client management operations (/client/*)

Each module defines route functions that can be attached to blueprints
dynamically. This allows creating fresh blueprints for test isolation.
"""

__all__ = [
    "clients",
    "credentials",
    "logins",
    "oauth",
    "sessions",
    "users",
    "vaults",
]

from typing import Any

import flask

from campus.common import schema

from .. import resources
from ..middleware import Authenticator
from . import clients, credentials, logins, oauth, root, sessions, users, vaults

# Route modules that require authentication
_AUTHENTICATED_ROUTE_MODULES = [
    clients,
    credentials,
    logins,
    root,
    sessions,
    users,
    vaults,
]

def basic_authenticate(client_id: str, client_secret: str) -> dict[str, Any]:
    """Authenticate using HTTP Basic Authentication."""
    resources.client.raise_for_authentication(
        schema.CampusID(client_id),
        client_secret
    )
    return {
        "client": resources.client[schema.CampusID(client_id)].get()
    }

def bearer_authenticate(token: str) -> dict[str, Any]:
    """Authenticate using HTTP Bearer Authentication."""
    credentials = resources.credentials["campus"].get(token_id=token)
    return {
        "client": resources.client[schema.CampusID(credentials.client_id)].get()
    }

# campus.auth authenticates directly from campus.auth.resources to avoid
# circular dependency with campus-api-python
# This is meant to be used with Flask.before_request to enforce authentication
# for all routes in the blueprint
# See https://flask.palletsprojects.com/en/stable/api/#flask.Flask.before_request
resource_authenticator = Authenticator(
    basic_authenticator=basic_authenticate,
    bearer_authenticator=bearer_authenticate
)


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialize the auth routes with the given Flask app or blueprint.

    Creates fresh blueprints each time to support test isolation.
    Authentication is applied to each blueprint individually to avoid
    affecting OAuth proxy routes which should be publicly accessible.

    Note: OAuth routes are registered WITHOUT authentication as they are
    publicly accessible for the device authorization flow.
    """
    for module in _AUTHENTICATED_ROUTE_MODULES:
        blueprint = module.create_blueprint()
        blueprint.before_request(resource_authenticator.authenticate)
        app.register_blueprint(blueprint)

    # Register OAuth blueprint WITHOUT authentication
    # These routes are publicly accessible for device authorization
    oauth_blueprint = oauth.create_blueprint()
    app.register_blueprint(oauth_blueprint)
