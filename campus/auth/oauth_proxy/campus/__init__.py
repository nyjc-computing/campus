"""campus.auth.routes.campus

Routes for Campus OAuth2.

While Campus supports the full OAuth2 flow (e.g. for third-party
clients), first-party clients may use this module so they don't have to
implement server-side storage for session management.
"""

import flask
import werkzeug

from campus import flask_campus
from campus.common import schema
from campus.common.errors import auth_errors

from . import proxy

PROVIDER = 'campus'

bp = flask.Blueprint(PROVIDER, __name__, url_prefix=f'/{PROVIDER}')


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise auth routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.before_request
def before_request() -> None:
    flask.g.proxy = proxy.get_proxy()


@bp.get('/authorize')
@flask_campus.unpack_request
def authorize(
        target: schema.Url,
        state: schema.CampusID,  # auth session ID
        client_id: schema.CampusID | None = None,  # Campus client ID or server
        login_hint: schema.Email | None = None,
) -> werkzeug.Response:
    """Prepares the Campus OAuth authorization URL and redirects to it.
    """
    params = {"state": state}
    if client_id:
        params["client_id"] = client_id
    if login_hint:
        params["login_hint"] = login_hint
    return flask.g.proxy.redirect_for_authorization(target, **params)


@bp.get('/callback')
def callback() -> werkzeug.Response:
    """Handles the Campus OAuth callback request.

    Dispatches to success or error handlers based on payload type.
    """
    callback_payload = flask_campus.get_request_payload()
    if "error" in callback_payload:
        # TODO: For testing - display error instead of redirecting
        # This should be replaced with proper error handling that redirects to target
        error_html = f"""
        <html>
        <head><title>OAuth Error</title></head>
        <body>
            <h1>OAuth Error</h1>
            <p><strong>Error:</strong> {callback_payload.get('error')}</p>
            <p><strong>Description:</strong> {callback_payload.get('error_description', 'N/A')}</p>
            <p><strong>Error URI:</strong> {callback_payload.get('error_uri', 'N/A')}</p>
            <hr>
            <p><strong>All callback parameters:</strong></p>
            <pre>{callback_payload}</pre>
        </body>
        </html>
        """
        return flask.Response(error_html, status=400, mimetype='text/html')
    else:
        return flask_campus.unpack_into(success_callback,
                                        **callback_payload)


def success_callback(
        state: str,
        code: str,
        scope: str,
        **kwargs: str
) -> werkzeug.Response:
    """Campus uses Google SSO for authentication. This function handles
    the Google OAuth callback request for an auth flow.
    """
    return flask.g.proxy.handle_callback(
        state,
        code,
        scope,
        **kwargs
    )
