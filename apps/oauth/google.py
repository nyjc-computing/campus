"""apps.oauth.google

Routes for Google OAuth2.
"""

from typing import NotRequired, TypedDict, Unpack

from flask import Blueprint, Flask

from apps import integrations
from apps.common.errors import api_errors
from apps.common.webauth.oauth2 import (
    OAuth2FlowScheme,
    OAuth2AuthorizationCodeFlowScheme,
)
from common.validation.flask import FlaskResponse, unpack_request, validate

bp = Blueprint('google', __name__, url_prefix='/google')
oauth2 = OAuth2FlowScheme.from_json(
    integrations.get_config('google')
)


class Callback(TypedDict, total=False):
    """Response type for a Google OAuth callback."""
    error: NotRequired[str]
    code: NotRequired[str]
    state: NotRequired[str]


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


@bp.post('/callback')
@unpack_request
@validate(
    request=Callback.__annotations__,
    response={"message": str},
    on_error=api_errors.raise_api_error
)
def google_callback(*_, **data: Unpack[Callback]) -> FlaskResponse:
    """Handle a Google OAuth callback request."""
    if "error" in data or "code" not in data:
        api_errors.raise_api_error(400, **data)
    # TODO: get client_id and client_secret from env
    assert isinstance(oauth2, OAuth2AuthorizationCodeFlowScheme)
    token_response = oauth2.exchange_code_for_token(
        code=data["code"],
        redirect_uri=data["redirect_uri"],
        client_id=client_id,
        client_secret=client_secret
    )
    if "error" in token_response:
        api_errors.raise_api_error(400, **token_response)
    # TODO: verify requested scopes were granted
    # TODO: store id, access token, refresh token, scopes in credentials store
    user_info = oauth2.get_user_info(token_response["access_token"])
    if "error" in user_info:
        api_errors.raise_api_error(400, **user_info)
    # TODO: redirect
