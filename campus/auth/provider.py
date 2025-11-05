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

import flask
import werkzeug

from campus.common import flask as campus_flask, schema
from campus.common.errors import auth_errors, token_errors
from campus.common.utils import url, utc_time
import campus.config

from . import oauth_proxy, resources

PROVIDER = "campus"

bp = flask.Blueprint('auth', __name__, url_prefix='/auth')


def init_app(app: flask.Blueprint | flask.Flask) -> None:
    """Initialize the OAuth2 provider blueprint."""
    app.register_blueprint(bp)


def _session_key() -> str:
    """Get the session key for Campus auth sessions."""
    return f"{PROVIDER}_session_id"


# OAuth2 endpoints
@bp.get('/authorize')
@campus_flask.unpack_request
def authorize(
        client_id: schema.CampusID,
        response_type: str,
        redirect_uri: str,
        scope: str | None = None,
        state: str | None = None,
        *,
        hd: str | None = None,  # hosted domain (for Google)
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
    if response_type not in campus.config.SUPPORTED_OAUTH2_GRANT_TYPES:
        raise auth_errors.UnsupportedResponseTypeError(
            f"Unsupported response_type: {response_type}"
        )
    # Check if client exists
    client = resources.client[client_id].get()
    # TODO: Validate redirect_uri; must be absolute URL
    authsession = resources.session[PROVIDER].new(
        expiry_seconds=campus.config.DEFAULT_OAUTH_EXPIRY_MINUTES * 60,
        client_id=schema.CampusID(client_id),
        redirect_uri=schema.Url(redirect_uri),
        scopes=scope.split(" ") if scope else [],
        state=state
    )
    flask.session[_session_key()] = authsession.id
    # Scope verification is not handled here.
    # The issued token will contain only the scopes allowed for the
    # client and consented by user.
    # The client app should handle insufficient scope errors.

    # Redirect to Google for OAuth
    params = {
        "target": flask.url_for('.callback', _external=True)
    }
    if hd:
        params["hd"] = hd
    oauth_authorize_url = flask.url_for(
        'oauth.google.authorize',
        _external=True,
        **params
    )
    return flask.redirect(oauth_authorize_url)



@bp.get('/callback')
@campus_flask.unpack_request
def callback(
        code: str,
        state: str,
) -> werkzeug.Response:
    """Handle the OAuth2 callback response from Google for Campus
    authentication flows.

    Method:
        GET /auth/callback

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


    # The authorization flow (from /auth/authorize) is expected to have
    # gone through Google OAuth.
    # This means there are two session keys, one for Google OAuth
    # and one for Campus OAuth.
    callback_payload = campus_flask.get_request_payload()
    if "error" in callback_payload:
        auth_errors.raise_from_json(callback_payload)
    else:
        return campus_flask.unpack_into(success_callback,
                                        **callback_payload)


def success_callback(
        state: str,
        code: str,
        scope: str,
        **kwargs: str
) -> werkzeug.Response:
    """Handle a Google OAuth callback request."""
    # Handle Google OAuth callback, get google credentials
    google_proxy = oauth_proxy.google.proxy.get_proxy()
    google_credentials = google_proxy.handle_auth_callback(
        state,
        code,
        scope,
    )
    # Check Campus session validity
    session_id = state
    authsession = resources.session[PROVIDER][session_id].get()
    if authsession is None:
        raise token_errors.InvalidRequestError("Auth session not found")
    if authsession.is_expired():
        raise token_errors.InvalidRequestError("Auth session expired")
    # Update auth session with user ID from Google credentials
    authsession = resources.session[PROVIDER][session_id].update(
        session_id=session_id,
        user_id=schema.UserID(google_credentials.user_id)
    )
    # Finalize session and redirect to client
    del flask.session[_session_key()]
    redirect_uri = authsession.redirect_uri
    if authsession.state:
        redirect_url = url.with_params(
            redirect_uri,
            code=authsession.authorization_code,
            state=authsession.state,
            scope=scope,
        )
    else:
        redirect_url = url.with_params(
            redirect_uri,
            code=authsession.authorization_code,
            scope=scope,
        )
    return flask.redirect(redirect_url)


@bp.post('/token')
@campus_flask.unpack_request
def token(
        grant_type: str,  # required
        code: str,  # required
        redirect_uri: str,  # required if used in /authorize
        client_id: str,  # required
        client_secret: str,  # required
) -> campus_flask.JsonResponse:
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
    authsession = resources.session[PROVIDER].get(code)
    if not authsession:  # No session found
        raise token_errors.InvalidRequestError()
    if code != authsession.authorization_code:
        raise token_errors.InvalidGrantError("Invalid authorization code")
    if redirect_uri != authsession.redirect_uri:
        raise token_errors.InvalidGrantError(
            f"Invalid redirect_uri: {redirect_uri}"
        )
    # Raises auth errors if auth fails
    resources.client.raise_for_authentication(client_id, client_secret)
    # OAuth2 flow complete, revoke session
    resources.session[PROVIDER][authsession.id].delete()
    del flask.session[_session_key()]

    if not authsession.user_id:
        raise auth_errors.InvalidRequestError(
            "User ID not found in auth session"
        )
    user_credentials_resource = (
        resources.credentials[PROVIDER][authsession.user_id]
    )
    credentials = user_credentials_resource.get(authsession.client_id)
    # Create token if not existing
    if credentials.token and not credentials.token.is_expired():
        token = credentials.token
    else:
        token = user_credentials_resource.new(
            client_id=flask.g.current_client.id,
            scopes=authsession.scopes,
            expiry_seconds=(
                campus.config.DEFAULT_TOKEN_EXPIRY_DAYS
                * utc_time.DAY_SECONDS
            ),
        )
        user_credentials_resource.update(
            client_id=credentials.client_id,
            token=token
        )
    return token.to_resource(), 200
