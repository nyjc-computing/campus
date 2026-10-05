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

import logging
from contextlib import suppress

import flask
import werkzeug

import campus.config
import campus.model as model
from campus import flask_campus
from campus.common import env, schema
from campus.common.errors import api_errors, auth_errors, token_errors
from campus.common.utils import secret, uid, url, utc_time

from . import resources, scopes

logger = logging.getLogger(__name__)

PROVIDER = "campus"
INVALIDATED = "INVALIDATED"  # Marker for used authorization codes

campus_cred_resource = resources.credentials[PROVIDER]
google_cred_resource = resources.credentials["google"]


def _session_key() -> str:
    """Get the session key for Campus auth sessions."""
    return f"{PROVIDER}_session_id"


def _stash_span_identity(
        *,
        client_id: schema.CampusID | str | None = None,
        user_id: schema.UserID | str | None = None,
) -> None:
    """Stamp the current request's span with login-flow identity (#820).

    Browser hops don't run the Authenticator, so nothing stashes
    client/user for the tracing middleware's span enrichment (#794's
    "auth spans missing client_id/user_id" flag). Same pattern as the
    journey stash (#803): the middleware reads g.client_id/g.user_id
    in after_request.
    """
    if client_id:
        flask.g.client_id = str(client_id)
    if user_id:
        flask.g.user_id = str(user_id)


def init_app(app: flask.Blueprint | flask.Flask) -> None:
    """Initialize the OAuth2 provider by adding authorization and token
    routes.
    """
    app.add_url_rule("authorize", view_func=authorize, methods=["GET"])
    app.add_url_rule("token", view_func=token, methods=["POST"])
    app.add_url_rule(
        "verify_login",
        view_func=verify_login_and_redirect,
        methods=["GET"]  # Changed from POST - called via redirect from Google callback
    )


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
            Space-separated list of Campus scopes requested by the
            client; must be within the session's scopes.
        - state: str
            Opaque value used by the client to maintain state between
            request and callback.
            Typically used to pass a session ID or target; Campus uses
            it as session ID

    Responses:
        400 invalid_scope: None
        - Returned when the request's scope parameter exceeds the
          scopes granted in the referenced auth session.
        404 Session not found: None
        - Returned when the user session is not found and user needs to
          log in.
        401 Invalid client_id/user_id: None
        - Returned when the client_id or user_id in the session does not
          match the request.
        400 Invalid request: None
        - Returned (without redirecting) when the client has no
          registered redirect_uris, when the request's redirect_uri does
          not exactly match a registered URI (RFC 6749 §3.1.2.2), or
          when the session's redirect_uri does not match the request.
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
    client = resources.client[client_id].get()

    # RFC 6749 §3.1.2.2: validate the request's redirect_uri against the
    # client's registered redirect_uris. §4.1.2.1 requires rejecting the
    # request without redirecting on mismatch, and this server fails
    # closed on clients with no registered redirect_uris at all.
    registered_uris = client.redirect_uris or []
    if not registered_uris:
        raise auth_errors.InvalidRequestError(
            f"Client '{client_id}' has no registered redirect_uris; "
            "authorization requests are rejected"
        )
    if redirect_uri not in registered_uris:
        raise auth_errors.InvalidRequestError(
            f"redirect_uri '{redirect_uri}' is not registered for "
            f"client '{client_id}'"
        )

    # ASSUME: app has already created a session via auth.sessions,
    # e.g. using campus_python
    # Provider should not create a new session, only update it.
    # Session ID should be passed as state parameter
    try:
        app_session = (
            resources.session[PROVIDER][schema.CampusID(state)]
            .get()
        )
    except api_errors.NotFoundError:
        # TODO: Handle invalid state error by redirecting back to app
        raise auth_errors.AuthorizationError(f"Invalid state: {state}") \
            from None

    # Validate client_id
    if client_id != app_session.client_id:
        raise auth_errors.UnauthorizedClientError(
            f"Client mismatch: {client_id}"
        )

    # Span identity (#820): stamp this browser hop's span with the
    # login flow's client — the middleware reads g.client_id/g.user_id
    # the same way it reads g.journey_id (#803).
    _stash_span_identity(client_id=client_id)

    # The authorization code is delivered to the session's redirect_uri,
    # so it must be the same registered URI that the request presented.
    if app_session.redirect_uri != redirect_uri:
        raise auth_errors.InvalidRequestError(
            "Session redirect_uri does not match the authorization request"
        )

    # The authorization request's scope parameter (RFC 6749 section 3.3)
    # must not exceed the scopes the session was created with: the
    # session API is the validated boundary (invariant A6,
    # docs/auth-token-invariants.md).
    if scope is not None:
        requested_scopes = scopes.parse(scope)
        if not scopes.covers(app_session.scopes, requested_scopes):
            raise auth_errors.InvalidScopeError(
                "Requested scope exceeds the scopes granted in the "
                "auth session",
                requested_scopes=requested_scopes,
                session_scopes=app_session.scopes,
            )

    # Login never carries upstream scopes (#733 Phase 2 retirement):
    # the google authorize endpoint merges its own base identity
    # scopes, and integration scopes are obtained exclusively through
    # the per-integration connect flow.

    # Build verify_login callback URL with Campus session state
    verify_callback_url = url.full_url_for(
        'auth.verify_login_and_redirect',
        state=state  # Preserve Campus session ID through Google OAuth flow
    )

    # Redirect to Google for OAuth with callback to verify_login
    params = {"target": verify_callback_url}
    if hd:
        params["hd"] = hd
    oauth_authorize_url = url.full_url_for(
        'auth.google.authorize',
        **params
    )

    # Login-journey correlation (#803): /authorize is the flow's first
    # browser touch, so it issues (or reuses) the campus_journey cookie
    # and records the id on the auth session — the server-to-server
    # /token exchange reads it from there later, since that call never
    # carries browser cookies. The id is also stashed in flask.g so this
    # request's own span gets the tag too: the middleware runs after the
    # handler, but it reads cookies from the request, which predates the
    # Set-Cookie on this response.
    journey_id = (
        flask.request.cookies.get(campus.config.JOURNEY_COOKIE)
        or uid.generate_category_uid("journey")
    )
    flask.g.journey_id = journey_id
    resources.session[PROVIDER][state].update(journey_id=journey_id)

    response = flask.redirect(oauth_authorize_url)
    response.set_cookie(
        campus.config.JOURNEY_COOKIE,
        journey_id,
        max_age=campus.config.JOURNEY_COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
    )
    return response


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
        POST /token

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
        401 unauthorized_client: None
        - Returned when the presenting client is not the client the
          authorization code was issued to (RFC 6749 section 4.1.3).
        401 Not authenticated: None
        - Returned when the session ID is not in the Flask session

    Scope handling:
        The exchanged token covers every scope of the auth session. If
        the user already holds an unexpired grant for this client that
        covers the requested scopes, that token is reused; otherwise a
        new token is issued with the union of the existing grant and
        the requested scopes (incremental scope authorization,
        docs/auth-token-invariants.md A2-A4).
    """
    # HACK: ensure client_id is CampusID type
    # TODO: improve unpack_into() to support openapi schemas
    client_id = schema.CampusID(client_id)
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

    # RFC 6749 section 4.1.3: the client presenting the authorization
    # code must be the client the code was issued to
    if client_id != authsession.client_id:
        raise auth_errors.UnauthorizedClientError(
            f"Client mismatch: {client_id}"
        )

    # Span identity (#820): the token exchange runs on behalf of the
    # authorizing user even though it authenticates with client
    # credentials — stamp the user onto the span alongside the client.
    _stash_span_identity(
        client_id=authsession.client_id,
        user_id=authsession.user_id,
    )

    # Invalidate authorization code to prevent reuse (single-use guarantee)
    # Session remains alive for finalization to retrieve target URL
    resources.session[PROVIDER][authsession.id].update(
        authorization_code=INVALIDATED
    )

    # Login-journey correlation (#803): /token is a server-to-server call
    # and never carries the browser cookie, so the journey id recorded at
    # /authorize is surfaced to the tracing middleware via flask.g.
    if authsession.journey_id:
        flask.g.journey_id = authsession.journey_id

    if not authsession.user_id:
        raise auth_errors.InvalidRequestError(
            "User ID not found in auth session"
        )
    user_credentials_resource = (
        campus_cred_resource[authsession.user_id]
    )
    requested_scopes = authsession.scopes

    # Reuse an existing unexpired token only if it already covers every
    # scope of this authorization (invariant A3: never return a narrower
    # token for a wider request). Otherwise issue a token carrying the
    # union of the existing grant and the requested scopes — Campus's
    # incremental scope authorization (invariant A4). update() re-points
    # the credential at the new token and deletes the superseded record,
    # so a replaced token cannot be replayed (invariant A5).
    credentials = None
    with suppress(api_errors.NotFoundError):
        credentials = user_credentials_resource.get(authsession.client_id)

    existing_token = credentials.token if credentials else None
    if (
        existing_token is not None
        and not existing_token.is_expired()
        and scopes.covers(existing_token.scopes, requested_scopes)
    ):
        token = existing_token
    else:
        token = model.OAuthToken(
            id=secret.generate_access_token(),
            expires_in=(
                campus.config.DEFAULT_TOKEN_EXPIRY_DAYS
                * utc_time.DAY_SECONDS
            ),
            # Minted alongside the access token so confidential clients
            # can refresh without a full re-login; the refresh grant
            # reissues the same scopes (invariant A2).
            refresh_token=secret.generate_access_code(),
            scopes=scopes.union(
                existing_token.scopes if existing_token else [],
                requested_scopes,
            ),
        )
        user_credentials_resource.update(
            client_id=authsession.client_id,
            token=token,
        )
    # The token resource carries no user identity; echo the authorized
    # user from the session so confidential clients (e.g. the audit web
    # UI gate, #696) can display login state without a second lookup.
    resource = token.to_resource()
    resource["user_id"] = str(authsession.user_id)
    return resource, 200


# Proxy endpoint for login verification
@flask_campus.unpack_request
def verify_login_and_redirect(
        state: schema.CampusID,  # session id
) -> werkzeug.Response:
    """Verify if the user is logged in. Default callback handler after
    Google auth

    Method:
        GET /verify_login

    Path Parameters:
        None

    Query Parameters:
        state: CampusID - Campus session ID (preserved through Google flow)

    Responses:
        302 Found: Redirect to app callback (redirect_uri) with authorization code
        401 Not authenticated: User domain not allowed or no valid Google credential
    """
    # Get user from Flask session (set by Google OAuth callback)
    user_str = flask.session.get('user_id')
    if not user_str:
        raise auth_errors.AuthorizationError(
            "User not found in session - authentication required",
        )
    user = schema.UserID(user_str)

    # Verify domain is permitted
    if not user.domain == env.WORKSPACE_DOMAIN:
        raise token_errors.InvalidGrantError(
            "Domain not allowed",
            domain=user.domain
        )

    # Verify user has valid Google credential and get userinfo for provisioning
    google_client_id = resources.vault["google"]["CLIENT_ID"]
    google_cred = None
    try:
        google_cred = google_cred_resource[user].get(google_client_id)
    except api_errors.NotFoundError:
        # User does not have a valid Google credential/sign-in
        # TODO: Display error page
        raise auth_errors.AuthorizationError(
            "No valid Google credential found for user",
            user_id=user
        ) from None

    # Get userinfo from Google to provision user record
    # Import at runtime to avoid circular dependency - type: ignore for pyright
    from campus.auth.oauth_proxy.google import get_proxy  # type: ignore
    proxy = get_proxy()

    # Refresh Google token if expired before fetching userinfo
    token = google_cred.token
    if not token:
        raise auth_errors.AuthorizationError(
            "Google credential exists but has no access token. Please re-authenticate with Google.",
            user_id=user
        )
    if token.is_expired():
        token = proxy._oauth2.refresh_token(
            token,
            client_id=proxy._CLIENT_ID,
            client_secret=proxy._CLIENT_SECRET
        )
        # Update the stored credential with refreshed token
        resources.credentials["google"][user].update(
            client_id=proxy._CLIENT_ID,
            token=token,
        )

    userinfo = proxy._oauth2.get_user_info(token.access_token)  # type: ignore[arg-type]

    # Provision user record (auto-create if not exists)
    user_name = userinfo.get("name", "")
    if not user_name:
        # Fallback to email localpart if name is empty
        user_name = str(user).split("@")[0]
        logger.warning(
            "Google userinfo missing 'name' field for user %s, using email localpart '%s' as fallback",
            user, user_name
        )
    resources.user.get_or_create(
        email=schema.Email(user),
        name=user_name
    )

    # Generate authorization code AFTER successful Google authentication
    authorization_code = secret.generate_authorization_code()

    # Update user_id AND authorization_code for app login
    authsession = resources.session[PROVIDER][state].update(
        user_id=user,
        authorization_code=authorization_code
    )

    # Span identity (#820): after verification the flow's client and
    # the verified user are both known — stamp them onto this hop's span.
    _stash_span_identity(
        client_id=authsession.client_id,
        user_id=authsession.user_id,
    )

    # NOTE: Token creation is now handled by /token endpoint
    # This endpoint only creates the authorization code for the app to exchange
    
    # Redirect to app callback (redirect_uri, not final target)
    assert authsession.state and authsession.authorization_code
    full_redirect_url = url.add_query(
        authsession.redirect_uri or url.canonical_origin(),
        # TODO: user consent screen for scope grant
        # For now, grant all scopes
        code=authsession.authorization_code,
        state=authsession.state,
        scope=" ".join(authsession.scopes)
    )
    return flask.redirect(full_redirect_url)
