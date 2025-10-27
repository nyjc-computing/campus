"""campus.apps.api.routes.session

Session routes for Campus API.
These routes are used by clients to facilitate login sessions.
"""

from flask import Blueprint, Flask
import flask

from campus.common.validation import flask as flask_validation
from campus.models import session

bp = Blueprint("session", __name__, url_prefix="/session")
sessions = session.LoginSessions()


def init_app(app: Blueprint | Flask) -> None:
    """Register the session blueprint with the given Flask app or
    blueprint.
    """
    app.register_blueprint(bp)


@bp.get("/authorization_url")
@flask_validation.unpack_request
def authorization_url(
        client_id: str,
        redirect_uri: str | None = None,
        scope: str | None = None,
        state: str | None = None,
):
    """Return the authorization URL for the OAuth flow."""
    return flask.jsonify(flask.url_for(
        'campusauth.authorize',
        _external=True,
        client_id=client_id,
        response_type="code",
        redirect_uri=redirect_uri or flask.request.host_url,
        scope=scope or "profile email",
        state=state,
    ))


@bp.get("/<session_id>")
def get_session(session_id: str):
    """Get the current user's session."""
    session = sessions.get_by_id(session_id)
    if not session:
        return {"error": "Session not found."}, 404
    return session.to_dict()


@bp.post("/<session_id>/revoke")
def revoke(session_id: str):
    """Revoke the user's login session."""
    sessions.delete(session_id)
    return {"status": "ok", "message": "Session revoked."}
