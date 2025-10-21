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
from typing import NotRequired, Required, TypedDict

from flask import Blueprint, Flask, redirect, request, url_for
from werkzeug.wrappers import Response

from campus.client.vault import get_vault
from campus.common import integration, schema
from campus.common.errors import api_errors
from campus.common.validation import flask as flask_validation
from campus.common.utils import url
from campus.common.webauth.oauth2 import (
    OAuth2AuthorizationCodeFlowScheme as OAuth2Flow
)
from campus.common.webauth.token import CredentialToken
from campus.models.credentials import UserCredentials
from campus.models.session import Sessions

PROVIDER = 'google'

google_user_credentials = UserCredentials(PROVIDER)

sessions = Sessions()
vault = get_vault()[PROVIDER]
bp = Blueprint(PROVIDER, __name__, url_prefix=f'/{PROVIDER}')
oauthconfig = integration.get_config(PROVIDER)
oauth2: OAuth2Flow = OAuth2Flow.from_json(oauthconfig, security="oauth2")

# Set up logger for OAuth flow
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class AuthorizeRequestSchema(TypedDict, total=False):
    """Request type for Google OAuth authorization.

    Reference: https://developers.google.com/identity/protocols/oauth2/web-server#httprest

    NotRequired fields will be filled in by redirect endpoint.
    """
    target: Required[str]  # The URL to redirect to after successful authentication
    login_hint: NotRequired[str]  # Optional hint for the user's email address
    # prompt: str  # Not used


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


def init_app(app: Flask | Blueprint) -> None:
    """Initialise auth routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.get('/authorize')
def authorize() -> Response:
    """Redirect to Google OAuth authorization endpoint."""
    logger.info("=== Google OAuth /authorize endpoint called ===")
    logger.debug(f"Request URL: {request.url}")
    logger.debug(f"Request args: {dict(request.args)}")
    logger.debug(f"Request host: {request.host}")

    # Requests to this endpoint are internal and should be strictly validated.
    params = flask_validation.validate_request_and_extract_urlparams(
        AuthorizeRequestSchema.__annotations__,
        on_error=api_errors.raise_api_error,
        ignore_extra=False,
    )
    logger.info(f"Validated params: {params}")

    # Store session with target URL
    session = oauth2.create_session(
        client_id=vault["CLIENT_ID"].get()["value"],
        scopes=oauth2.scopes,
        target=params.pop('target'),
    )
    logger.info(
        f"Created OAuth session - state: {session.state}, target: {session.target}")
    logger.debug(f"Session scopes: {session.scopes}")

    session.store()
    logger.debug("Session stored successfully")

    redirect_uri = url.create_url("https", request.host, url_for('.callback'))
    logger.info(f"Redirect URI: {redirect_uri}")

    authorization_url = session.get_authorization_url(
        redirect_uri,
        **params
    )
    logger.info(f"Authorization URL generated: {authorization_url}")
    logger.info("=== Redirecting to Google for authorization ===")

    return redirect(authorization_url)


@bp.get('/callback')
def callback() -> Response:
    """Handle a Google OAuth callback request."""
    logger.info("=== Google OAuth /callback endpoint called ===")
    logger.debug(f"Request URL: {request.url}")
    logger.debug(f"Request args: {dict(request.args)}")
    logger.debug(f"Request headers: {dict(request.headers)}")

    # Requests to this endpoint are from Google, can be more loosely validated.
    params = flask_validation.validate_request_and_extract_urlparams(
        Callback.__annotations__,
        on_error=api_errors.raise_api_error,
        ignore_extra=True,
        strict=False,
    )
    logger.info(f"Validated callback params: {params}")

    # Retrive session stored in /authorize
    # Exchange the authorization code for an access token.
    if "code" in params and "state" in params:
        logger.info("Success callback received (code and state present)")
    elif "error" in params:
        logger.error(f"Error callback received: {params}")
    else:
        logger.error(f"Unexpected callback response: {params}")
        raise AssertionError(f"Unexpected response: {params}") from None

    match params:
        case {"error": _}:
            logger.error(f"OAuth error response: {params}")
            api_errors.raise_api_error(401, **params)
        case {"code": code, "state": state}:
            logger.info(
                f"Processing authorization code exchange - state: {state}")
            logger.debug(
                f"Authorization code (first 10 chars): {code[:10]}...")

            session = oauth2.retrieve_session()
            if not session or session.state != state:
                logger.error(
                    f"Session state mismatch - expected: {session.state if session else 'NO SESSION'}, received: {state}")
                api_errors.raise_api_error(
                    401,
                    error="Invalid session state",
                    message="The session state does not match the expected value."
                )
            logger.info("Session state validated successfully")

            client_secret = vault["CLIENT_SECRET"].get()["value"]
            logger.debug(
                f"Client secret retrieved (length: {len(client_secret)})")
            redirect_uri = url.create_url(
                "https", request.host, url_for('.callback'))
            logger.info("Exchanging authorization code for token...")

            token_response = session.exchange_code_for_token(
                code=code,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
            )
            logger.info(
                f"Token exchange response received: {list(token_response.keys())}")
            if "error" in token_response:
                logger.error(f"Token exchange error: {token_response}")
            else:
                logger.debug(
                    f"Token type: {token_response.get('token_type')}, expires_in: {token_response.get('expires_in')}")
        case _:
            logger.error(f"Unexpected callback params structure: {params}")
            api_errors.raise_api_error(400, **params)

    # Validate the token response
    match token_response:
        case {"error": "invalid_grant"}:
            # Reference: https://developers.google.com/identity/protocols/oauth2/web-server#exchange-errors-invalid-grant
            # TODO: display user-friendly error message before restarting flow
            logger.warning("Invalid grant error - restarting OAuth flow")
            return redirect(url_for('authorize', target=session.target))
        case {"error": _}:
            # Handle other errors returned by the token exchange
            logger.error(f"Token exchange returned error: {token_response}")
            api_errors.raise_api_error(400, **token_response)

    flask_validation.validate_json_response(
        schema=GoogleTokenResponseSchema.__annotations__,
        resp_json=token_response,
        on_error=api_errors.raise_api_error,
        ignore_extra=True,
    )
    logger.info("Token response validated successfully")

    # Verify requested scopes were granted
    credentials = CredentialToken.from_response(token_response)
    logger.debug(f"Credentials created - scopes granted: {credentials.scopes}")

    missing_scopes = set(session.scopes) - set(credentials.scopes)
    if missing_scopes:
        logger.error(
            f"Missing scopes: {list(missing_scopes)}, granted: {credentials.scopes}")
        api_errors.raise_api_error(
            403,
            error="Missing scopes",
            missing_scopes=list(missing_scopes),
            granted_scopes=credentials.scopes,
        )
    logger.info("All requested scopes were granted")

    logger.info("Fetching user info...")
    user_info = oauth2.get_user_info(credentials.access_token)
    if "error" in user_info:
        logger.error(f"Failed to fetch user info: {user_info}")
        api_errors.raise_api_error(400, **user_info)
    logger.info(
        f"User info retrieved - email: {user_info.get('email', 'N/A')}")

    # Store the access token in the user's credentials
    logger.info(f"Storing credentials for user: {user_info['email']}")
    google_user_credentials.store(
        user_id=user_info["email"],
        issued_at=schema.DateTime.utcnow(),
        token=credentials.token,
    )
    logger.info("Credentials stored successfully")

    # Session cleanup is expected to be handled automatically
    logger.info(
        f"=== OAuth flow complete - redirecting to target: {session.target} ===")
    return redirect(session.target)


def get_valid_token(user_id: str) -> CredentialToken:
    """Retrieve the user's Google OAuth token.

    This function is not a flask view function.
    """
    record = google_user_credentials.get(user_id)
    token = CredentialToken.from_dict(PROVIDER, record["token"])
    if token.is_expired():
        # token is refreshed in-place
        oauth2.refresh_token(
            token=token,
            client_id=vault["CLIENT_ID"].get()["value"],
            client_secret=vault["CLIENT_SECRET"].get()["value"],
        )
        google_user_credentials.store(
            user_id=record["user_id"],
            issued_at=schema.DateTime.utcnow(),
            token=token.to_dict(),
        )
    return token
