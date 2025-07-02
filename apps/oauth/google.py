"""apps.oauth.google

Routes for Google OAuth2.

Reference: https://developers.google.com/identity/protocols/oauth2/web-server
"""

from typing import NotRequired, Required, TypedDict, Unpack

from flask import Blueprint, Flask, redirect
from werkzeug.wrappers import Response

from apps.common.errors import api_errors
from apps.common.models.credentials import UserCredentials
from apps.common.webauth.oauth2 import (
    OAuth2AuthorizationCodeFlowScheme as OAuth2Flow
)
from apps.common.webauth.oauth2.authorization_code import AuthorizationErrorCode
from common.integration import config
from common.services.vault import get_vault
from common.validation.flask import unpack_request_urlparams

PROVIDER = 'google'

user_credentials = UserCredentials(PROVIDER)

vault = get_vault(PROVIDER)
bp = Blueprint(PROVIDER, __name__, url_prefix=f'/{PROVIDER}')
oauthconfig = config.get_config(PROVIDER)
oauth2: OAuth2Flow = OAuth2Flow.from_json(
    oauthconfig,
    security="oauth2",
)


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
    error: AuthorizationErrorCode
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
@unpack_request_urlparams
def authorize(*_, **params: Unpack[AuthorizeRequestSchema]) -> Response:
    """Redirect to Google OAuth authorization endpoint."""
    session = oauth2.create_session(
        client_id=vault.get('CLIENT_ID'),
        scopes=oauth2.scopes,
        target=params['target'],
    )
    session.store()
    if "login_hint" in params:
        extra_params = {"login_hint": params["login_hint"]}
    else:
        extra_params = {}
    authorization_url = session.get_authorization_url(**extra_params)
    return redirect(authorization_url)

@bp.get('/callback')
@unpack_request_urlparams
def callback(*_, **params: Unpack[Callback]) -> Response:
    """Handle a Google OAuth callback request."""
    if "error" in params:
        api_errors.raise_api_error(401, **params)
    elif "code" not in params or "state" not in params:
        api_errors.raise_api_error(400, **params)
    session = oauth2.retrieve_session(params["state"])
    token_response = session.exchange_code_for_token(
        code=params["code"],
        client_secret= vault.get('CLIENT_SECRET'),
    )
    if "error" in token_response:
        api_errors.raise_api_error(400, **token_response)

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
    user_credentials.store(
        user_id=user_info["email"],
        token=token_response
    )

    # Session cleanup is expected to be handled automatically
    return redirect(session.target)
