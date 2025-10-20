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

from typing import NotRequired, TypedDict, cast
from urllib.parse import urlencode

from flask import (
    Blueprint,
    g,
    redirect,
    session as flask_session,
    url_for
)
from werkzeug.wrappers import Response

from campus.common import schema
from campus.common.errors import api_errors
from campus.models.session import Sessions
from campus.models.token import Tokens
from campus.common.utils import secret
import campus.common.validation.flask as flask_validation

from .authentication import client_auth_required


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


# OAuth2 endpoints
@client_auth_required
@bp.get('/oauth2/authorize')
def oauth2_authorize() -> Response:
    """Summary: 
        OAuth2 authorization endpoint for user consent and code grant.
        1. Validates the authorization request
        2. Authenticates the user (through Google Workspace)
        3. Verifies scope of consent
        4. Issues authorization code
        5. Redirects user to the specified redirect URI

    Method:
        GET /oauth2/authorize

    Path Parameters:
        None

    Query parameters:
        - client_id: ID of OAuth client requesting authorization
        - response_type: str (required)
            Must be "code" for authorization code flow.
        - redirect_uri: str (required)
            URI to redirect the user to after authentication
        - scope: str (optional)
            Space-separated list of scopes requested by the client.
        - state: str (optional)
            Opaque value used by the client to maintain state between request and callback.

    Responses:
        501 Not Implemented: None
        - Returned when missing scopes as this is not implemented yet.
        404 Session not found: None
        - Returned when the user session is not found and user needs to log in.
        401 Invalid client_id/user_id: None
        - Returned when the client_id or user_id in the session does not match the request.
        302 Found: Redirect
        - Redirects to the specified redirect URI with the authorization code, as well as state if provided.
          e.g. /oauth2/authorize?code=abc123&state=xyz
    """
    req_json: AuthorizationCodeRequest = flask_validation.validate_request_and_extract_json(
        AuthorizationCodeRequest.__annotations__,
        on_error=api_errors.raise_api_error
    )  # type: ignore
    session = sessions.get()
    if not session:
        # TODO: Redirect to login with error message
        return redirect(url_for("campusauth.login"))
    # TODO: Verify scope of consent against user access level
    # missing_scopes = tokens.validate_scope(
    #     session=dict(session),
    #     scopes=req_json.get("scope") or ""
    # )
    # if missing_scopes:
    #     # TODO: redirect for additional scope authorization
    #     return "Additional scope authorization not implemented", 501
    # Issue authorization code
    authorization_code = secret.generate_authorization_code()
    target = req_json.get("state", "")
    # TODO: Handle update errors
    session = sessions.update(
        session[schema.CAMPUS_KEY],
        authorization_code=authorization_code,
        # scopes=req_json.get("scope", "").split(),
        redirect_uri=req_json["redirect_uri"],
        target=target
    )
    # Redirect user to the specified redirect URI
    params = {
        "code": authorization_code,
    }
    if target:
        params["state"] = target
    redirect_uri = f'{req_json["redirect_uri"]}?{urlencode(params)}'
    return redirect(redirect_uri)


@client_auth_required
@bp.post('/oauth2/token')
def oauth2_token() -> flask_validation.JsonResponse:
    """Summary:
        OAuth2 token endpoint for exchanging authorization code for access token.

    Method:
        POST /oauth2/token

    Path Parameters:
        None

    Query Parameters:
        None

    Request Body:
        grant_type: str (required)
            Must be "authorization_code".
        code: str (required)
            The authorization code received from `/oauth2/authorize`.
        redirect_uri: str (required)
            Must match the redirect_uri used in authorization.
        client_id: str (required)
            OAuth client identifier.
        client_secret: str (required)
            Secret key for the OAuth client.

    Responses:
        501 Not Implemented: None
        - Returned as token issuance is not implemented yet, as well as completing the OAuth2 flow and revoking the session.
        400 Invalid authorization code: None
        - Returned when the authorization code in the json does not match the one used in the session.
        400 Invalid redirect_uri: None
        - Returned when the redirect_uri does not match the one used in the authorization request.
        400 Invalid grant_type: None
        - Returned when grant_type is not "authorization_code"
        401 Not authenticated: None
        - Returned when the session ID is not in the Flask session
    """
    req_json: TokenRequest = cast(
        TokenRequest,
        flask_validation.validate_request_and_extract_json(
            TokenRequest.__annotations__,
            on_error=api_errors.raise_api_error
        )
    )
    session = sessions.get()
    if not session:
        return {"error": "No OAuth session"}, 401
    if not req_json["grant_type"] == "authorization_code":
        return {"error": "Invalid grant_type: expected 'authorization_code'"}, 400
    if req_json["code"] != session["authorization_code"]:
        return {"error": "Invalid authorization code"}, 400
    # TODO: Issue token
    token = tokens.new(
        {
            "client_id": g.current_client["id"],
            "user_id": g.current_user["id"],
            "scopes": session["scopes"],
        },
        expiry_seconds=DEFAULT_EXPIRY
    )
    # OAuth2 flow complete, revoke session
    sessions.delete(session[schema.CAMPUS_KEY])
    return {"message": "Not implemented"}, 501


@bp.get('/login')
def login() -> Response:
    """Summary:
        Login endpoint for user authentication.

    Method:
        GET /login

    Path Parameters:
        None

    Query Parameters:
        None

    Responses:
        302 Found: Redirect
        - If the user is already logged in, redirects to the home or dashboard page, 
          otherwise creates a new session and redirects to OAuth authorization.
    """
    login_session = sessions.get()
    if login_session:
        # User already logged in, redirect to home or dashboard
        return redirect(url_for('campus.home'))
    # TODO: get user_id, client_id from auth header
    sessions.new(
        {
            "user_id": flask_session["user_id"],
            "client_id": flask_session["client_id"]
        },
        expiry_seconds=DEFAULT_EXPIRY
    )
    return redirect(url_for('oauth.google.authorize'))


@bp.post('/logout')
def logout() -> Response:
    """Summary:
        Logout endpoint for user session termination.

    Method:
        POST /logout

    Path Parameters:
        None

    Query Parameters:
        None

    Request Body:
        None

    Responses:
        501 Not Implemented: str
        - Returned as revoking the login is not implemented yet.
    """
    sessions.delete()
    return redirect(url_for('campus.home'))
