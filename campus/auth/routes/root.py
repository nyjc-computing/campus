"""campus.auth.routes.root

Flask routes for Campus root actions.

WARNING: This module contains routes that should be used only by Campus
backend services (e.g. campus.api), not by other clients.

All access must be carefully authenticated and authorized.
"""

import campus_python
import flask

from campus import flask_campus
from campus.common import schema
from campus.common.errors import api_errors

from .. import get_yapper
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
        result = {
            "error": "Missing authentication credentials."
        }, 400
    get_yapper().emit('campus.root.authenticate')
    return result


def authenticate_credentials(
        client_id: schema.CampusID,
        client_secret: str
) -> flask_campus.JsonResponse:
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
    return resp_json, status_code


def authenticate_token(token: str) -> flask_campus.JsonResponse:
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
    return resp_json, status_code
