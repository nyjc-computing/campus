"""campus.apps.oauth.discord

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

from typing import cast

import flask
import werkzeug

from campus.client.vault import get_vault
from campus.common import integration, schema
from campus.common.errors import auth_errors, token_errors
from campus.common.validation import flask as flask_validation
from campus.models import session, webauth
from campus.vault import credentials

PROVIDER = "discord"

discord_credentials = credentials.get_provider(PROVIDER)

auth_sessions = session.AuthSessions(PROVIDER)
vault = get_vault()[PROVIDER]
bp = flask.Blueprint(PROVIDER, __name__, url_prefix=f"/{PROVIDER}")
oauthconfig = integration.get_config(PROVIDER)
oauth2 = webauth.oauth2.OAuth2AuthorizationCodeFlowScheme.from_json(
    config=cast(integration.schema.IntegrationConfigSchema, oauthconfig),
    security="oauth2"
)


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise Discord OAuth routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.get("/authorize")
def authorize(target: schema.Url) -> werkzeug.Response:
    """Prepares the Discord OAuth authorization URL and redirects to it."""
    redirect_uri = flask.url_for('.callback', _external=True)
    auth_session = oauth2.init_session(
        redirect_uri=redirect_uri,
        client_id=vault["CLIENT_ID"].get()['value'],
        scopes=oauth2.scopes,
        target=target
    )
    authorization_url = oauth2.get_authorization_url(redirect_uri)
    return flask.redirect(authorization_url)


@bp.get("/callback")
def callback() -> werkzeug.Response:
    """Handles the Discord OAuth callback request.

    Dispatches to success or error handlers based on payload type.
    """
    callback_payload = flask_validation.get_request_payload()
    if "error" in callback_payload:
        return flask_validation.unpack_into(error_callback,
                                            **callback_payload)
    else:
        return flask_validation.unpack_into(success_callback,
                                            **callback_payload)


def error_callback(
        error: str,
        error_description: str,
        error_uri: str
) -> werkzeug.Response:
    """Handle a Discord OAuth error callback request."""
    auth_errors.raise_from_error(error, error_description)  # type: ignore


def success_callback(
        state: str,
        code: str,  # on success
        scope: str,  # on success
        authuser: str,  # on success
        hd: str,  # on success
        prompt: str  # on success
) -> werkzeug.Response:
    """Handle a Discord OAuth callback request."""
    # Requests to endpoint are from Discord, can be more loosely validated.
    auth_session = oauth2.retrieve_session()
    error_description = None
    if not auth_session:
        error_description = "No active OAuth session found."
    elif auth_session.is_expired():
        error_description = "OAuth session has expired."
    elif auth_session.id != state:
        error_description = "Session state mismatch."
    elif auth_session.redirect_uri is None:
        error_description = "No redirect URI in auth session."
    if error_description:
        raise auth_errors.InvalidRequestError(error_description)
    assert auth_session.redirect_uri
    client_secret = vault["CLIENT_SECRET"].get()["value"]

    # Retrieve access token from Discord
    token_response = oauth2.exchange_code_for_token(
        code=code,
        client_secret=client_secret,
        redirect_uri=auth_session.redirect_uri
    )
    if "error" in token_response:
        raise token_errors.raise_from_error(
            error=token_response["error"],
            error_description=token_response.get(
                "error_description", "Unknown error during token exchange."
            )
        )
    # user_id is needed to store creds
    user_info = oauth2.get_user_info(token_response["access_token"])
    if "error" in user_info:
        raise token_errors.raise_from_error(
            error=user_info["error"],
            error_description=user_info.get(
                "error_description", "Unknown error retrieving user info."
            )
        )
    token = discord_credentials.create_credentials(
        expiry_seconds=token_response["expires_in"],
        access_token=token_response["access_token"],
        refresh_token=token_response.get("refresh_token"),
        scopes=token_response["scope"].split(" "),
        client_id=vault["CLIENT_ID"].get()["value"],
        user_id=user_info["id"]
    )
    assert token.access_token  # for static checkers

    # Verify requested scopes were granted
    if missing_scopes := token.get_missing_scopes(
            requested_scopes=auth_session.scopes
    ):
        raise auth_errors.InvalidScopeError(
            f"Missing scopes: {', '.join(missing_scopes)}"
        )

    discord_credentials.store_credentials(token)
    auth_sessions.delete()
    return flask.redirect(auth_session.target
                          or flask.request.host_url)
