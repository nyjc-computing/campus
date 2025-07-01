"""apps.oauth.google

Routes for Google OAuth2.

Reference: https://developers.google.com/identity/protocols/oauth2/web-server
"""

from typing import NotRequired, Required, TypedDict, Unpack

from flask import Blueprint, Flask

from apps.common.models.integration import config
from apps.common.errors import api_errors
from common.validation.flask import FlaskResponse, unpack_request, validate
from common.webauth.oauth2 import OAuth2AuthorizationCodeFlowScheme
from common.webauth.oauth2.authorization_code import (
    AuthorizationErrorCode,
)

vault = get_vault('google')
bp = Blueprint('google', __name__, url_prefix='/google')
oauth2: OAuth2AuthorizationCodeFlowScheme = OAuth2AuthorizationCodeFlowScheme.from_json(
    config.get_config('google')
)


class Authorize(TypedDict, total=False):
    """Request type for Google OAuth authorization.

    Reference: https://developers.google.com/identity/protocols/oauth2/web-server#httprest

    NotRequired fields will be filled in by redirect endpoint.
    """
    client_id: str  # will be filled in from vault
    redirect_uri: Required[str]  # The URI to redirect to after authorization
    response_type: str  # 'code' for authorization code flow
    scope: str  # Space-separated list of scopes requested
    access_type: NotRequired[str]  # from integration config
    state: NotRequired[str]  # Optional state parameter to maintain state between request and callback
    include_granted_scopes: bool  # from integration config
    login_hint: NotRequired[str]  # Optional hint for the user's email address
    # prompt: str  # Not used


class Callback(TypedDict, total=False):
    """Response type for a Google OAuth callback.

    This should be cast to either AuthorizationResponseSchema or
    AuthorizationErrorResponseSchema based on the presence of 'code' or 'error'.
    """
    error: AuthorizationErrorCode
    code: str
    state: str
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
    request=Authorize.__annotations__,
    response={"url": str},
    on_error=api_errors.raise_api_error
)
def google_authorize(*_, **params: Unpack[Authorize]) -> FlaskResponse:
    """Fill in missing params before redirect to Google OAuth authorization
    endpoint.
    """
    params["client_id"] = vault.get('CLIENT_ID')
    params["response_type"] = "code"
    params["access_type"] = "offline"
    if "redirect_uri" not in params or "scope" not in params:
        api_errors.raise_api_error(400, **params)

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
    token_response = oauth2.exchange_code_for_token(
        code=params["code"],
        redirect_uri=params["redirect_uri"],
        client_id=vault.get('CLIENT_ID'),
        client_secret= vault.get('CLIENT_SECRET'),
    )
    if "error" in token_response:
        api_errors.raise_api_error(400, **token_response)
    # TODO: verify requested scopes were granted
    # TODO: store id, access token, refresh token, scopes in credentials store
    user_info = oauth2.get_user_info(token_response["access_token"])
    if "error" in user_info:
        api_errors.raise_api_error(400, **user_info)
    # TODO: redirect
