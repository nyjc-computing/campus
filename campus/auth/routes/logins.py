"""campus.auth.routes.logins

Flask routes for Campus login management.

These routes handle Campus user logins.

Authentication is handled in a global routes.before_request hook.
"""

import flask

from campus.common import flask_campus, schema
import campus.yapper

from ..resources import login as login_resource

# Create blueprint for login management routes
bp = flask.Blueprint('logins', __name__, url_prefix='/logins')

# Lazy-loaded yapper instance to avoid circular dependencies
_yapper_instance = None


def get_yapper():
    """Get yapper instance, creating it lazily to avoid circular
    dependencies."""
    global _yapper_instance
    if _yapper_instance is None:
        _yapper_instance = campus.yapper.create()
    return _yapper_instance


@bp.post("/")
def new(
        *,
        expiry_seconds: int,
        client_id: schema.CampusID,
        user_id: schema.UserID,
        device_id: str | None = None,
        agent_string: str,
) -> flask_campus.JsonResponse:
    """Get a session for a specific authentication provider by
    authorization code.

    POST /sessions/{provider}/
    Body: {
        "code": "authorization_code"
    }
    Returns: {
        "session_token": "session_token",
        "expires_at": "2024-01-01T00:00:00Z",
        ...
    }
    """
    loginsession = login_resource.new(
        expiry_seconds=expiry_seconds,
        client_id=client_id,
        user_id=user_id,
        device_id=device_id,
        agent_string=agent_string,
    )
    get_yapper().emit(
        'campus.logins.new',
        {
            "id": str(loginsession.id),
            "client_id": str(client_id),
            "user_id": str(user_id),
            "device_id": device_id,
        }
    )
    return loginsession.to_resource(), 200


@bp.delete("/<session_id>/")
def delete(session_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Delete a login session.

    DELETE /logins/<session_id>/
    """
    login_resource[session_id].delete()
    get_yapper().emit('campus.logins.delete', {"id": str(session_id)})
    return {}, 200


@bp.get("/<session_id>/")
def get(session_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Get a login session.

    GET /logins/<session_id>/
    """
    loginsession = login_resource[session_id].get()
    return loginsession.to_resource(), 200


@bp.patch("/<session_id>/")
@flask_campus.unpack_request
def update(
        session_id: schema.CampusID,
        expiry_seconds: int
) -> flask_campus.JsonResponse:
    """Update a login session.

    PATCH /logins/<session_id>/
    Body: {
        "expiry_seconds": 3600
    }
    """
    loginsession = login_resource[session_id].update(
        expiry_seconds=expiry_seconds
    )
    get_yapper().emit(
        'campus.logins.update',
        {"id": str(session_id), "expiry_seconds": expiry_seconds}
    )
    return loginsession.to_resource(), 200
