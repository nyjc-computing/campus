"""campus.audit.web.auth

Browser OAuth gate for the Audit Web UI (docs/web-ui-requirements.md §5).

The gated surface: all UI pages under /audit (except the public landing
page and this blueprint's static assets) and the /audit/api/* data
endpoints require a logged-in user who is on the admin allowlist;
/audit/v1/* keeps its API-key authentication and is unaffected.

Admin allowlist (temporary stopgap until a proper admin/role gate):

- AUDIT_ADMINS: comma-separated campus.auth user ids (emails), compared
  case-insensitively; whitespace around entries is ignored. Intended
  for a handful of accounts (<= 5).
- An unset or empty variable means no one has access (fail-closed,
  mirroring the OAuth credential handling below).
- Authenticated users not on the list get a 403 page (403 JSON on
  /audit/api/*). The landing page, login page, and static assets stay
  reachable without admin rights.

The gate drives Campus Auth's authorization-code flow (RFC 6749 §4.1,
campus.auth.provider) server-side:

1. GET /audit/login renders a login page; its button links to
   GET /audit/login/start, which creates a campus auth session
   (server-to-server) and redirects the browser to the auth service's
   /auth/v1/authorize.
2. Campus Auth authenticates the user (Google Workspace), then redirects
   to GET /audit/callback with a single-use authorization code.
3. GET /audit/callback exchanges the code at /auth/v1/token (confidential
   client) and stores the token and user identity in the signed Flask
   cookie session, then sends the browser to the trace list. The token
   is never exposed to browser JS.
4. GET /audit/logout revokes the token (best-effort), clears the
   session, and redirects to the landing page.

Configuration (fail-closed: the UI is unusable without it):

- AUDIT_OAUTH_CLIENT_ID: the audit deployment's confidential OAuth client
  registered in campus.auth, with the callback URL
  ``{PUBLIC_URL}/audit/callback`` in its redirect_uris (#685 enforces
  exact-match validation).
- AUDIT_OAUTH_CLIENT_SECRET: the client's secret.

These are explicit variables rather than the ambient CLIENT_ID/CLIENT_
SECRET pair so the UI gate's credentials cannot collide with other
DefaultClient consumers (same reasoning as AUDIT_API_KEY in #699).

Test injection: set ``AuthClient.json_client_class`` to route the gate's
auth-service requests through a test double, mirroring AuditClient.
"""

__all__ = [
    "AuthClient",
    "create_blueprint",
    "is_admin",
    "is_authenticated",
    "require_login_api",
    "require_login_page",
]

import logging
import time
import typing

import flask
import werkzeug

import campus.flask_campus as flask_campus
from campus.common import env
from campus.common.http import DefaultClient, HttpClientError, JsonClient
from campus.common.utils import url

logger = logging.getLogger(__name__)

# Signed-cookie session keys
SESSION_KEY = "audit_oauth"
LOGIN_STATE_KEY = "audit_login_state"

# UI endpoints reachable without a login: the landing page and the UI
# blueprint's static assets (the landing and login pages need their CSS
# and JS). Everything else under /audit requires a login session.
PUBLIC_UI_ENDPOINTS = frozenset({"audit_ui.index", "audit_ui.static"})

# Campus Auth endpoints (paths are appended to the auth service origin)
_AUTHORIZE_PATH = "/auth/v1/authorize"
_SESSIONS_PATH = "/auth/v1/sessions/campus/"
_TOKEN_PATH = "/auth/v1/token"
_REVOKE_PATH = "/auth/v1/oauth/revoke"

# Scopes are not yet enforced by the auth provider's consent flow; the
# session is created with none and the issued token inherits [].
_SCOPES: list[str] = []


def _get_base_url() -> str:
    """Get the campus.auth service origin for the current environment."""
    import campus.config

    return campus.config.get_base_url("campus.auth")


def _client_credentials() -> tuple[str, str]:
    """Return the audit deployment's OAuth client credentials.

    Raises:
        OSError: if either credential variable is unset.
    """
    client_id = env.get("AUDIT_OAUTH_CLIENT_ID")
    client_secret = env.get("AUDIT_OAUTH_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise OSError(
            "Audit web UI OAuth gate is not configured: set "
            "AUDIT_OAUTH_CLIENT_ID and AUDIT_OAUTH_CLIENT_SECRET "
            "(a confidential client registered in campus.auth with "
            f"{get_redirect_uri()} in its redirect_uris)"
        )
    return client_id, client_secret


def get_redirect_uri() -> str:
    """Get this deployment's OAuth callback URL (the registered
    redirect_uri): ``{PUBLIC_URL}/audit/callback``.
    """
    return f"{url.canonical_origin()}/audit/callback"


class AuthClient:
    """HTTP client for the campus.auth OAuth endpoints used by the gate.

    The transport may be swapped for tests via the ``json_client_class``
    class attribute (mirrors campus.audit.client.AuditClient).
    """

    json_client_class: type[JsonClient] | None = None

    def __init__(self, base_url: str | None = None) -> None:
        """Initialize the auth client.

        Args:
            base_url: Override the auth service origin (defaults to the
                environment-appropriate deployment URL).
        """
        self.base_url = base_url or _get_base_url()
        client_id, client_secret = _client_credentials()
        self.client_id = client_id
        self.client_secret = client_secret
        client_class = type(self).json_client_class
        if client_class is not None:
            self._client = client_class(base_url=self.base_url)
        else:
            self._client = DefaultClient(
                base_url=self.base_url,
                auth=(client_id, client_secret),
            )

    def create_authorization_session(self, redirect_uri: str) -> str:
        """Create a campus auth session and return its id (the OAuth
        ``state`` value for /auth/v1/authorize).

        Raises:
            HttpClientError: on auth service errors.
        """
        response = self._client.post(
            _SESSIONS_PATH,
            json={
                "client_id": self.client_id,
                "redirect_uri": redirect_uri,
                "scopes": _SCOPES,
            },
        )
        if response.status_code != 200:
            raise HttpClientError(
                f"Session creation failed ({response.status_code}): "
                f"{response.text[:200]}"
            )
        session_id = response.json().get("id")
        if not session_id:
            raise HttpClientError(
                f"Session creation returned no session id: "
                f"{response.text[:200]}"
            )
        return str(session_id)

    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """Exchange an authorization code for a token resource.

        Returns:
            The token response dict (id/access_token, expires_at,
            expires_in, scope, user_id, ...).

        Raises:
            HttpClientError: on auth service errors.
        """
        response = self._client.post(
            _TOKEN_PATH,
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        if response.status_code != 200:
            raise HttpClientError(
                f"Code exchange failed ({response.status_code}): "
                f"{response.text[:200]}"
            )
        token = response.json()
        if not token.get("access_token") and not token.get("id"):
            raise HttpClientError(
                f"Token response missing access token: "
                f"{response.text[:200]}"
            )
        return token

    def revoke_token(self, token: str) -> None:
        """Revoke an access token (RFC 7009). Best-effort: errors are
        logged and swallowed so logout never fails on auth downtime.

        The auth service returns 200 regardless of token state, so no
        status handling is needed.
        """
        try:
            response = self._client.post(
                _REVOKE_PATH,
                json={"token": token, "client_id": self.client_id},
            )
        except HttpClientError as e:
            logger.warning("Token revocation failed during logout: %s", e)
            return
        if response.status_code != 200:
            logger.warning(
                "Token revocation returned %s during logout",
                response.status_code,
            )


def is_authenticated() -> bool:
    """Check the Flask session for a live audit UI login."""
    session_data = flask.session.get(SESSION_KEY)
    if not isinstance(session_data, dict):
        return False
    access_token = session_data.get("access_token")
    expires_at = session_data.get("expires_at")
    if not access_token or not isinstance(expires_at, (int, float)):
        return False
    return bool(time.time() < expires_at)


def _session_user_id() -> str | None:
    """Return the logged-in user's campus.auth user id, if any."""
    session_data = flask.session.get(SESSION_KEY)
    if not isinstance(session_data, dict):
        return None
    user_id = session_data.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        return None
    return user_id


def _admin_emails() -> frozenset[str]:
    """Parse the AUDIT_ADMINS allowlist.

    The variable holds comma-separated campus.auth user ids (emails).
    Entries are trimmed and compared case-insensitively; empty entries
    are ignored. An unset or empty variable allows no one (fail-closed).
    """
    raw = env.get("AUDIT_ADMINS") or ""
    return frozenset(
        entry.strip().lower() for entry in raw.split(",") if entry.strip()
    )


def is_admin() -> bool:
    """Check whether the logged-in user is on the AUDIT_ADMINS
    allowlist.

    Read per-request so allowlist changes take effect without touching
    the login session.
    """
    user_id = _session_user_id()
    return user_id is not None and user_id.strip().lower() in _admin_emails()


def require_login_page() -> werkzeug.Response | None:
    """Before-request gate for UI page routes: redirect to login.

    Returns None to allow the request when the user is authenticated
    AND on the admin allowlist, or when the request targets a public
    endpoint (landing page, static assets). Authenticated non-admins
    get a 403 page rather than a login redirect (re-authenticating
    cannot help; the page tells them how to get access).
    """
    if flask.request.endpoint in PUBLIC_UI_ENDPOINTS:
        return None
    if is_authenticated():
        if is_admin():
            return None
        return _forbidden_page()
    try:
        _client_credentials()
    except OSError as e:
        return flask.Response(
            f"<h1>Audit Web UI unavailable</h1><p>{e}</p>",
            status=503,
            mimetype="text/html",
        )
    return flask.redirect(flask.url_for("audit_auth.login"))


def require_login_api() -> flask_campus.JsonResponse | werkzeug.Response | None:
    """Before-request gate for UI data endpoints: 401 JSON when not
    logged in (browsers redirect pages; fetch() callers get 401), and
    403 JSON for logged-in non-admins.
    """
    if is_authenticated():
        if is_admin():
            return None
        user_id = _session_user_id() or "unknown"
        logger.warning(
            "Audit UI data access denied for non-admin user %s", user_id
        )
        return {
            "error": (
                "Admin access required: this account is not on the "
                "audit admin allowlist."
            )
        }, 403
    return {"error": "Authentication required. Visit /audit/login."}, 401


def _forbidden_page() -> flask.Response:
    """Render the 403 page for authenticated non-admin visitors."""
    user_id = _session_user_id() or "unknown"
    logger.warning("Audit UI access denied for non-admin user %s", user_id)
    return flask.Response(
        flask.render_template("forbidden.html", user_id=user_id),
        status=403,
        mimetype="text/html",
    )


def _error_page(message: str, status: int) -> flask.Response:
    """Render a minimal HTML error page for login flow failures."""
    return flask.Response(
        f"<h1>Login failed</h1><p>{message}</p>"
        f'<p><a href="/audit/login">Try again</a></p>',
        status=status,
        mimetype="text/html",
    )


def create_blueprint() -> flask.Blueprint:
    """Create a Flask blueprint for the OAuth gate routes.

    Returns:
        A Flask blueprint with login/callback/logout route handlers
    """
    bp = flask.Blueprint(
        'audit_auth',
        __name__,
        url_prefix='/audit',
    )

    @bp.route('/login')
    def login() -> werkzeug.Response | str:
        """Render the login page.

        Authenticated admins are sent straight to the trace list;
        authenticated non-admins get the forbidden page (re-logging in
        cannot help); everyone else sees a page with a button that
        starts the OAuth flow at /audit/login/start (a proper login
        page rather than an immediate redirect to the auth service).
        """
        if is_authenticated():
            if is_admin():
                return flask.redirect(flask.url_for("audit_ui.traces"))
            return _forbidden_page()
        return flask.render_template('login.html')

    @bp.route('/login/start')
    def login_start() -> werkzeug.Response:
        """Start the browser OAuth flow.

        Creates a campus auth session (its id serves as the OAuth state)
        and redirects the browser to the auth service's authorize
        endpoint. Campus Auth then authenticates the user via Google
        Workspace and redirects back to /audit/callback.
        """
        redirect_uri = get_redirect_uri()
        try:
            auth = AuthClient()
            session_id = auth.create_authorization_session(redirect_uri)
        except (OSError, HttpClientError) as e:
            logger.error("Login initiation failed: %s", e)
            return _error_page(
                "Could not start the login flow. "
                "The authentication service may be unavailable.",
                502,
            )
        # Single pending login per browser session; compared against the
        # state echoed back by the auth service (CSRF protection).
        flask.session[LOGIN_STATE_KEY] = session_id
        authorize_url = url.add_query(
            f"{auth.base_url}{_AUTHORIZE_PATH}",
            client_id=auth.client_id,
            response_type="code",
            redirect_uri=redirect_uri,
            state=session_id,
        )
        return flask.redirect(authorize_url)

    @bp.route('/callback')
    def callback() -> werkzeug.Response:
        """Handle the auth service redirect back from login.

        Validates the state, exchanges the authorization code for a
        token, and stores the login in the Flask session.
        """
        code = flask.request.args.get("code")
        state = flask.request.args.get("state")
        error = flask.request.args.get("error")
        if error:
            return _error_page(
                f"The authentication service reported: {error}", 400
            )
        pending_state = flask.session.pop(LOGIN_STATE_KEY, None)
        if not pending_state or not state or state != pending_state:
            return _error_page(
                "Invalid or expired login state. Please start again.", 400
            )
        if not code:
            return _error_page(
                "The authentication service did not return an "
                "authorization code.",
                400,
            )
        try:
            auth = AuthClient()
            token = auth.exchange_code(code, get_redirect_uri())
        except (OSError, HttpClientError) as e:
            logger.error("Authorization code exchange failed: %s", e)
            return _error_page(
                "Could not complete the login flow. "
                "The authentication service may be unavailable.",
                502,
            )
        # RFC 6749 token responses carry access_token; the campus token
        # resource uses id for the token string (see OAuthToken).
        access_token = token.get("access_token") or token.get("id")
        try:
            expires_in = int(token.get("expires_in") or 0)
        except (TypeError, ValueError):
            expires_in = 0
        flask.session[SESSION_KEY] = {
            "access_token": typing.cast(str, access_token),
            "expires_at": time.time() + expires_in,
            "scope": token.get("scope") or "",
            "user_id": token.get("user_id") or "unknown",
        }
        return flask.redirect(flask.url_for("audit_ui.traces"))

    @bp.route('/logout')
    def logout() -> werkzeug.Response:
        """Revoke the access token (best-effort), clear the session,
        and return the visitor to the landing page.
        """
        session_data = flask.session.pop(SESSION_KEY, None)
        flask.session.pop(LOGIN_STATE_KEY, None)
        if isinstance(session_data, dict) and session_data.get("access_token"):
            try:
                auth = AuthClient()
            except OSError as e:
                logger.warning("Logout could not build auth client: %s", e)
            else:
                auth.revoke_token(session_data["access_token"])
        flask.flash("You have been signed out of the Audit Web UI.")
        return flask.redirect(flask.url_for("audit_ui.index"))

    return bp
