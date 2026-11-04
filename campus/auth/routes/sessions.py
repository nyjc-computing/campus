"""campus.auth.routes.sessions

Flask routes for session management.

These routes handle sessions.

Authentication is handled in a global routes.before_request hook.
Since #1055 the per-id routes (GET/PATCH/DELETE) are additionally
authorization-gated: the session-owning client and the deployment
operator drive and administer sessions (designated admin users join
via the sessions vocabulary); other principals are denied
(require_session_access). GET /sessions/ is the admin enumeration,
operator/designated-admin only. The creation and code-exchange
routes stay open to any authenticated client — they are the
server-to-server flow boundary every flask_campus app calls with its
own credentials.
"""

import contextlib

import flask

import campus.config
import campus.flask_campus as flask_campus
from campus.common import schema
from campus.common.errors import FieldError, ValidationError, api_errors

from .. import authz, get_yapper, scopes
from ..resources import client as client_resource
from ..resources import session as session_resource
from ..resources import user as user_resource

# Create blueprint for session management routes
bp = flask.Blueprint('sessions', __name__, url_prefix='/sessions')

# The admin metadata view (#1055): what GET /sessions/ and every
# non-owning principal's per-id read may carry. The authorization
# code is a flow secret and journey_id is an internal audit
# correlation id (#803); device_id rides along because it is the
# stable device identity (#825) that audit attribution correlates
# on — observational, not secret.
_SESSION_METADATA_FIELDS = (
    "id",
    "provider",
    "client_id",
    "user_id",
    "created_at",
    "expires_at",
    "redirect_uri",
    "scopes",
    "state",
    "target",
    "device_id",
)


def _is_owning_client(authsession) -> bool:
    """True if the authenticated client principal owns the session.

    User principals are never a session's owning client (#854); the
    super-admin root acts as a user and is metadata-viewed like the
    other non-owning principals.
    """
    if authz.is_user_principal():
        return False
    client = getattr(flask.g, "current_client", None)
    return (
        client is not None
        and str(client.id) == str(authsession.client_id)
    )


def _session_metadata(authsession) -> dict:
    """The admin metadata view of a session record (#1055).

    The field allowlist behind GET /sessions/ and every non-owning
    principal's per-id read: no authorization_code, no journey/device
    correlation ids, no user embed.
    """
    resource = authsession.to_resource()
    return {
        field: resource[field]
        for field in _SESSION_METADATA_FIELDS
        if field in resource
    }


def _session_view(authsession) -> dict:
    """Serialize a session for the current principal (#1055).

    The owning client gets the full flow record — it created the
    session and drives the code exchange, so it sees the
    authorization_code it was minted. Every other authorized
    principal (operator, designated admin) gets metadata only. The
    embedded user (#879) rides the existing visibility decision and
    is attached only when the principal may see it.
    """
    resource = (
        authsession.to_resource()
        if _is_owning_client(authsession)
        else _session_metadata(authsession)
    )
    if authsession.user is not None:
        resource["user"] = authsession.user.to_resource()
    return resource


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
    """Sweep expired sessions

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


@bp.get("/")
@flask_campus.unpack_request
def list_sessions(
        provider: str | None = None,
        client_id: schema.CampusID | None = None,
        user_id: schema.UserID | None = None,
        limit: str | None = None,
        offset: str | None = None,
) -> flask_campus.JsonResponse:
    """List auth sessions (admin view)

    GET /sessions/
    Authorization: the operator, or a designated admin user whose
    grant row and token cover sessions:read (#1055). Client
    principals may not enumerate sessions: the per-id routes stay
    the owning client's flow surface, and #881 keeps client
    principals off administrative enumeration.

    Query Params: {
        "provider": "campus",       # optional filter
        "client_id": "client_...",  # optional filter
        "user_id": "user@...",      # optional filter
        "limit": 100,               # optional page size, 1-500 (default 100)
        "offset": 0                 # optional, default 0
    }
    Returns: {
        "sessions": [ ...session metadata records... ],
        "total": <matching sessions before pagination>
    }

    Records carry metadata only (#1055): no authorization_code and no
    journey correlation id, no user embeds — hydrate users via the
    users routes. Finalized sessions are deleted by the
    DELETE route, so the listing shows live sessions only, newest
    first; expired-but-unswept sessions appear until swept.
    """
    authz.require_operator(
        "list auth sessions", admin_scope=authz.SESSIONS_READ
    )
    try:
        page_size = 100 if limit is None else int(limit)
        page_offset = 0 if offset is None else int(offset)
    except (TypeError, ValueError) as e:
        raise ValidationError(
            "limit and offset must be integers",
            errors=[FieldError(
                field="limit",
                code="INVALID_FORMAT",
                message=str(e)
            )]
        ) from e
    page_size = max(1, min(page_size, 500))
    page_offset = max(0, page_offset)
    sessions = session_resource.list(
        provider=provider,
        client_id=client_id,
        user_id=user_id,
    )
    return {
        "sessions": [
            _session_metadata(authsession) for authsession in sessions
        ][page_offset:page_offset + page_size],
        "total": len(sessions),
    }, 200


@bp.post("/<provider>/authorization_code")
@flask_campus.unpack_request
def get_by_authorization_code(
        *,
        provider: str,
        code: str,
) -> flask_campus.JsonResponse:
    """Look up a session by authorization code

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
    """Create an auth session

    Server-to-server: the app backend creates the session, then
    sends the browser to `GET /authorize` with `state` = the
    session id. For `provider=campus`, requested scopes are
    validated fail-closed against the client's `allowed_scopes`
    (invariant A1/A6); proxy providers carry the upstream
    provider's scope strings instead.

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
    """Finalize an auth session

    This marks the session as finalized after successful authentication.

    DELETE /sessions/{provider}/{session_id}
    Authorization: the session-owning client, the operator, or a
    designated admin user covering sessions:write (#1055); other
    principals are denied — finalizing deletes the session, so an
    unowned DELETE is a revoke of another app's login flow. The
    owning client's delete emits campus.sessions.finalize (flow
    semantics); any other authorized caller emits
    campus.sessions.revoke (admin semantics).

    Returns: {
        "target": <url>
    }
    """
    session = session_resource[provider][session_id]
    authsession = session.get()
    authz.require_session_access(
        authsession.client_id,
        "finalize an auth session",
        admin_scope=authz.SESSIONS_WRITE,
    )
    _embed_session_user(authsession)
    target = session.finalize()
    revoked_by_admin = not _is_owning_client(authsession)
    get_yapper().emit(
        'campus.sessions.revoke' if revoked_by_admin
        else 'campus.sessions.finalize',
        {
            "provider": provider,
            "session_id": str(session_id),
            **({"client_id": str(authsession.client_id)}
               if revoked_by_admin else {}),
        }
    )
    return _session_view(authsession) | {"target": target}, 200


@bp.get("/<provider>/<session_id>/")
def get_provider_session(
        provider: str,
        session_id: schema.CampusID,
) -> flask_campus.JsonResponse:
    """Get an auth session

    GET /sessions/{provider}/{session_id}
    Authorization: the session-owning client, the operator, or a
    designated admin user covering sessions:read (#1055); other
    principals are denied — the record embeds the session user
    (#879) and carries the flow's authorization code. The owning
    client gets the full flow record; every other authorized
    principal gets metadata only.

    Returns: {
        "session_token": "session_token",
        "expires_at": "2024-01-01T00:00:00Z",
        ...
    }
    """
    authsession = session_resource[provider][session_id].get()
    authz.require_session_access(
        authsession.client_id,
        "read an auth session",
        admin_scope=authz.SESSIONS_READ,
    )
    _embed_session_user(authsession)
    get_yapper().emit(
        'campus.sessions.get',
        {
            "provider": provider,
            "session_id": str(session_id)
        }
    )
    return _session_view(authsession), 200


@bp.patch("/<provider>/<session_id>/")
@flask_campus.unpack_request
def update_provider_session(
        provider: str,
        session_id: schema.CampusID,
        user_id: schema.UserID | None = None,
        authorization_code: str | None = None,
) -> flask_campus.JsonResponse:
    """Update an auth session

    Only `user_id` and `authorization_code` can be updated (this is how the login flow binds them).

    Only user_id and authorization_code can be updated.

    PATCH /sessions/{provider}/{session_id}
    Authorization: the session-owning client or the operator
    (#1055); binding user_id/authorization_code onto another app's
    session is a login-flow takeover.

    Returns: {
        "success": true
    }
    """
    authsession = session_resource[provider][session_id].get()
    authz.require_session_access(
        authsession.client_id, "update an auth session"
    )
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
    new_bp.add_url_rule("/", "list_sessions", list_sessions, methods=["GET"])
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
