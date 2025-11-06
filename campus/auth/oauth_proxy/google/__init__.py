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

from typing import Literal

import flask
import werkzeug

from campus.common import flask as campus_flask, schema
from campus.common.errors import auth_errors

from . import proxy

PROMPT_OPTION = Literal["consent", "login", "none", "select_account"]
PROVIDER = 'google'

bp = flask.Blueprint(PROVIDER, __name__, url_prefix=f'/{PROVIDER}')


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise auth routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.before_request
def before_request() -> None:
    flask.g.proxy = proxy.get_proxy()


@bp.get('/authorize')
@campus_flask.unpack_request
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
    callback_payload = campus_flask.get_request_payload()
    if "error" in callback_payload:
        auth_errors.raise_from_json(callback_payload)
    else:
        return campus_flask.unpack_into(success_callback,
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
