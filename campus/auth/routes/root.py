"""campus.auth.routes.root

Flask routes for Campus root actions.

WARNING: This module contains routes that should be used only by Campus
backend services (e.g. campus.api), not by other clients.

All access must be carefully authenticated and authorized.
"""

import flask

from campus.common import flask as campus_flask, schema
from campus.common.errors import api_errors
import campus.yapper

import campus_python

from ..resources import (
    client as client_resource,
    credentials as creds_resource,
    user as user_resource,
)

# Create blueprint for session management routes
bp = flask.Blueprint('root', __name__, url_prefix='/root')

# Lazy-loaded yapper instance to avoid circular dependencies
_yapper_instance = None

campus_auth = campus_python.Campus().auth


def get_yapper():
    """Get yapper instance, creating it lazily to avoid circular
    dependencies."""
    global _yapper_instance
    if _yapper_instance is None:
        _yapper_instance = campus.yapper.create()
    return _yapper_instance


@bp.post("/authenticate")
@campus_flask.unpack_request
def authenticate(
        *,
        token: str | None = None,
        client_id: schema.CampusID | None = None,
        client_secret: str | None = None,
) -> campus_flask.JsonResponse:
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
        return authenticate_token(token)
    elif client_id and client_secret:
        return authenticate_credentials(client_id, client_secret)
    else:
        return {
            "error": "Missing authentication credentials."
        }, 400

def authenticate_credentials(
        client_id: schema.CampusID,
        client_secret: str
) -> campus_flask.JsonResponse:
    """Authenticate using client credentials."""
    if client_resource.is_valid_credentials(client_id, client_secret):
        resp_json = {
            "client": client_resource[client_id].get().to_resource(),
        }
        status_code = 200
    else:
        resp_json = {
            "error": "Invalid client credentials."
        }
        status_code = 401
    get_yapper().emit(
        "campus.root.authenticate",
        {
            "client_id": client_id,
            "status_code": status_code,
        }
    )
    return resp_json, status_code


def authenticate_token(token: str) -> campus_flask.JsonResponse:
    """Authenticate using a token."""
    try:
        user_creds = creds_resource["campus"].get(token)
    except api_errors.NotFoundError as err:
        resp_json = {
            "error": str(err)
        }
        status_code = 401
    else:
        resp_json = {
            "client": client_resource[user_creds.client_id].get().to_resource(),
            "user": user_resource[user_creds.user_id].get().to_resource(),
        }
        status_code = 200
    yapper = get_yapper().emit(
        "campus.root.authenticate",
        {
            "token_id": token,
            "status_code": status_code,
        }
    )
    return resp_json, status_code
