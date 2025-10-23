"""campus.apps.oauth.google

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
from typing import NotRequired, Optional, Required, TypedDict, cast

import flask
import werkzeug

from campus.client.vault import get_vault
from campus.common import env, integration, schema
from campus.common.errors import api_errors
from campus.common.utils import url
from campus.common.validation import flask as flask_validation
from campus.models import session, webauth
from campus.vault import credentials

PROVIDER = 'google'

google_credentials = credentials.get_provider(PROVIDER)

auth_sessions = session.AuthSessions(PROVIDER)
vault = get_vault()[PROVIDER]
bp = flask.Blueprint(PROVIDER, __name__, url_prefix=f'/{PROVIDER}')
oauthconfig = integration.get_config(PROVIDER)
oauth2 = webauth.oauth2.OAuth2AuthorizationCodeFlowScheme.from_json(
    config=cast(integration.schema.IntegrationConfigSchema, oauthconfig),
    security="oauth2"
)

# Set up logger for OAuth flow
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# class AuthorizeRequestSchema(TypedDict, total=False):
#     """Request type for Google OAuth authorization.

#     Reference: https://developers.google.com/identity/protocols/oauth2/web-server#httprest

#     NotRequired fields will be filled in by redirect endpoint.
#     """
#     target: Required[str]  # The URL to redirect to after successful authentication
#     login_hint: NotRequired[str]  # Optional hint for the user's email address
#     # prompt: str  # Not used


class Callback(TypedDict, total=False):
    """Response type for a Google OAuth callback.

    This may be a success or error callback.
    """
    state: Required[str]
    redirect_uri: Required[str]  # The URI to redirect to after authorization
    code: str  # on success
    scope: str  # on success
    authuser: str  # on success
    hd: str  # on success
    prompt: str  # on success
    error: str  # on error
    error_description: str  # on error
    error_uri: str  # on error


class GoogleTokenResponseSchema(TypedDict):
    """Response schema for access token exchange."""
    access_token: str  # Access token issued by the OAuth2 provider
    token_type: str  # Type of the token (e.g., "Bearer")
    expires_in: int  # Lifetime of the access token in seconds
    scope: str  # Scopes granted by the access token
    # Optional refresh token for long-lived sessions
    refresh_token: NotRequired[str]


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise auth routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.get('/authorize')
@flask_validation.unpack_request
def authorize(
        target: schema.Url,
        login_hint: Optional[schema.Email] = None
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
    redirect_uri = url.create_url(
        protocol="https",
        domain=env.HOSTNAME,
        path=flask.url_for('.callback')
    )
    auth_session = oauth2.init_session(
        redirect_uri=redirect_uri,
        user_id=login_hint,
        client_id=vault["CLIENT_ID"].get()["value"],
        scopes=oauth2.scopes,
        target=target,
    )
    authorization_url = oauth2.get_authorization_url(redirect_uri)
    return flask.redirect(authorization_url)


@bp.get('/callback')
def callback() -> werkzeug.Response:
    """Handles the Google OAuth callback request.
    
    Dispatches to success or error handlers based on paylaod type.
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
    """Handle a Google OAuth error callback request."""
    api_errors.raise_api_error(401,
                               error=error,
                               error_description=error_description,
                               error_uri=error_uri)

def success_callback(
        state: str,
        code: str,  # on success
        scope: str,  # on success
        authuser: str,  # on success
        hd: str,  # on success
        prompt: str  # on success
) -> werkzeug.Response:
    """Handle a Google OAuth callback request."""
    # Requests to endpoint are from Google, can be more loosely validated.
    auth_session = oauth2.retrieve_session()
    if not auth_session:
        flask.abort(401, description="No active OAuth session found.")
    if auth_session.id != state:
        flask.abort(401, description="Session state mismatch.")
    client_secret = vault["CLIENT_SECRET"].get()["value"]
    token_response = oauth2.exchange_code_for_token(
        code=code,
        client_secret=client_secret,
        redirect_uri=auth_session.redirect_uri,
    )

    # Validate the token response
    match token_response:
        case {"error": "invalid_grant"}:
            # Reference: https://developers.google.com/identity/protocols/oauth2/web-server#exchange-errors-invalid-grant
            # TODO: display user-friendly error message before restarting flow
            logger.warning("Invalid grant error - restarting OAuth flow")
            authorization_url = url.full_url_for('.authorize')
            return flask.redirect(authorization_url)
        case {"error": _}:
            # Handle other errors returned by the token exchange
            logger.error(f"Token exchange returned error: {token_response}")
            flask.abort(401, **token_response)

    # Retrieve user info (user_id)
    # user_id is needed to store creds
    user_info = oauth2.get_user_info(token_response["access_token"])
    if "error" in user_info:
        flask.abort(400, **user_info)
    token = google_credentials.create_credentials(
        expiry_seconds=token_response["expires_in"],
        access_token=token_response["access_token"],
        refresh_token=token_response.get("refresh_token"),
        scopes=token_response["scope"].split(" "),
        client_id=vault["CLIENT_ID"].get()["value"],
        user_id=user_info["email"]
    )
    assert token.access_token  # for static checkers

    # Verify requested scopes were granted
    if missing_scopes := token.get_missing_scopes(
        requested_scopes=oauth2.session.scopes
    ):
        flask.abort(403,
                    description="Missing required scopes.",
                    missing_scopes=list(missing_scopes),
                    granted_scopes=token.scopes)

    # Store the access token in the user's credentials
    google_credentials.store_credentials(token)

    auth_sessions.delete()
    return flask.redirect(oauth2.session.target
                          or flask.request.host_url)
