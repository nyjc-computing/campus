"""campus.auth.routes.sessions

Flask routes for session management.

These routes handle sessions.

Authentication is handled in a global routes.before_request hook.
"""

import flask

from campus.common import flask_campus, schema
import campus.config
import campus.yapper

from ..resources import session as session_resource

# Create blueprint for session management routes
bp = flask.Blueprint('sessions', __name__, url_prefix='/sessions')

# Lazy-loaded yapper instance to avoid circular dependencies
_yapper_instance = None


def get_yapper():
    """Get yapper instance, creating it lazily to avoid circular
    dependencies."""
    global _yapper_instance
    if _yapper_instance is None:
        _yapper_instance = campus.yapper.create()
    return _yapper_instance


@bp.post("/sweep")
def sweep(at_time: schema.DateTime | None = None) -> flask_campus.JsonResponse:
    """Sweep expired sessions.

    POST /sessions/sweep
    Body: {
        "at_time": "2024-01-01T00:00:00Z"  # Optional, defaults to now
    }
    Returns: {
        "swept_count": 42
    }
    """
    swept_count = session_resource.sweep(at_time=at_time)
    get_yapper().emit('campus.sessions.sweep')
    return {"swept_count": swept_count}, 200


@bp.post("/<provider>/authorization_code")
def get_by_authorization_code(
        *,
        provider: str,
        code: str,
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
    authsession = session_resource[provider].get(code)
    return authsession.to_resource(), 200


@bp.post("/<provider>")
def new_provider_session(
        *,
        provider: str,
        # expiry_seconds: int,
        user_id: schema.UserID | None = None,
        redirect_uri: schema.Url,
        scopes: list[str] | None = None,
        authorization_code: str | None = None,
        state: str | None = None,
        target: schema.Url | None = None,
) -> flask_campus.JsonResponse:
    """Create a new session for a specific authentication provider.

    POST /sessions/{provider}/
    Body: {
        "expiry_seconds": 3600,
        "user_id": "user_id",
        "redirect_uri": "https://example.com/callback",
        "scopes": ["scope1", "scope2"],
        "authorization_code": "auth_code",
        "state": "state",
        "target": "https://example.com/target"
    }
    Returns: {
        "session_token": "new_session_token",
        "expires_at": "2024-01-01T00:00:00Z"
    }
    """
    client_id = flask.g.current_client.id
    expiry_seconds = campus.config.DEFAULT_OAUTH_EXPIRY_MINUTES * 60
    authsession = session_resource[provider].new(
        expiry_seconds=expiry_seconds,
        client_id=client_id,
        user_id=user_id,
        redirect_uri=redirect_uri,
        scopes=scopes,
        authorization_code=authorization_code,
        state=state,
        target=target
    )
    get_yapper().emit('campus.sessions.new', {"provider": provider})
    return authsession.to_resource(), 200


@bp.delete("/<provider>/<session_id>")
def delete_provider_session(
        provider: str,
        session_id: schema.CampusID,
) -> flask_campus.JsonResponse:
    """Finalize a session for a specific authentication provider.

    This marks the session as finalized after successful authentication.

    DELETE /sessions/{provider}/{session_id}
    Returns: {
        "target": <url>
    }
    """
    target = session_resource[provider][session_id].finalize()
    get_yapper().emit(
        'campus.sessions.finalize',
        {
            "provider": provider,
            "session_id": str(session_id)
        }
    )
    return {"target": target}, 200


@bp.get("/<provider>/<session_id>")
def get_provider_session(
        provider: str,
        session_id: schema.CampusID,
) -> flask_campus.JsonResponse:
    """Get a session for a specific authentication provider.

    GET /sessions/{provider}/{session_id}
    Returns: {
        "session_token": "session_token",
        "expires_at": "2024-01-01T00:00:00Z",
        ...
    }
    """
    authsession = session_resource[provider][session_id].get()
    get_yapper().emit(
        'campus.sessions.get',
        {
            "provider": provider,
            "session_id": str(session_id)
        }
    )
    return authsession.to_resource(), 200


@bp.patch("/<provider>/<session_id>")
def update_provider_session(
        provider: str,
        session_id: schema.CampusID,
        user_id: schema.UserID | None = None,
        authorization_code: str | None = None,
) -> flask_campus.JsonResponse:
    """Update a session for a specific authentication provider.

    Only user_id and authorization_code can be updated.

    PATCH /sessions/{provider}/{session_id}
    Returns: {
        "success": true
    }
    """
    updates = {}
    if user_id is not None:
        updates["user_id"] = str(user_id)
    if authorization_code is not None:
        updates["authorization_code"] = authorization_code
    session_resource[provider][session_id].update(**updates)
    get_yapper().emit(
        'campus.sessions.update',
        {
            "provider": provider,
            "session_id": str(session_id),
            "updates": updates
        }
    )
    return {}, 200
