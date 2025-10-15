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

from typing import NotRequired, TypedDict

from flask import Blueprint, Flask
from werkzeug.wrappers import Response

from campus.client.vault import get_vault
from campus.common import integration, schema
from campus.common.errors import api_errors
from campus.common.utils import utc_time
from campus.common.validation import flask as flask_validation
from campus.common.webauth.oauth2.client_credentials import (
    OAuth2ClientCredentialsFlowScheme as OAuth2Flow
)
from campus.common.webauth.token import CredentialToken

PROVIDER = 'discord'

vault = get_vault()[PROVIDER]
bp = Blueprint(PROVIDER, __name__, url_prefix=f'/{PROVIDER}')
oauthconfig = integration.get_config(PROVIDER)
oauth2: OAuth2Flow = OAuth2Flow.from_json(oauthconfig, security="oauth2")


class TokenRequestSchema(TypedDict, total=False):
    """Request schema for Discord app token request."""
    scopes: NotRequired[list[str]]  # Optional list of scopes to request


class DiscordTokenResponseSchema(TypedDict):
    """Response schema for Discord token endpoint."""
    access_token: str  # Access token issued by Discord
    token_type: str  # Type of the token (e.g., "Bearer")
    expires_in: int  # Lifetime of the access token in seconds
    scope: str  # Scopes granted by the access token


class AppTokenResponseSchema(TypedDict):
    """Normalized response schema for app token."""
    access_token: str  # Access token for Discord API
    token_type: str  # Token type (Bearer)
    expires_in: int  # Token lifetime in seconds
    scope: list[str]  # Granted scopes as list
    expires_at: schema.DateTime  # RFC3339 timestamp when token expires


def init_app(app: Flask | Blueprint) -> None:
    """Initialise Discord OAuth routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.post('/token')
def get_app_token() -> AppTokenResponseSchema:
    """Get Discord app token using Client Credentials flow."""
    # Validate request parameters
    params = flask_validation.validate_request_and_extract_json(
        TokenRequestSchema.__annotations__,
        on_error=api_errors.raise_api_error,
    )
    
    # Get client credentials from vault
    client_id = vault["CLIENT_ID"].get()["value"]
    client_secret = vault["CLIENT_SECRET"].get()["value"]
    
    # Use requested scopes or default application scopes
    scopes = params.get('scopes', oauth2.scopes)
    
    # Get app token from Discord
    token_response = oauth2.get_app_token(
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes
    )
    
    # Validate token response
    flask_validation.validate_json_response(
        schema=DiscordTokenResponseSchema.__annotations__,
        resp_json=token_response,
        on_error=api_errors.raise_api_error,
        ignore_extra=True,
    )
    
    # Create normalized response
    credentials = CredentialToken(provider=PROVIDER, **token_response)
    expires_at = schema.DateTime.utcafter(seconds=token_response["expires_in"])
    
    response_data: AppTokenResponseSchema = {
        "access_token": token_response["access_token"],
        "token_type": token_response["token_type"],
        "expires_in": token_response["expires_in"],
        "scope": credentials.scopes,
        "expires_at": expires_at,
    }
    flask_validation.validate_json_response(
        schema=AppTokenResponseSchema.__annotations__,
        resp_json=response_data,
        on_error=api_errors.raise_api_error,
    )
    return response_data


@bp.get('/token')
def get_app_token_get() -> AppTokenResponseSchema:
    """Get Discord app token using Client Credentials flow (GET method)."""
    # Validate query parameters
    params = flask_validation.validate_request_and_extract_urlparams(
        TokenRequestSchema.__annotations__,
        on_error=api_errors.raise_api_error,
        ignore_extra=False,
    )
    
    # Get client credentials from vault
    client_id = vault["CLIENT_ID"].get()["value"]
    client_secret = vault["CLIENT_SECRET"].get()["value"]
    
    # Use requested scopes or default application scopes
    scopes = params.get('scopes', oauth2.scopes)
    
    # Get app token from Discord
    token_response = oauth2.get_app_token(
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes
    )
    
    # Validate token response
    flask_validation.validate_json_response(
        schema=DiscordTokenResponseSchema.__annotations__,
        resp_json=token_response,
        on_error=api_errors.raise_api_error,
        ignore_extra=True,
    )
    
    # Create normalized response
    credentials = CredentialToken(provider=PROVIDER, **token_response)
    expires_at = schema.DateTime.utcafter(seconds=token_response["expires_in"])
    
    response_data: AppTokenResponseSchema = {
        "access_token": token_response["access_token"],
        "token_type": token_response["token_type"],
        "expires_in": token_response["expires_in"],
        "scope": credentials.scopes,
        "expires_at": expires_at,
    }
    flask_validation.validate_json_response(
        schema=AppTokenResponseSchema.__annotations__,
        resp_json=response_data,
        on_error=api_errors.raise_api_error,
    )
    return response_data


def get_valid_app_token(scopes: list[str] | None = None) -> CredentialToken:
    """Retrieve a valid Discord app token.
    
    This function is not a flask view function.
    Returns a cached token if valid, otherwise fetches a new one.
    """
    # TODO: Implement token caching logic
    # For now, always fetch a new token
    
    client_id = vault["CLIENT_ID"].get()["value"]
    client_secret = vault["CLIENT_SECRET"].get()["value"]
    
    scopes = scopes or oauth2.scopes
    
    token_response = oauth2.get_app_token(
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes
    )
    
    credentials = CredentialToken(provider=PROVIDER, **token_response)
    
    # TODO: Cache the token with expiry timestamp
    # TODO: Check cache first and return cached token if still valid
    
    return credentials
