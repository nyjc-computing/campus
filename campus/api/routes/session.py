"""campus.apps.api.routes.session

Session routes for Campus API.
These routes are used by clients to facilitate login sessions.
"""

import flask

from campus.common import flask as campus_flask, schema

bp = flask.Blueprint("session", __name__, url_prefix="/session")


def init_app(app: flask.Blueprint | flask.Flask) -> None:
    """Register the session blueprint with the given Flask app or
    blueprint.
    """
    app.register_blueprint(bp)


@bp.get("/authorization_url")
@campus_flask.unpack_request
def authorization_url(
        client_id: str,
        redirect_uri: str | None = None,
        scope: str | None = None,
        state: str | None = None,
):
    """Return the authorization URL for the OAuth flow."""
    return flask.jsonify(flask.url_for(
        'campus.auth.authorize',
        _external=True,
        client_id=client_id,
        response_type="code",
        redirect_uri=redirect_uri or flask.request.host_url,
        scope=scope or "profile email",  # TODO: change to Campus scopes
        state=state,
    ))


@bp.get("/<session_id>")
def get_session(session_id: str):
    """Get the current user's session."""
    from campus.api import resources

    session = resources.session[schema.CampusID(session_id)].get()
    if not session:
        return {"error": "Session not found."}, 404
    return session.to_resource()


@bp.post("/<session_id>/revoke")
def revoke(session_id: str):
    """Revoke the user's login session."""
    from campus.api import resources

    resources.session[schema.CampusID(session_id)].delete()
    return {"status": "ok", "message": "Session revoked."}
