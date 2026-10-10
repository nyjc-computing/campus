"""campus.auth.routes

Flask blueprint modules for the auth service.

This package contains all HTTP route definitions organized by functionality:
- vault.py: Secret management operations (/vault/*)
- client.py: Client management operations (/client/*)

Each module defines route functions that can be attached to blueprints
dynamically. This allows creating fresh blueprints for test isolation.
"""

__all__ = [
    "broker",
    "clients",
    "connections",
    "credentials",
    "grants",
    "integrations",
    "logins",
    "logout",
    "oauth",
    "sessions",
    "users",
    "vaults",
]

from typing import Any

import flask

from campus.common import schema
from campus.common.errors import api_errors
from campus.common.errors.base import ErrorConstant

from .. import resources
from ..middleware import Authenticator
from . import (
    broker,
    clients,
    connections,
    credentials,
    grants,
    integrations,
    logins,
    logout,
    oauth,
    root,
    sessions,
    users,
    vaults,
)

# Route modules that require authentication
_AUTHENTICATED_ROUTE_MODULES = [
    broker,
    clients,
    connections,
    credentials,
    grants,
    logins,
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
    """Authenticate using HTTP Bearer Authentication.

    User tokens are resolved first; a miss falls through to app
    credentials (client_credentials grant), which resolve to the
    client with no user (#739). This mirrors authenticate_token in
    routes/root.py.
    """
    try:
        credentials = resources.credentials["campus"].get(token_id=token)
    except api_errors.NotFoundError:
        return _authenticate_app_bearer(token)
    try:
        client = resources.client[schema.CampusID(credentials.client_id)].get()
    except api_errors.NotFoundError as err:
        # Unknown and revoked tokens alike are authentication failures:
        # RFC 6750 §3.1 expects 401 invalid_token, not 404 (#729). 404
        # stays reserved for unknown routes and resources.
        raise api_errors.UnauthorizedError(
            str(err),
            error_code=ErrorConstant.AUTH_TOKEN_INVALID,
        ) from None
    token_record = credentials.token
    return {
        "client": client,
        # Bearer authentication carries the user context (the token's
        # owner); basic (client-credentials) auth has none. The token
        # bridge uses this to bind releases to the authenticated user.
        # Scopes ride along for the management-scope gates (#865):
        # authz reads them from this dict, fail-closed (missing token
        # record or no scopes means no management authority).
        "user": {
            "id": str(credentials.user_id),
            "scopes": list(token_record.scopes) if token_record else [],
        },
    }


def _authenticate_app_bearer(token: str) -> dict[str, Any]:
    """Authenticate an app-scoped (client_credentials) bearer token.

    App tokens carry no user identity: the confidential client is the
    resource owner (RFC 6749 §4.4), so the result is the client only.
    """
    try:
        app_credentials = resources.app_credentials.get(token_id=token)
        client = resources.client[schema.CampusID(app_credentials.client_id)].get()
    except api_errors.NotFoundError as err:
        # Unknown and revoked tokens of either kind are authentication
        # failures: RFC 6750 §3.1 expects 401 invalid_token, not 404
        # (#729). 404 stays reserved for unknown routes and resources.
        raise api_errors.UnauthorizedError(
            str(err),
            error_code=ErrorConstant.AUTH_TOKEN_INVALID,
        ) from None
    return {
        "client": client,
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

    # Register root blueprint WITHOUT authentication.
    # /root/authenticate is itself the authentication endpoint: requiring a
    # pre-existing valid credential on it is a chicken-and-egg problem for
    # callers that only hold the credentials they are trying to validate
    # (e.g. campus.api's request middleware). Like the OAuth routes, it only
    # ever confirms the validity of the credentials in the request body (#614).
    root_blueprint = root.create_blueprint()
    app.register_blueprint(root_blueprint)

    # Register the browser-session logout blueprint WITHOUT
    # authentication (#785): the Flask session it clears IS the
    # credential, so there is nothing to authenticate against. Like the
    # OAuth routes it is publicly accessible, and idempotent.
    logout_blueprint = logout.create_blueprint()
    app.register_blueprint(logout_blueprint)
