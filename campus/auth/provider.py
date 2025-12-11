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
(D) Campus backend exchanges the authorization code directly with
    Google's token endpoint for user profile.
"""

import flask
import werkzeug

import campus.config
from campus import flask_campus
from campus.common import schema
from campus.common.errors import api_errors, auth_errors, token_errors
from campus.common.utils import secret, utc_time

from . import resources

PROVIDER = "campus"


def _session_key() -> str:
    """Get the session key for Campus auth sessions."""
    return f"{PROVIDER}_session_id"


def init_app(app: flask.Blueprint | flask.Flask) -> None:
    """Initialize the OAuth2 provider by adding authorization and token
    routes.
    """
    app.add_url_rule("authorize", view_func=authorize, methods=["GET"])
    app.add_url_rule("token", view_func=token, methods=["POST"])


# OAuth2 endpoints
@flask_campus.unpack_request
def authorize(
        client_id: schema.CampusID,
        response_type: str,
        redirect_uri: str,
        state: str,
        scope: str | None = None,
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
        - state: str
            Opaque value used by the client to maintain state between
            request and callback.
            Typically used to pass a session ID or target; Campus uses
            it as session ID

    Responses:
        501 Not Implemented: None
        - Returned when missing scopes as this is not implemented yet.
        404 Session not found: None
        - Returned when the user session is not found and user needs to
          log in.
        401 Invalid client_id/user_id: None
        - Returned when the client_id or user_id in the session does not
          match the request.
        302 Found: Redirect
        - Redirects to the specified redirect URI with the
          authorization code, as well as state if provided.
          e.g. /oauth2/authorize?code=abc123&state=xyz
    """
    if response_type not in campus.config.SUPPORTED_OAUTH2_GRANT_TYPES:
        raise auth_errors.UnsupportedResponseTypeError(
            f"Unsupported response_type: {response_type}"
        )

    # Check if client exists
    resources.client[client_id].get()

    # ASSUME: app has already created a session via auth.sessions,
    # e.g. using campus_python
    # Provider should not create a new session, only update it.
    # Session ID should be passed as state parameter
    try:
        app_session = resources.session[PROVIDER][state].get()
    except api_errors.NotFoundError:
        # TODO: Handle invalid state error by redirecting back to app
        raise auth_errors.AuthorizationError(f"Invalid state: {state}") \
            from None

    # Validate client_id
    if client_id != app_session.client_id:
        raise auth_errors.UnauthorizedClientError(
            f"Client mismatch: {client_id}"
        )

    # Update authorization code if not set (for idempotency)
    if app_session.authorization_code is None:
        authorization_code = secret.generate_authorization_code()
        resources.session[PROVIDER][state].update(
            authorization_code=authorization_code
        )

    # Scope verification not yet handled here.
    # TODO: Create consent screen for user scope consent
    # The issued token will contain only the scopes allowed for the
    # client and consented by user.
    # The client app should handle insufficient scope errors.

    # Redirect to Google for OAuth
    params = {"target": redirect_uri}
    if hd:
        params["hd"] = hd
    oauth_authorize_url = flask.url_for(
        'auth.google.authorize',
        _external=True,
        **params
    )
    return flask.redirect(oauth_authorize_url)


@flask_campus.unpack_request
def token(
        grant_type: str,  # required
        code: str,  # required
        redirect_uri: str,  # required if used in /authorize
        client_id: str,  # required
        client_secret: str,  # required
) -> flask_campus.JsonResponse:
    """Summary:
        OAuth2 token endpoint for exchanging authorization code for
        access token.

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
        - Returned when the authorization code in the json does not
          match the one used in the session.
        400 Invalid redirect_uri: None
        - Returned when the redirect_uri does not match the one used in
          the authorization request.
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
