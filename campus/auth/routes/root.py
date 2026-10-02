"""campus.auth.routes.root

Flask routes for Campus root actions.

WARNING: This module contains routes that should be used only by Campus
backend services (e.g. campus.api), not by other clients.

All access must be carefully authenticated and authorized.
"""

import flask

from campus import flask_campus
from campus.common import schema
from campus.common.errors import api_errors
from campus.common.errors.base import ErrorConstant

from .. import get_yapper
from ..resources import (
    app_credentials,
)
from ..resources import (
    client as client_resource,
)
from ..resources import (
    credentials as creds_resource,
)
from ..resources import (
    user as user_resource,
)

# Create blueprint for session management routes
bp = flask.Blueprint('root', __name__, url_prefix='/root')


@bp.post("/")
@flask_campus.unpack_request
def authenticate(
        *,
        token: str | None = None,
        client_id: schema.CampusID | None = None,
        client_secret: str | None = None,
) -> flask_campus.JsonResponse:
    """Authenticate a service client using token or client credentials.

    GET /root/authenticate
    Query Params: {
        "token": token (optional),
    } or {
        "client_id": client_id (optional),
        "client_secret": client_secret (optional)
    }
    Returns: {
        "client": { ... }
    } or {
        "client": { ... },
        "user": { ... }
    }
    """
    if token:
        result = authenticate_token(token)
    elif client_id and client_secret:
        result = authenticate_credentials(client_id, client_secret)
    else:
        raise api_errors.InvalidRequestError(
            "Missing authentication credentials.",
            error_code=ErrorConstant.AUTH_INVALID_REQUEST,
        )
    get_yapper().emit('campus.root.authenticate')
    return result


def authenticate_credentials(
        client_id: schema.CampusID,
        client_secret: str
) -> flask_campus.JsonResponse:
    """Authenticate using client credentials."""
    if not client_resource.is_valid_credentials(client_id, client_secret):
        raise api_errors.UnauthorizedError(
            "Invalid client credentials.",
            error_code=ErrorConstant.AUTH_INVALID_CLIENT,
        )
    return {
        "client": client_resource[client_id].get().to_resource(),
    }, 200


def authenticate_token(token: str) -> flask_campus.JsonResponse:
    """Authenticate using a token.

    Tries user credentials first; a miss falls through to app
    credentials (client_credentials grant), which resolve to the
    client with no user.
    """
    try:
        user_creds = creds_resource["campus"].get(token)
    except api_errors.NotFoundError:
        return authenticate_app_token(token)
    return {
        "client": client_resource[user_creds.client_id].get().to_resource(),  # type: ignore[index]
        "user": user_resource[user_creds.user_id].get().to_resource(),
    }, 200


def authenticate_app_token(token: str) -> flask_campus.JsonResponse:
    """Authenticate an app (client-scoped) token.

    App tokens come from the client_credentials grant (RFC 6749
    section 4.4): the confidential client is the resource owner, so
    the result carries the client only — callers must treat a missing
    "user" key as an app-scoped session.
    """
    try:
        app_creds = app_credentials.get(token)
    except api_errors.NotFoundError as err:
        raise api_errors.UnauthorizedError(
            str(err),
            error_code=ErrorConstant.AUTH_TOKEN_INVALID,
        ) from None
    return {
        "client": client_resource[app_creds.client_id].get().to_resource(),  # type: ignore[index]
    }, 200


def create_blueprint() -> flask.Blueprint:
    """Create a fresh blueprint with routes for test isolation.

    Creates a new blueprint instance and manually registers all route
    functions to support creating multiple independent Flask apps.
    """
    new_bp = flask.Blueprint('root', __name__, url_prefix='/root')

    # Manually register routes (mimicking the decorator behavior)
    new_bp.add_url_rule("/", "authenticate", authenticate, methods=["POST"])

    return new_bp
