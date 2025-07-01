"""apps.oauth.google

Routes for Google OAuth2.

Reference: https://developers.google.com/identity/protocols/oauth2/web-server
"""

from typing import NotRequired, Required, TypedDict, Unpack

from flask import Blueprint, Flask, redirect

from apps.common.models.integration import config
from apps.common.errors import api_errors
from common.services.vault import get_vault
from common.validation.flask import FlaskResponse, unpack_request, validate
from common.webauth.credentials import ProviderCredentials
from common.webauth.oauth2 import (
    OAuth2AuthorizationCodeFlowScheme as OAuth2Flow
)
from common.webauth.oauth2.authorization_code import (
    AuthorizationErrorCode,
)

PROVIDER = 'google'

vault = get_vault(PROVIDER)
bp = Blueprint(PROVIDER, __name__, url_prefix=f'/{PROVIDER}')
oauthconfig = config.get_config(PROVIDER)
oauth2: OAuth2Flow = OAuth2Flow.from_json(oauthconfig)


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
@validate(
    request=AuthorizeRequestSchema.__annotations__,
    response={"url": str},
    on_error=api_errors.raise_api_error
)
def google_authorize(*_, **params: Unpack[AuthorizeRequestSchema]) -> FlaskResponse:
    """Redirect to Google OAuth authorization endpoint."""
    session = oauth2.create_session(
        client_id=vault.get('CLIENT_ID'),
        scopes=oauth2.scopes,
        target=params['target'],
    )
    session.store()
    # TODO: pass login_hint to authorization URL if provided
    extra_params = {}
    return redirect(session.get_authorization_url(**extra_params))

@bp.post('/callback')
@unpack_request
@validate(
    request=Callback.__annotations__,
    response={"message": str},
    on_error=api_errors.raise_api_error
)
def google_callback(*_, **params: Unpack[Callback]) -> FlaskResponse:
    """Handle a Google OAuth callback request."""
    if "error" in params:
        api_errors.raise_api_error(401, **params)
    elif "code" not in params:
        api_errors.raise_api_error(400, **params)
    session = oauth2.retrieve_session(params["state"])
    if not session:
        api_errors.raise_api_error(400, error="No authentication session found")
    token_response = session.exchange_code_for_token(
        code=params["code"],
        client_secret= vault.get('CLIENT_SECRET'),
    )
    if "error" in token_response:
        api_errors.raise_api_error(400, **token_response)
    # TODO: verify requested scopes were granted
    assert "access_token" in token_response, "Access token not found in response"
    user_info = oauth2.get_user_info(token_response["access_token"])
    if "error" in user_info:
        api_errors.raise_api_error(400, **user_info)
    # Store the access token in the user's credentials
    credentials = ProviderCredentials(user_info["email"], "google")
    credentials.set_access_token(token_response["access_token"])
    credentials.set_scopes(token_response["scope"].split(" "))
    if "refresh_token" in token_response:
        credentials.set_refresh_token(token_response["refresh_token"])
    # TODO: handle successful authentication
    session.delete()
    return redirect(session.target)
