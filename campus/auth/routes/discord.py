"""campus.auth.routes.discord

Routes for Discord OAuth2 Client Credentials flow.

Reference: https://discord.com/developers/docs/topics/oauth2

Discord OAuth 2.0 Client Credentials Flow:

+--------+        (A)        +---------+ 
|        |------------------>| Discord |
| Campus |   Token Request    |         | 
| Server |   (Basic Auth)    +---------+ 
|        |        (B)        +---------+
|        |<------------------|         |
|        |   Access Token    | Campus  |
|        |                   | Backend |
+--------+                   +---------+

Legend:
(A) Campus server requests an app token using client credentials
    - Uses Basic Auth with client_id:client_secret
    - Requests application-level scopes only
(B) Discord returns an access token for the application
    - Token can be used for Discord API calls
    - No user context, application-level access only

This flow is suitable for server-to-server authentication where no user
interaction is required.
"""

import flask
import werkzeug

from campus.client.vault import get_vault
import campus.integrations as integrations
from campus.common import schema
from campus.common.errors import auth_errors, token_errors
from campus.common.validation import flask as flask_validation
from campus.models import session, token, webauth

PROVIDER = "discord"

tokens = token.Tokens()

auth_sessions = session.AuthSessions(PROVIDER)
vault = get_vault()[PROVIDER]
bp = flask.Blueprint(PROVIDER, __name__, url_prefix=f"/{PROVIDER}")
oauth2 = webauth.oauth2.OAuth2FlowScheme.from_config(
    provider=PROVIDER,
    config=integrations.get_config(PROVIDER),
)


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise Discord OAuth routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.get("/authorize")
def authorize(target: schema.Url) -> werkzeug.Response:
    """Prepares the Discord OAuth authorization URL and redirects to it."""
    redirect_uri = flask.url_for('.callback', _external=True)
    oauth2.init_session(
        redirect_uri=redirect_uri,
        client_id=vault["CLIENT_ID"].get()['value'],
        scopes=oauth2.scopes,
        target=target
    )
    authorization_url = oauth2.get_authorization_url()
    return flask.redirect(authorization_url)


@bp.get("/callback")
def callback() -> werkzeug.Response:
    """Handles the Discord OAuth callback request.

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
    """Handle a Discord OAuth callback request."""
    oauth2.validate_callback(state)
    client_secret = vault["CLIENT_SECRET"].get()["value"]

    # Retrieve access token from Discord
    token = oauth2.exchange_code_for_token(
        code=code,
        client_secret=client_secret,
        redirect_uri=auth_session.redirect_uri
    )
    # user_id is needed to store creds
    user_info = oauth2.get_user_info(token.access_token)
    if "error" in user_info:
        raise token_errors.raise_from_error(
            error=user_info["error"],
            error_description=user_info.get(
                "error_description", "Unknown error retrieving user info."
            )
        )
    token = tokens.new(
        client_id=vault["CLIENT_ID"].get()["value"],
        user_id=user_info["id"],
        scopes=token.scopes,
        expiry_seconds=token.expires_in
    )
    assert token.access_token  # for static checkers

    # Verify requested scopes were granted
    if missing_scopes := token.validate_scope(auth_session.scopes):
        raise auth_errors.InvalidScopeError(
            f"Missing scopes: {', '.join(missing_scopes)}"
        )
    # Store token
    tokens.store(token)
    target = oauth2.auth_session.target
    oauth2.end_session()
    return flask.redirect(target or flask.request.host_url)
