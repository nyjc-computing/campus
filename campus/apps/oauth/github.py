from typing import Required, TypedDict

from flask import Blueprint, Flask, redirect, request, url_for
from werkzeug.wrappers import Response

from campus.client.vault import get_vault
from campus.common import integration, schema
from campus.common.errors import api_errors
from campus.common.utils import url
from campus.common.validation import flask as flask_validation
from campus.common.webauth.oauth2 import (
    OAuth2AuthorizationCodeFlowScheme as OAuth2Flow
)
from campus.common.webauth.token import CredentialToken
from campus.models.credentials import UserCredentials
from campus.models.session import Sessions

PROVIDER = 'github'

github_user_credentials = UserCredentials(PROVIDER)

session = Sessions()
vault = get_vault()[PROVIDER]
bp = Blueprint(PROVIDER, __name__, url_prefix=f'/{PROVIDER}')
oauthconfig = integration.get_config(PROVIDER)
oauth2: OAuth2Flow = OAuth2Flow.from_json(oauth2config, security="oauth2")

class AuthorizeRequestSchema(TypedDict, total=False):
    
    target: Required[str]

class Callback(TypedDict, total=False):
    
    error: str
    code: str
    state: Required[str]
    error_description: str
    redirect_uri: Required[str]

class GithubTokenResponseSchema(TypedDict):
    access_token: str
    token_type: str
    scope: str


def init_app(app: Flask | Blueprint) -> None:
    """Initialise auth routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)

@bp.get('/authorize')
def authorize() -> Response:
    """Redirect to GitHub OAuth authorization endpoint."""
    params = flask_validation.validate_request_and_extract_urlparams(
        AuthorizeRequestSchema.__annotations__,
        on_error=api_errors.raise_api_error,
        ignore_extra=False
    )
    
    session = oauth2.create_session(
        client_id=vault["CLIENT_ID"].get()['value'],
        scopes=oauth2.scopes,
        target=params.pop("target")
    )
    session.store()
    redirect_uri = url.create_url("https", request.host, url_for(".callback"))
    authorization_url = session.get_authorization_url(
        redirect_uri,
        **params,
    )
    
    return redirect(authorization_url)


@bp.get('/callback')
def callback() -> Response:
    """Handle a GitHub OAuth callback request."""
    params = flask_validation.validate_request_and_extract_urlparams(
        Callback.__annotations__,
        on_error=api_errors.raise_api_error,
        ignore_extra=True,
    )
    
    match params:
        case {"error": _}:
            api_errors.raise_api_error(401, **params)
        case {"code": code, "state": state}:
            session = oauth2.retrieve_session()
            if not session or session.state != state:
                api_errors.raise_api_error(
                    401,
                    error="Invalid session state",
                    message="The session state does not match the expected value.",
                )
            token_response = session.exchange_code_for_token(
                code=code,
                client_secret=vault["CLIENT_SECRET"].get()["value"],
            )
        case _:
            api_errors.raise_api_error(400, **params)
    
    flask_validation.validate_json_response(
        schema=GithubTokenResponseSchema.__annotations__,
        resp_json=token_response,
        on_error=api_errors.raise_api_error,
        ignore_extra=True,
    )
    
    credentials = CredentialToken(provider=PROVIDER, **token_response)
    user_info = oauth2.get_user_info(credentials.access_token)
    if "error" in user_info:
        api_errors.raise_api_error(400, **user_info)
    
    github_user_credentials.store(
        user_id=user_info["id"],  # GitHub uses `id` as unique identifier
        issued_at=schema.DateTime.utcnow(),
        token=credentials.token,
    )
    
    return redirect(session.target)

def get_valid_token(user_id: str) -> CredentialToken:
    """Retrieve the user's GitHub OAuth token."""
    record = github_user_credentials.get(user_id)
    token = CredentialToken.from_dict(PROVIDER, record["token"])
    if token.is_expired():
        oauth2.refresh_token(
            token=token,
            client_id=vault["CLIENT_ID"].get()["value"],
            client_secret=vault["CLIENT_SECRET"].get()["value"],
        )
        github_user_credentials.store(
            user_id=record["user_id"],
            issued_at=schema.DateTime.utcnow(),
            token=token.to_dict(),
        )
    return token
