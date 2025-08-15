"""campus.apps.campusauth.routes

Routes for Campus authentication - clients and users.
"""

from typing import NotRequired, TypedDict, Unpack
from urllib.parse import urlencode

from flask import (
    Blueprint,
    Flask,
    redirect,
    session as flask_session,
    url_for
)

from campus.common.errors import api_errors
from campus.models.token import Tokens
import campus.common.validation.flask as flask_validation
from campus.common.utils import secret

# No url prefix because authentication endpoints are not only used by the API
bp = Blueprint('campusauth', __name__, url_prefix='/')

tokens = Tokens()


class AuthorizationCodeRequest(TypedDict):
    """Request data for OAuth2 authorization code request."""
    client_id: str
    response_type: str
    redirect_uri: str
    scope: NotRequired[str]
    state: NotRequired[str]


def init_app(app: Flask | Blueprint) -> None:
    """Initialise campusauth routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


# OAuth2 endpoints
@bp.get('/oauth2/authorize')
def oauth2_authorize() -> flask_validation.HtmlResponse:
    """OAuth2 authorization endpoint for user consent and code grant.

    This endpoint:
    1. Validates the authorization request
    2. Authenticates the user (through Google Workspace)
    3. Verifies scope of consent
    4. Issues authorization code
    5. Redirects user to the specified redirect URI
    """
    req_json: AuthorizationCodeRequest = flask_validation.validate_request_and_extract_json(
        AuthorizationCodeRequest.__annotations__,
        on_error=api_errors.raise_api_error
    )  # type: ignore
    if "session_id" not in flask_session:
        # TODO: redirect to login for authentication
        return redirect(url_for("campusauth.login"))
    session = tokens.get_session(
        session_id=flask_session["session_id"]
    )
    if not session:
        # TODO: Redirect to login with error message
        return "Session not found", 404
    # Verify client_id and user_id
    if session["client_id"] != req_json["client_id"]:
        # TODO: Redirect to login with error message
        return "Invalid client_id", 401
    if session["user_id"] != flask_session["user_id"]:
        # TODO: Redirect to login with error message
        return "Invalid user_id", 401
    # Verify scope of consent
    missing_scopes = tokens.validate_scope(
        session=session,
        scopes=req_json.get("scope") or ""
    )
    if missing_scopes:
        # TODO: redirect for additional scope authorization
        return "Not implemented", 501
    # Issue authorization code
    authorization_code = secret.generate_authorization_code()
    # TODO: Handle update errors
    session = tokens.update_session(
        session["id"],
        authorization_code=authorization_code
    )
    # Redirect user to the specified redirect URI
    params = {
        "code": authorization_code,
    }
    if "state" in req_json:
        params["state"] = req_json["state"]
    redirect_uri = f'{req_json["redirect_uri"]}?{urlencode(params)}'
    return redirect(redirect_uri), 302


@bp.post('/oauth2/token')
def oauth2_token() -> flask_validation.JsonResponse:
    """OAuth2 token endpoint for exchanging authorization code for access token."""
    # TODO: retrieve session, verify session auth_code

    return {"message": "Not implemented"}, 501


@bp.get('/login')
def login() -> flask_validation.HtmlResponse:
    """Login endpoint."""
    # TODO: Initialise auth session
    return redirect(url_for('campus.oauth.google.authorize'))


@bp.post('/logout')
def logout() -> flask_validation.HtmlResponse:
    """Logout endpoint."""
    # TODO: Revoke session
    return "Not implemented", 501
