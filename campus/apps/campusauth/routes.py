"""campus.apps.campusauth.routes

Routes for Campus authentication - clients and users.

Campus OAuth 2.0 Authorization Flow Diagram:

+--------+        (A)        +---------+
|        | ----------------->|         |
|        |   Auth Request    |         |
|        |                   | Campus  |
|        |        (B)        | Backend |
|        | +---------------- +---------+
|        | | Redirect after
|        | |  session init   +---------+
|        | +---------------->|         |
                             | Google  |
|        |        (C)        |         |
|        | +---------------- +---------+
|        | | Redirect w Code +---------+     (D)       +-----------+
|        | +---------------->|         |---------------|  Google   |
|  User  |                   |         |<--------------| Tokeninfo |
|        |                   | Campus  |   Tokeninfo   | Endpoint  |
|        |                   | Backend |               +-----------+
|        |                   | (goog)  |
|        |<----------------- |         |
+--------+    Authorised     +---------+

Legend:
(A) User sends auth request to Campus
(B) User is redirected to Google for authentication and consent.
(C) Google redirects the user back to Campus with an authorization code.
(D) Campus backend exchanges the authorization code directly with Google's
    token endpoint for user profile.
"""

from typing import NotRequired, TypedDict
from urllib.parse import urlencode

from flask import (
    Blueprint,
    Flask,
    redirect,
    session as flask_session,
    url_for
)

from campus.common import schema
from campus.common.errors import api_errors
from campus.models.session import Sessions
from campus.models.token import Tokens
import campus.common.validation.flask as flask_validation
from campus.common.utils import secret

# No url prefix because authentication endpoints are not only used by the API
bp = Blueprint('campusauth', __name__, url_prefix='/')

tokens = Tokens()
sessions = Sessions()

DEFAULT_EXPIRY = 600


class AuthorizationCodeRequest(TypedDict):
    """Request data for OAuth2 authorization code request."""
    client_id: str
    response_type: str
    redirect_uri: str
    scope: NotRequired[str]
    state: NotRequired[str]


class TokenRequest(TypedDict):
    """Request data for OAuth2 token request."""
    grant_type: str
    code: str
    redirect_uri: str
    client_id: str
    client_secret: str


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

    At this point, the client (and thus the request) does not have a valid
    token yet, only an ongoing session, so there is no need to authenticate
    the request.
    """
    req_json: AuthorizationCodeRequest = flask_validation.validate_request_and_extract_json(
        AuthorizationCodeRequest.__annotations__,
        on_error=api_errors.raise_api_error
    )  # type: ignore
    if "session_id" not in flask_session:
        # TODO: redirect to login for authentication
        return redirect(url_for("campusauth.login"))
    session = sessions.get(flask_session["session_id"])
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
        return "Additional scope authorization not implemented", 501
    # Issue authorization code
    authorization_code = secret.generate_authorization_code()
    # TODO: Handle update errors
    session = sessions.update(
        session[schema.CAMPUS_KEY],
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
    """OAuth2 token endpoint for exchanging authorization code for
    access token.
    """
    req_json: TokenRequest = flask_validation.validate_request_and_extract_json(
        TokenRequest.__annotations__,
        on_error=api_errors.raise_api_error
    )  # type: ignore
    # No valid session
    if "session_id" not in flask_session:
        return {"error": "No OAuth session"}, 401
    session = sessions.get(flask_session["session_id"])
    if not session:
        return {"error": "No OAuth session"}, 401
    if not req_json["grant_type"] == "authorization_code":
        return {"error": "Invalid grant_type: expected 'authorization_code'"}, 400
    if not req_json["redirect_uri"] == session["redirect_uri"]:
        return {"error": "redirect_uri mismatch"}, 400
    if req_json["code"] != session["authorization_code"]:
        return {"error": "Invalid authorization code"}, 400
    # TODO: Issue token; get client_id from header, user_id from session
    token = tokens.new(
        {
            "client_id": session["client_id"],
            "user_id": session["user_id"],
            "scopes": session.get("scopes", []),
        },
        expiry_seconds=DEFAULT_EXPIRY
    )
    # OAuth2 flow complete, revoke session
    sessions.delete(session[schema.CAMPUS_KEY])
    return {"message": "Not implemented"}, 501


@bp.get('/login')
def login() -> flask_validation.HtmlResponse:
    """Login endpoint."""
    if "session_id" not in flask_session:
        # New login session
        session = sessions.new(
            {
                "user_id": flask_session["user_id"],
                "client_id": flask_session["client_id"]
            },
            expiry_seconds=DEFAULT_EXPIRY
        )
        flask_session["session_id"] = session[schema.CAMPUS_KEY]
    return redirect(url_for('oauth.google.authorize'))


@bp.post('/logout')
def logout() -> flask_validation.HtmlResponse:
    """Logout endpoint."""
    # TODO: Revoke login token
    return "Not implemented", 501
