"""campus.auth.routes.credentials

Flask routes for credentials management.

Authentication is handled in a global routes.before_request hook.
"""

import flask

from campus.common import flask_campus, schema
import campus.model
from .. import get_yapper

from ..resources import credentials as creds_resource

# Create blueprint for session management routes
bp = flask.Blueprint('credentials', __name__, url_prefix='/credentials')


@bp.get("/<provider>/")
@flask_campus.unpack_request
def get_by_token(
        *,
        provider: str,
        token_id: str | None = None,
) -> flask_campus.JsonResponse:
    """Get credentials for a specific token, or list all credentials for
    a provider.

    GET /credentials/{provider}
    Query Params: {
        "token_id": token_id (optional)
    }
    Returns: {
        "credentials": { ... }
    }
    """
    if token_id:
        credentials = creds_resource[provider].get(token_id)
        return credentials.to_resource(), 200
    else:
        # list all
        credentials_list = creds_resource[provider].list_all()
        return {
            "credentials": [
                cred.to_resource() for cred in credentials_list
            ]
        }, 200


@bp.delete("/<provider>/<user_id>")
@flask_campus.unpack_request
def delete_by_user(
        provider: str,
        user_id: schema.UserID,
) -> flask_campus.JsonResponse:
    """Delete credentials for a specific provider and user ID.

    DELETE /credentials/{provider}/{user_id}
    Returns: {
        "success": true
    }
    """
    client_id = flask.g.current_client.id
    creds_resource[provider][user_id].delete(client_id)
    return {}, 200


@bp.get("/<provider>/<user_id>")
@flask_campus.unpack_request
def get_by_user(
        provider: str,
        user_id: schema.UserID,
) -> flask_campus.JsonResponse:
    """Get credentials for a specific provider and user ID.

    GET /credentials/{provider}/{user_id}
    Query Params: {
        "token_id": "optional_token_id"
    }
    Returns: {
        "credentials": { ... }
    }
    """
    client_id = flask.g.current_client.id
    credentials = creds_resource[provider][user_id].get(client_id)
    return credentials.to_resource(), 200


@bp.patch("/<provider>/<user_id>")
@flask_campus.unpack_request
def update_credentials(
        provider: str,
        user_id: schema.UserID,
        token: campus.model.OAuthToken,
) -> flask_campus.JsonResponse:
    """Update credentials for a specific provider and user ID.

    PATCH /credentials/{provider}/{user_id}
    Body: {
        "client_id": "client_id",
        "token": { ... }
    }
    Returns: {}
    """
    client_id = flask.g.current_client.id
    creds_resource[provider][user_id].update(
        client_id,
        token
    )
    return {}, 200


@bp.post("/<provider>/<user_id>")
@flask_campus.unpack_request
def new_credentials(
        provider: str,
        user_id: schema.UserID,
        scopes: list[str],
        expiry_seconds: int,
) -> flask_campus.JsonResponse:
    """Issue new credentials for a specific provider and user ID.

    POST /credentials/{provider}/{user_id}
    Body: {
        "client_id": "client_id"
    }
    Returns: {
        "credentials": { ... }
    }
    """
    client_id = flask.g.current_client.id
    credentials = creds_resource[provider][user_id].new(
        client_id=client_id,
        scopes=scopes,
        expiry_seconds=expiry_seconds
    )
    return credentials.to_resource(), 201
