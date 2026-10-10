"""campus.auth.routes.logins

Flask routes for Campus login management.

These routes handle Campus user logins.

Authentication is handled in a global routes.before_request hook.
"""

import contextlib

import flask

from campus import flask_campus
from campus.common import schema
from campus.common.errors import api_errors

from .. import authz, get_yapper
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

    return new_bp
