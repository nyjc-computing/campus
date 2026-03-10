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

import flask

from campus.common import webauth
from campus.common.errors import auth_errors

from .. import resources
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


def authenticate() -> tuple[dict[str, str], int] | None:
    """Authenticate the client credentials using HTTP Basic/Bearer
    Authentication.

    This function is used only in campus.auth; it accesses resources
    directly to avoid a circular dependency with campus-api-python.

    This function is meant to be used with Flask.before_request
    to enforce authentication for all routes in the blueprint.

    Any return value from this function will be treated as a response
    to the client, and the request will not be processed further.

    See https://flask.palletsprojects.com/en/stable/api/#flask.Flask.before_request
    """
    req_header = dict(flask.request.headers)
    httpauth = (
        webauth.http.HttpAuthenticationScheme
        .with_header(provider="campus", http_header=req_header)
    )
    assert httpauth.header
    if not httpauth.header.authorization:
        raise auth_errors.InvalidRequestError(
            "Missing Authorization property in HTTP header"
        )
    match httpauth.scheme:
        case "basic":
            client_id, client_secret = (
                httpauth.header.authorization.credentials()
            )
            # Raises auth errors if auth fails
            resources.client.raise_for_authentication(
                client_id, client_secret)  # type: ignore[arg-type]
            flask.g.current_client = resources.client[client_id].get()  # type: ignore[index]
        case "bearer":
            access_token = httpauth.header.authorization.token
            # TODO: Support ClientCredentials
            credentials = resources.credentials["campus"].get(
                token_id=access_token
            )
            flask.g.current_client = (
                resources.client[credentials.client_id].get()  # type: ignore[index]
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
        blueprint.before_request(authenticate)
        app.register_blueprint(blueprint)

    # Register OAuth blueprint WITHOUT authentication
    # These routes are publicly accessible for device authorization
    oauth_blueprint = oauth.create_blueprint()
    app.register_blueprint(oauth_blueprint)
