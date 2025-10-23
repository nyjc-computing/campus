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

import logging
from typing import Any

import flask
import werkzeug

from campus.common import env, schema
from campus.models import credentials, session
from campus.common.utils import url, secret
import campus.common.validation.flask as flask_validation
from campus.vault import credentials

DEFAULT_TARGET_ENDPOINT = ".success"
PROVIDER = "campus"

# No url prefix because authentication endpoints are not only used by the API
bp = flask.Blueprint('campusauth', __name__, url_prefix='/')

# tokens = Tokens()
auth_sessions = session.AuthSessions(PROVIDER)
login_sessions = session.LoginSessions()
campus_credentials = credentials.get_provider(PROVIDER)

DEFAULT_EXPIRY = 600  # in minutes

# Set up logger for authentication flow
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# class AuthorizationCodeRequest(TypedDict):
#     """Request data for OAuth2 authorization code request."""
#     client_id: str
#     response_type: str
#     redirect_uri: str
#     scope: NotRequired[str]
#     state: NotRequired[str]


# class TokenRequest(TypedDict):
#     """Request data for OAuth2 token request."""
#     grant_type: str
#     code: str
#     redirect_uri: str
#     client_id: str
#     client_secret: str

# OAuth2 endpoints
@bp.get('/authorize')
@flask_validation.unpack_request
def authorize(
        client_id: str,
        response_type: str,
        redirect_uri: str | None = None,
        scope: str | None = None,
        state: str | None = None,  # client secret
        target: str | None = None,
) -> werkzeug.Response:
    """Implements RFC 6749 4.1.1 Authorization Code Grant

    Method:
        GET /authorize

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
    if response_type != "code":
        flask.abort(400, description="Invalid response_type: expected 'code'")
    auth_session = auth_sessions.get()
    if auth_session and auth_session.client_id == client_id:
        # Valid auth session exists; revoke and restart auth flow
        auth_sessions.delete(auth_session.id)
    # Create new auth session
    auth_session = auth_sessions.new(
        client_id=client_id,
        redirect_uri=schema.Url(redirect_uri),
        scopes=scope.split() if scope else [],
        authorization_code=secret.generate_authorization_code(),
        state=state,
        target=target
    )
    # Defer to campus.oauth.google for user authentication
    oauth_authorize_url = flask.url_for(
        endpoint='oauth.google.authorize',
        target=flask.url_for('.campusapp_callback'),
    )
    return flask.redirect(oauth_authorize_url)


@bp.get('/callback')
def campusapp_callback() -> werkzeug.Response:
    """After user authentication with Google."""
    auth_session = auth_sessions.get()
    if not auth_session:
        flask.abort(401, description="No OAuth session found")
    # Redirect to callback uri with authorization code
    params: dict[str, Any] = {"code": auth_session.authorization_code}
    if auth_session.state:
        params["state"] = auth_session.state
    if auth_session.scopes:
        params["scope"] = " ".join(auth_session.scopes)
    redirect_uri_with_params = url.with_params(
        auth_session.target or flask.request.host_url,
        **params
    )
    # Don't delete auth session yet; needed for token exchange
    return flask.redirect(redirect_uri_with_params)


@bp.post('/token')
@flask_validation.unpack_request
def token(
        grant_type: str,
        code: str,
        redirect_uri: str,
        client_id: str,
        client_secret: str,
) -> flask_validation.JsonResponse:
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
    session = auth_sessions.get()
    if not session:
        return {"error": "No OAuth session"}, 401
    if not grant_type == "authorization_code":
        return {"error": "Invalid grant_type: expected 'authorization_code'"}, 400
    if code != session.authorization_code:
        return {"error": "Invalid authorization code"}, 400
    # TODO: Validate client_id and client_secret
    # TODO: Validate redirect_uri
    # TODO: Issue token
    token = campus_credentials.create_credentials(
        user_id=session.user_id,
        client_id=session.client_id,
        scopes=session.scopes,
        expiry_seconds=DEFAULT_EXPIRY * 60
    )
    # OAuth2 flow complete, revoke auth code and clear session state
    auth_sessions.delete(session.id)
    return token.to_dict(), 200


@bp.get('/login')
def login() -> werkzeug.Response:
    """Main login page user authentication.

    For testing only, should be implemented by client applications.
    For now, it redirects directly to Google OAuth2 authorization.
    """
    authorization_url = flask.url_for(
        ".authorize",
        client_id=env.CLIENT_ID,
        response_type="code",
        redirect_uri=url.full_url_for('.campusapp_callback'),
        scope="",
        state=secret.generate_session_state(),
        target=url.full_url_for('.success')
    )
    return flask.redirect(authorization_url)


@bp.post('/logout')
def logout() -> werkzeug.Response:
    """Page to log user out."""
    auth_sessions.delete()
    return flask.redirect(flask.url_for('campus.home'))


@bp.get('/success')
def success() -> str:
    """Placeholder success page after successful authentication."""
    return f"Authentication successful!<br>Args: {flask.request.args}"
