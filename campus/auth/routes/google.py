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

import flask
import werkzeug

from campus.client.vault import get_vault
import campus.integrations as integrations
from campus.common import schema
from campus.common.errors import auth_errors, token_errors
from campus.common.validation import flask as flask_validation
from campus.models import session, token, webauth

PROVIDER = 'google'

tokens = token.Tokens()

auth_sessions = session.AuthSessions(PROVIDER)
vault = get_vault()[PROVIDER]
bp = flask.Blueprint(PROVIDER, __name__, url_prefix=f'/{PROVIDER}')
oauth2 = webauth.oauth2.OAuth2FlowScheme.from_config(
    provider=PROVIDER,
    config=integrations.get_config(PROVIDER),
)


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise auth routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.get('/authorize')
@flask_validation.unpack_request
def authorize(
        target: schema.Url,
        login_hint: schema.Email | None = None
) -> werkzeug.Response:
    """Prepares the Google OAuth authorization URL and redirects to it."""
    # Requests to this endpoint are internal and should be strictly
    # validated.
    # Transform codespace URL
    # target = url.create_url(
    #     protocol="https",
    #     domain=env.HOSTNAME,
    #     path=target
    # )
    redirect_uri = flask.url_for('.callback', _external=True)
    oauth2.init_session(
        redirect_uri=redirect_uri,
        user_id=login_hint,
        client_id=vault["CLIENT_ID"].get()["value"],
        scopes=oauth2.scopes,
        target=target
    )
    authorization_url = oauth2.get_authorization_url()
    return flask.redirect(authorization_url)


@bp.get('/callback')
def callback() -> werkzeug.Response:
    """Handles the Google OAuth callback request.

    Dispatches to success or error handlers based on payload type.
    """
    callback_payload = flask_validation.get_request_payload()
    if "error" in callback_payload:
        auth_errors.raise_from_json(callback_payload)
    else:
        return flask_validation.unpack_into(success_callback,
                                            **callback_payload)


def success_callback(
        state: str,
        code: str,  # on success
        scope: str,  # on success
        authuser: str,  # on success
        hd: str,  # on success
        prompt: str  # on success
) -> werkzeug.Response:
    """Handle a Google OAuth callback request."""
    oauth2.validate_callback(state)
    client_secret = vault["CLIENT_SECRET"].get()["value"]

    # Retrieve access token from Google
    token = oauth2.exchange_code_for_token(
        code=code,
        client_secret=client_secret,
        redirect_uri=auth_session.redirect_uri,
    )
    # user_id is needed to store creds
    user_info = oauth2.get_user_info(token.access_token)
    if "error" in user_info:
        raise token_errors.raise_from_error(
            error=user_info["error"],
            error_description=user_info.get("error_description", ""),
            error_uri=user_info.get("error_uri")
        )
    token = tokens.new(
        client_id=vault["CLIENT_ID"].get()["value"],
        user_id=user_info["email"],
        scopes=token.scopes,
        expiry_seconds=token.expires_in
    )
    assert token.access_token  # for static checkers

    # Verify requested scopes were granted
    if missing_scopes := token.validate_scope(oauth2.auth_session.scopes):
        raise auth_errors.InvalidScopeError(
            f"Missing required scopes: {', '.join(missing_scopes)}"
        )
    target = oauth2.auth_session.target
    oauth2.end_session()
    return flask.redirect(target or flask.request.host_url)
