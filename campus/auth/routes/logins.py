"""campus.auth.routes.logins

Flask routes for Campus login management.

These routes handle Campus user logins.

Authentication is handled in a global routes.before_request hook.
"""

import contextlib

import flask

import campus.config
import campus.model
from campus import flask_campus
from campus.common import schema
from campus.common.errors import api_errors, token_errors
from campus.common.utils import secret, utc_time

from .. import authz, get_yapper
from ..resources import credentials as creds_resource
from ..resources import login as login_resource
from ..resources import user as user_resource

# Create blueprint for login management routes
bp = flask.Blueprint('logins', __name__, url_prefix='/logins')


def _embed_login_user(loginsession) -> None:
    """Attach the login session's user record for the owning client (#879).

    Same contract as the sessions blueprint's _embed_session_user:
    flask_campus apps hydrate the signed-in user from login-session
    reads instead of the operator-gated users routes; visibility is
    decided by authz.session_user_visible and a missing record
    degrades to a response without the embed.
    """
    if not loginsession.user_id:
        return
    if not authz.session_user_visible(loginsession.client_id):
        return
    with contextlib.suppress(api_errors.NotFoundError):
        loginsession.user = user_resource[loginsession.user_id].get()


@bp.post("/")
@flask_campus.unpack_request
def new(
        *,
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
        client_id=client_id,
        user_id=user_id,
        device_id=device_id,
        agent_string=agent_string,
    )
    get_yapper().emit('campus.logins.new')
    return loginsession.to_resource(), 200


@bp.delete("/<session_id>/")
def delete(session_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Delete a login session.

    DELETE /logins/<session_id>/

    A client-credentials (Basic) caller may revoke any session it owns
    without presenting the auth-service session cookie (#692): that
    cookie lives in the caller's per-process cookie jar, so a
    multi-worker or restarted deployment cannot present the cookie its
    own POST /logins established. Session creation is already scoped to
    the client's credentials, so client-scoped revocation mirrors the
    creation rights.

    A Bearer caller may revoke a session record that attributes to its
    own user (#837): non-browser clients (the CLI) create their login
    session server-side and hold no auth-service cookie, so the
    cookie-synced delete path can never work for them. No new risk —
    the same bearer can already revoke the underlying token outright
    via POST /oauth/revoke. Browser (cookie-carrying) revocation is
    unchanged.
    """
    session = login_resource[session_id].get()
    current_client = getattr(flask.g, "current_client", None)
    current_user = getattr(flask.g, "current_user", None)
    # Bearer auth resolves the user as a dict (#802 glue); Basic callers
    # have no user at all.
    current_user_id = (
        current_user.get("id") if isinstance(current_user, dict)
        else getattr(current_user, "id", None)
    ) if current_user else None
    if (
            current_client is not None
            and current_user is None
            and str(session.client_id) == str(current_client.id)
    ):
        # Owning app client: skip the client-side (cookie) sync.
        login_resource[session_id].delete(sync_client=False)
    elif (
            current_user_id is not None
            and session.user_id is not None
            and str(session.user_id) == str(current_user_id)
    ):
        # Owning user (Bearer): server-side delete only, same reason.
        login_resource[session_id].delete(sync_client=False)
    else:
        login_resource[session_id].delete()
    get_yapper().emit('campus.logins.delete', {"session_id": session_id})
    return {}, 200


@bp.get("/<session_id>/")
def get(session_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Get a login session.

    GET /logins/<session_id>/
    """
    loginsession = login_resource[session_id].get()
    _embed_login_user(loginsession)
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
    get_yapper().emit('campus.logins.update', {"session_id": session_id})
    return loginsession.to_resource(), 200


@bp.post("/<session_id>/token")
def token(session_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Re-acquire the login session user's campus bearer (#963).

    POST /logins/<session_id>/token
    Authorization: Basic (the session-owning confidential client only).

    The session-bound re-acquisition lane (invariant A10,
    docs/auth-token-invariants.md): with_user_session() re-acquires the
    user's campus bearer after a worker restart or token expiry without
    the operator-gated credentials routes (#854) and without re-running
    the browser login. The login session plays the authorization code's
    role, so the issuance semantics mirror the code exchange
    (campus/auth/provider.py::token) with two differences: the grant
    record's scopes are the source of truth (A2 — this route never
    widens; growth requires a fresh browser flow), and the response
    omits the refresh token — campus refresh material never leaves the
    auth service in this lane (B2 philosophy); an expired token is
    rotated server-side, exactly as the refresh grant does.

    A missing credential record is an invalid grant, never minted from
    nothing: revoking the campus token (C5) or deleting the record must
    force re-login, not resurrect the grant under a live session (A5).

    The route serves exactly one principal — the session-owning
    confidential client, the #879 session_user_visible ruling extended
    from user-record visibility to token issuance. User principals are
    denied outright (a user bearer is never the session's client,
    #854 — and bearer auth sets current_client to the minting client,
    which could otherwise pass the ownership check), and the operator
    is denied too: it already holds the credentials management routes,
    keeping this route laser-scoped.

    Errors: 400 invalid_grant (unknown/expired session, no user on the
    session, missing/expired-chain credential), 403 (user principal,
    operator, or non-owning client).
    """
    # Client principals only (A10): user bearers are denied outright,
    # super-admin included — the credentials routes remain the
    # operator/admin path.
    authz.forbid_user_principal(
        "re-acquire campus tokens via a login session (#963/A10)"
    )
    if authz.is_operator():
        raise api_errors.ForbiddenError(
            "The operator principal uses the credentials management "
            "routes (#854); login-session token issuance serves the "
            "session-owning confidential client only (#963/A10)"
        )
    client = getattr(flask.g, "current_client", None)
    if client is None:
        # Unreachable via the Authenticator (every request resolves to
        # a client or user principal); fail closed regardless.
        raise api_errors.ForbiddenError(
            "Login-session token issuance requires a confidential "
            "client principal"
        )
    try:
        loginsession = login_resource[session_id].get()
    except api_errors.NotFoundError:
        raise token_errors.InvalidGrantError(
            "Invalid or expired login session"
        ) from None
    if str(loginsession.client_id) != str(client.id):
        raise api_errors.ForbiddenError(
            "Clients may not re-acquire tokens for another client's "
            "login session; only the session-owning client may "
            "(#963/A10)"
        )
    if loginsession.is_expired():
        raise token_errors.InvalidGrantError(
            "Invalid or expired login session"
        )
    if not loginsession.user_id:
        raise token_errors.InvalidGrantError(
            "Login session has no user; cannot issue a campus token"
        )
    try:
        credentials = creds_resource["campus"][loginsession.user_id].get(
            str(client.id)
        )
    except api_errors.NotFoundError:
        # Revoked or never exchanged: never minted from nothing (C5/A5).
        raise token_errors.InvalidGrantError(
            "No campus grant for this user and client; "
            "re-authentication is required"
        ) from None
    token_record = credentials.token
    if token_record is None:
        # Credential row whose token document is missing (#960 restore
        # case): the grant cannot be honored.
        raise token_errors.InvalidGrantError(
            "No campus grant for this user and client; "
            "re-authentication is required"
        )
    now = schema.DateTime.utcnow()
    if (
        token_record.refresh_token_expires_at is not None
        and token_record.refresh_token_expires_at.to_timestamp() < now.to_timestamp()
    ):
        # Mirror the refresh grant's chain-lifetime check: a credential
        # whose refresh chain has lapsed cannot be re-acquired.
        raise token_errors.InvalidGrantError(
            "The campus grant's refresh chain has expired; "
            "re-authentication is required"
        )
    if token_record.is_expired():
        # Rotate the record server-side, exactly as the refresh grant
        # does: new pair, same granted scopes (A2), supersession is
        # deletion (A5). The new refresh token never leaves this
        # service — the next expired-token call rotates again.
        issued = campus.model.OAuthToken(
            id=secret.generate_access_token(),
            expires_in=(
                campus.config.DEFAULT_TOKEN_EXPIRY_DAYS
                * utc_time.DAY_SECONDS
            ),
            refresh_token=secret.generate_access_code(),
            scopes=token_record.scopes,
        )
        creds_resource["campus"][loginsession.user_id].update(
            client_id=str(client.id),
            token=issued,
        )
    else:
        issued = token_record
    remaining = int(
        (issued.expires_at.to_datetime() - now.to_datetime()).total_seconds()
    )
    get_yapper().emit('campus.oauth.token', {
        "grant_type": "login_session",
        "client_id": str(client.id),
        "user_id": str(loginsession.user_id),
    })
    # Minimal RFC 6749-shaped response (C2 philosophy): deliberately no
    # refresh_token. user_id is echoed like both existing token
    # endpoints (#837), so apps can display login state without a
    # second lookup.
    return {
        "access_token": str(issued.id),
        "token_type": issued.token_type,
        "expires_in": remaining,
        "scope": issued.scope,
        "user_id": str(loginsession.user_id),
    }, 200


def create_blueprint() -> flask.Blueprint:
    """Create a fresh blueprint with routes for test isolation.

    Creates a new blueprint instance and manually registers all route
    functions to support creating multiple independent Flask apps.
    """
    new_bp = flask.Blueprint('logins', __name__, url_prefix='/logins')

    # Manually register routes (mimicking the decorator behavior)
    new_bp.add_url_rule("/", "new", new, methods=["POST"])
    new_bp.add_url_rule("/<session_id>/", "delete", delete, methods=["DELETE"])
    new_bp.add_url_rule("/<session_id>/", "get", get, methods=["GET"])
    new_bp.add_url_rule("/<session_id>/", "update", update, methods=["PATCH"])
    new_bp.add_url_rule("/<session_id>/token", "token", token, methods=["POST"])

    return new_bp
