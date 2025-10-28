"""campus.auth.provider

Routes for implementing Campus OAuth2 provider.

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

import flask
import werkzeug

from campus.common import schema
from campus.common.errors import auth_errors, token_errors
from campus.common.utils import url, utc_time
from campus.common.validation import flask as flask_validation
from campus.models import session, token as token_model

from . import authentication

PROVIDER = "campus"

bp = flask.Blueprint('auth', __name__, url_prefix='/auth')

tokens = token_model.Tokens()
sessions = session.AuthSessions(PROVIDER)

DEFAULT_OAUTH_EXPIRY = 600
DEFAULT_TOKEN_EXPIRY = 30 * utc_time.DAY_SECONDS
SUPPORTED_GRANT_TYPES = ("code",)


def init_app(app: flask.Blueprint | flask.Flask) -> None:
    """Initialize the OAuth2 provider blueprint."""
    app.register_blueprint(bp)


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
@bp.get('/authorize')
@flask_validation.unpack_request
def authorize(
        client_id: schema.CampusID,  # required
        response_type: str,  # required
        redirect_uri: str | None = None,  # optional
        scope: str | None = None,  # optional
        state: str | None = None  # recommended
) -> werkzeug.Response:
    """Follows RFC 6749 Section 4.1.1
    https://datatracker.ietf.org/doc/html/rfc6749#section-4.1.1
    
    Summary: 
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
    if response_type not in SUPPORTED_GRANT_TYPES:
        raise auth_errors.UnsupportedResponseTypeError(
            f"Unsupported response_type: {response_type}"
        )
    client = authentication.get_client(client_id)
    if not client:
        raise auth_errors.UnauthorizedClientError(
            f"Invalid client_id: {client_id}"
        )
    # TODO: Validate redirect_uri; must be absolute URL
    authsession = sessions.new(
        client_id=client_id,
        expiry_seconds=DEFAULT_OAUTH_EXPIRY,
        redirect_uri=redirect_uri,
        scopes=scope.split(" ") if scope else [],
        state=state
    )
    # Scope verification is not handled here.
    # The issued token will contain only the scopes allowed for the
    # client and consented by user.
    # The client app should handle insufficient scope errors.

    # Redirect to Google for OAuth
    oauth_authorize_url = flask.url_for(
        'oauth.google.authorize',
        target=flask.url_for('.callback', _external=True),
    )
    return flask.redirect(oauth_authorize_url)


@bp.get('/callback')
def callback() -> werkzeug.Response:
    """OAuth2 callback endpoint after user authenticates with Google.

    Method:
        GET /oauth2/callback

    Path Parameters:
        None

    Query Parameters:
        - code: str (required)
            Authorization code returned by Google after user consent.
        - state: str (optional)
            Opaque value used by the client to maintain state between request and callback.

    Responses:
        302 Found: Redirect
        - Redirects to the original redirect_uri specified in /authorize,
          appending the authorization code and state if provided.
          e.g. /client/callback?code=abc123&state=xyz
    """
    # TODO: Check validity of Google OAuth token and identity
    authsession = sessions.get()
    redirect_uri: str = (
        authsession.redirect_uri
        if authsession and authsession.redirect_uri
        else flask.request.base_url
    )
    if authsession is None:
        raise token_errors.InvalidRequestError("Auth session not found")
    if authsession.state:
        redirect_url = url.with_params(
            redirect_uri,
            code=authsession.authorization_code,
            state=authsession.state
        )
    else:
        redirect_url = url.with_params(
            redirect_uri,
            code=authsession.authorization_code
        )
    return flask.redirect(redirect_url)


@bp.post('/token')
@flask_validation.unpack_request
def token(
        grant_type: str,  # required
        code: str,  # required
        redirect_uri: str,  # required if used in /authorize
        client_id: str,  # required
        client_secret: str,  # required
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
    if grant_type != "authorization_code":
        raise token_errors.UnsupportedGrantTypeError(
            f"Unsupported grant_type: {grant_type}"
        )
    authsession = sessions.get()
    if not authsession:
        raise token_errors.InvalidRequestError()
    if code != authsession.authorization_code:
        raise token_errors.InvalidGrantError("Invalid authorization code")
    if redirect_uri != authsession.redirect_uri:
        raise token_errors.InvalidGrantError(f"Invalid redirect_uri: {redirect_uri}")
    if "error" in authentication.authenticate_client(
        client_id,
        client_secret
    ):
        raise token_errors.UnauthorizedClientError(
            f"Unauthorized client: {client_id}"
        )
    # OAuth2 flow complete, revoke session
    sessions.delete(authsession.id)
    token = tokens.new(
        client_id=flask.g.current_client["id"],
        user_id=flask.g.current_user["id"],
        scopes=authsession.scopes,
        expiry_seconds=DEFAULT_TOKEN_EXPIRY
    )
    return token.to_dict(), 200
