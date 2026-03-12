"""campus.auth.routes.google

Routes for Google OAuth2.

Reference: https://developers.google.com/identity/protocols/oauth2/web-server

Google OAuth 2.0 Authorization Flow Diagram:

+--------+        (A)        +---------+
|        |------------------>| Google  |
|        |   Auth Request    |         |
|        |                   +---------+
|        |        (B)        +---------+
|        | +-----------------|         |
|  User  | +---------------->|         |     (C)       +-----------+
|        | Redirect w/ Code  | Campus  |---------------|  Google   |
|        |                   | Backend |<--------------|  Token    |
|        |        (D)        |         | Token Request | Endpoint  |
|        |<----------------- |         |               +-----------+
+--------+ Redirect to sess  +---------+
                target

Legend:
(A) User is redirected from Campus to Google for authentication and consent.
    - a server-side session is initialised
    - the session_id is stored client-side
(B) Google redirects the user back to Campus with an authorization code.
(C) Campus backend exchanges the authorization code directly with Google's
    token endpoint for user profile.
(D) Campus redirects user to session target.

Apps and view functions sending the user to this endpoint must first establish
a server-side session with a target.
"""

import logging
from typing import Literal

import flask
import werkzeug

from campus import flask_campus
from campus.common import schema
from campus.common.errors import auth_errors

from . import proxy

logger = logging.getLogger(__name__)

PROMPT_OPTION = Literal["consent", "login", "none", "select_account"]
PROVIDER = 'google'


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise auth routes with the given Flask app/blueprint.

    Creates a fresh blueprint each time to support test isolation.
    """
    bp = flask.Blueprint(PROVIDER, __name__, url_prefix=f'/{PROVIDER}')

    @bp.before_request
    def before_request() -> None:
        flask.g.proxy = proxy.get_proxy()

    @bp.get('/authorize')
    @flask_campus.unpack_request
    def authorize(
            target: schema.Url,
            hd: str | None = "nyjc.edu.sg",
            login_hint: schema.Email | None = None,
            prompt: PROMPT_OPTION | None = None,
    ) -> werkzeug.Response:
        """Prepares the Google OAuth authorization URL and redirects to it.
        """
        return flask.g.proxy.redirect_for_authorization(
            target,
            hd=hd,
            login_hint=login_hint,
            prompt=prompt
        )

    @bp.get('/callback')
    def callback() -> werkzeug.Response:
        """Handles the Google OAuth callback request.

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
        """Handle a Google OAuth callback request."""
        return flask.g.proxy.handle_consent_callback(
            state,
            code,
            scope,
            **kwargs
        )

    app.register_blueprint(bp)
