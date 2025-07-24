"""apps.oauth.google

Routes for Google OAuth2.

Reference: https://developers.google.com/identity/protocols/oauth2/web-server
"""

import os
from typing import NotRequired, Required, TypedDict

from flask import Blueprint, Flask, redirect, request, url_for
from werkzeug.wrappers import Response

from campus.common.errors import api_errors
from campus.models.credentials import UserCredentials
from campus.common.webauth.oauth2 import (
    OAuth2AuthorizationCodeFlowScheme as OAuth2Flow
)
from campus.common.webauth.token import CredentialToken
from campus.common import integration
from campus.client import Campus
import campus.common.validation.flask as flask_validation
from campus.common.utils import url, utc_time

PROVIDER = 'google'

google_user_credentials = UserCredentials(PROVIDER)

campus_client = Campus()
vault = campus_client.vault[PROVIDER]
bp = Blueprint(PROVIDER, __name__, url_prefix=f'/{PROVIDER}')
oauthconfig = integration.get_config(PROVIDER)
oauth2: OAuth2Flow = OAuth2Flow.from_json(oauthconfig, security="oauth2")


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

    This should be cast to either AuthorizationResponseSchema or
    AuthorizationErrorResponseSchema based on the presence of 'code' or 'error'.
    """
    error: str
    code: str
    state: Required[str]
    error_description: str
    error_uri: str
    redirect_uri: Required[str]  # The URI to redirect to after authorization


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
    # Requests to this endpoint are internal and should be strictly validated.
    params = flask_validation.validate_request_and_extract_urlparams(
        AuthorizeRequestSchema.__annotations__,
        on_error=api_errors.raise_api_error,
        ignore_extra=False,
    )
    # Store session with target URL
    session = oauth2.create_session(
        client_id=vault["CLIENT_ID"].get(),
        scopes=oauth2.scopes,
        target=params.pop('target'),
    )
    session.store()
    redirect_uri = url.create_url("https", request.host, url_for('.callback'))
    authorization_url = session.get_authorization_url(
        redirect_uri,
        **params
    )
    return redirect(authorization_url)


@bp.get('/callback')
def callback() -> Response:
    """Handle a Google OAuth callback request."""
    # Requests to this endpoint are from Google, can be more loosely validated.
    params = flask_validation.validate_request_and_extract_urlparams(
        Callback.__annotations__,
        on_error=api_errors.raise_api_error,
        ignore_extra=True,
    )

    # Retrive session stored in /authorize
    # Exchange the authorization code for an access token.
    match params:
        case {"error": _}:
            api_errors.raise_api_error(401, **params)
        case {"code": code, "state": state}:
            session = oauth2.retrieve_session()
            if not session or session.state != state:
                api_errors.raise_api_error(
                    401,
                    error="Invalid session state",
                    message="The session state does not match the expected value."
                )
            token_response = session.exchange_code_for_token(
                code=code,
                client_secret=vault["CLIENT_SECRET"].get(),
            )
        case _:
            api_errors.raise_api_error(400, **params)

    # Validate the token response
    match token_response:
        case {"error": "invalid_grant"}:
            # Reference: https://developers.google.com/identity/protocols/oauth2/web-server#exchange-errors-invalid-grant
            # TODO: display user-friendly error message before restarting flow
            return redirect(url_for('authorize', target=session.target))
        case {"error": _}:
            # Handle other errors returned by the token exchange
            api_errors.raise_api_error(400, **token_response)
    flask_validation.validate_json_response(
        schema=GoogleTokenResponseSchema.__annotations__,
        resp_json=token_response,
        on_error=api_errors.raise_api_error,
        ignore_extra=True,
    )

    # Verify requested scopes were granted
    credentials = CredentialToken(provider=PROVIDER, **token_response)
    missing_scopes = set(session.scopes) - set(credentials.scopes)
    if missing_scopes:
        api_errors.raise_api_error(
            403,
            error="Missing scopes",
            missing_scopes=list(missing_scopes),
            granted_scopes=credentials.scopes,
        )
    user_info = oauth2.get_user_info(credentials.access_token)
    if "error" in user_info:
        api_errors.raise_api_error(400, **user_info)

    # Store the access token in the user's credentials
    google_user_credentials.store(
        user_id=user_info["email"],
        issued_at=utc_time.now(),
        token=credentials.token,
    )

    # Session cleanup is expected to be handled automatically
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
            client_id=vault["CLIENT_ID"].get(),
            client_secret=vault["CLIENT_SECRET"].get(),
        )
        google_user_credentials.store(
            user_id=record["user_id"],
            issued_at=utc_time.now(),
            token=token.to_dict(),
        )
    return token
