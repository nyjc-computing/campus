"""apps.oauth.google

Routes for Google OAuth2.

Reference: https://developers.google.com/identity/protocols/oauth2/web-server
"""

import os
from typing import NotRequired, Required, TypedDict

from flask import Blueprint, Flask, redirect
from werkzeug.wrappers import Response

from apps.common.errors import api_errors
from apps.common.models.credentials import UserCredentials
from apps.common.webauth.oauth2 import (
    OAuth2AuthorizationCodeFlowScheme as OAuth2Flow
)
from common.integration import config
from common.services.vault import get_vault
import common.validation.flask as flask_validation

PROVIDER = 'google'

google_user_credentials = UserCredentials(PROVIDER)

vault = get_vault(PROVIDER)
bp = Blueprint(PROVIDER, __name__, url_prefix=f'/{PROVIDER}')
oauthconfig = config.get_config(PROVIDER)
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


class TokenResponseSchema(TypedDict, total=False):
    """Response schema for access token exchange."""
    access_token: str  # Access token issued by the OAuth2 provider
    token_type: str  # Type of the token (e.g., "Bearer")
    expires_in: int  # Lifetime of the access token in seconds
    scope: str  # Scopes granted by the access token
    refresh_token: NotRequired[str]  # Optional refresh token for long-lived sessions


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
    session = oauth2.create_session(
        client_id=vault.get('CLIENT_ID'),
        scopes=oauth2.scopes,
        target=params.pop('target'),
    )
    session.store()
    redirect_uri = os.environ['REDIRECT_URI']
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
    if "error" in params:
        api_errors.raise_api_error(401, **params)
    elif "code" not in params or "state" not in params:
        api_errors.raise_api_error(400, **params)
    session = oauth2.retrieve_session(params["state"])
    token_response = session.exchange_code_for_token(
        code=params["code"],
        client_secret= vault.get('CLIENT_SECRET'),
    )
    match token_response:
        case {"error": "invalid_grant"}:
            # Reference: https://developers.google.com/identity/protocols/oauth2/web-server#exchange-errors-invalid-grant
            # TODO: display user-friendly error message before restarting flow
            return redirect(url_for('authorize', target=session.target))

    # Verify requested scopes were granted
    assert "scope" in token_response, "Response missing scope"
    granted_scopes = token_response["scope"].split(" ")
    missing_scopes = set(session.scopes) - set(granted_scopes)
    if missing_scopes:
        api_errors.raise_api_error(
            403,
            error="Missing scopes",
            missing_scopes=list(missing_scopes),
            granted_scopes=granted_scopes,
        )
    assert "access_token" in token_response
    user_info = oauth2.get_user_info(token_response["access_token"])
    if "error" in user_info:
        api_errors.raise_api_error(400, **user_info)

    # Store the access token in the user's credentials
    google_user_credentials.store(
        user_id=user_info["email"],
        token=token_response
    )

    # Session cleanup is expected to be handled automatically
    return redirect(session.target)
