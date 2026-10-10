"""campus.auth.routes.sessions

Flask routes for session management.

These routes handle sessions.

Authentication is handled in a global routes.before_request hook.
"""

import contextlib

import flask

import campus.config
from campus import flask_campus
from campus.common import schema
from campus.common.errors import api_errors

from .. import authz, get_yapper, scopes
from ..resources import client as client_resource
from ..resources import session as session_resource
from ..resources import user as user_resource

# Create blueprint for session management routes
bp = flask.Blueprint('sessions', __name__, url_prefix='/sessions')


def _embed_session_user(authsession) -> None:
    """Attach the session user's record for the owning client (#879).

    flask_campus apps hydrate the signed-in user from session reads
    and finalization instead of the operator-gated users routes. The
    resources are ungated for in-process callers by design; the
    visibility decision is made here via authz.session_user_visible.
    A missing user record mid-flow degrades to a response without the
    embed rather than failing the session read.
    """
    if not authsession.user_id:
        return
    if not authz.session_user_visible(authsession.client_id):
        return
    with contextlib.suppress(api_errors.NotFoundError):
        authsession.user = user_resource[authsession.user_id].get()


def _validated_campus_scopes(
        client_id: schema.CampusID,
        scopes_value: list[str] | None,
) -> list[str]:
    """Validate requested scopes against the client's allowlist.

    Applies to Campus-provider sessions only: proxy-provider sessions
    carry the upstream provider's scope strings, which are validated
    by the proxy flows instead. Fail-closed per invariant A1/A6
    (docs/auth-token-invariants.md): the authenticated session-creation
    boundary is where an allowlisted client's scope request is first
    enforced.

    Raises:
        api_errors.NotFoundError: If the client does not exist.
        auth_errors.InvalidScopeError: If any scope is outside the
            client's allowed_scopes.
    """
    client = client_resource[client_id].get()
    return scopes.validate_for_client(
        client.allowed_scopes,
        scopes_value,
    )


@bp.post("/sweep")
@flask_campus.unpack_request
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
@flask_campus.unpack_request
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


@bp.post("/<provider>/")
@flask_campus.unpack_request
def new_provider_session(
        *,
        provider: str,
        client_id: schema.CampusID,
        # expiry_seconds: int,
        user_id: schema.UserID | None = None,
        redirect_uri: schema.Url,
        scopes: list[str] | None = None,
        authorization_code: str | None = None,
        state: str | None = None,
        target: schema.Url | None = None,
) -> flask_campus.JsonResponse:
    """Create a new session for a specific authentication provider.

    For provider="campus", requested scopes are validated fail-closed
    against the client's allowed_scopes allowlist (invariant A1/A6,
    docs/auth-token-invariants.md).

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
    expiry_seconds = campus.config.DEFAULT_OAUTH_EXPIRY_MINUTES * 60
    validated_scopes = (
        _validated_campus_scopes(client_id, scopes)
        if provider == "campus"
        else scopes or []
    )
    authsession = session_resource[provider].new(
        expiry_seconds=expiry_seconds,
        client_id=client_id,
        user_id=user_id,
        redirect_uri=redirect_uri,
        scopes=validated_scopes,
        authorization_code=authorization_code,
        state=state,
        target=target
    )
    get_yapper().emit('campus.sessions.new', {"provider": provider})
    return authsession.to_resource(), 200


@bp.delete("/<provider>/<session_id>/")
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
    session = session_resource[provider][session_id]
    authsession = session.get()
    _embed_session_user(authsession)
    target = session.finalize()
    get_yapper().emit(
        'campus.sessions.finalize',
        {
            "provider": provider,
            "session_id": str(session_id)
        }
    )
    return authsession.to_resource() | {"target": target}, 200


@bp.get("/<provider>/<session_id>/")
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
    _embed_session_user(authsession)
    get_yapper().emit(
        'campus.sessions.get',
        {
            "provider": provider,
            "session_id": str(session_id)
        }
    )
    return authsession.to_resource(), 200


@bp.patch("/<provider>/<session_id>/")
@flask_campus.unpack_request
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
        updates["user_id"] = user_id
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


def create_blueprint() -> flask.Blueprint:
    """Create a fresh blueprint with routes for test isolation.

    Creates a new blueprint instance and manually registers all route
    functions to support creating multiple independent Flask apps.
    """
    new_bp = flask.Blueprint('sessions', __name__, url_prefix='/sessions')

    # Manually register routes (mimicking the decorator behavior)
    new_bp.add_url_rule("/sweep", "sweep", sweep, methods=["POST"])
    new_bp.add_url_rule(
        "/<provider>/authorization_code", "get_by_authorization_code",
        get_by_authorization_code, methods=["POST"]
    )
    new_bp.add_url_rule("/<provider>/", "new_provider_session", new_provider_session, methods=["POST"])
    new_bp.add_url_rule(
        "/<provider>/<session_id>/", "delete_provider_session",
        delete_provider_session, methods=["DELETE"]
    )
    new_bp.add_url_rule("/<provider>/<session_id>/", "get_provider_session", get_provider_session, methods=["GET"])
    new_bp.add_url_rule(
        "/<provider>/<session_id>/", "update_provider_session",
        update_provider_session, methods=["PATCH"]
    )

    return new_bp
