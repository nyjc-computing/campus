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

API-key sign-in (#915, development only): a second login path at
/audit/login/key accepts an audit API key (the Bearer credentials
minted via /audit/v1/apikeys) instead of the OAuth flow, so holders of
a scoped key can use the trace viewer in the browser. campus.audit
stays self-contained and user-blind: the key's owner_id is an
email-format label shown as the session identity, never resolved
against any user store.

- Only keys whose scopes cover traces:read (wildcard-aware) may sign
  in; the session stores the key id, the owner label, and an expiry —
  never the plaintext key (cookie sessions are signed, not encrypted).
- Every request re-resolves the key record by id, so revocation,
  expiry, and scope changes take effect mid-session.
- The routes exist only when ENV=development (404 elsewhere), keeping
  key-based sign-in a development-environment feature by construction.

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
   session, and routes the browser through the auth service's
   /auth/v1/logout (clearing the campusauth SSO cookie, #791) back to
   the landing page.

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

import hmac
import logging
import secrets
import time
import typing

import flask
import werkzeug

import campus.flask_campus as flask_campus
from campus.common import env
from campus.common.http import DefaultClient, HttpClientError, JsonClient
from campus.common.utils import url

from ..decorators import scope_matches
from ..resources import apikeys as apikeys_resource

logger = logging.getLogger(__name__)

# Signed-cookie session keys
SESSION_KEY = "audit_oauth"
LOGIN_STATE_KEY = "audit_login_state"
# API-key sign-in (#915): a parallel session shape. Mutually exclusive
# with SESSION_KEY — signing in one way clears the other.
APIKEY_SESSION_KEY = "audit_apikey"
# CSRF token for the paste-key form (mirrors LOGIN_STATE_KEY's role)
KEY_LOGIN_CSRF_KEY = "audit_key_login_csrf"

# API-key sessions live at most 12h and never past the key's own
# expires_at; each request also re-checks revocation (see _api_key).
KEY_SESSION_TTL_SECONDS = 12 * 60 * 60

# The least scope an API key must hold to use the trace viewer —
# the same read privilege /audit/v1/traces requires of API callers.
UI_READ_SCOPE = "traces:read"

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


def _is_development() -> bool:
    """Whether API-key sign-in (#915) may exist in this deployment."""
    return env.ENV == env.DEVELOPMENT


def _oauth_session() -> dict | None:
    """Return the live OAuth session dict, if any (auth + expiry)."""
    session_data = flask.session.get(SESSION_KEY)
    if not isinstance(session_data, dict):
        return None
    access_token = session_data.get("access_token")
    expires_at = session_data.get("expires_at")
    if not access_token or not isinstance(expires_at, (int, float)):
        return None
    if not time.time() < expires_at:
        return None
    return session_data


def _api_key_session() -> dict | None:
    """Return the API-key session dict if present and unexpired.

    Expiry alone is not sufficient for access — is_admin() re-resolves
    the key record so revocation and scope changes apply immediately.
    """
    session_data = flask.session.get(APIKEY_SESSION_KEY)
    if not isinstance(session_data, dict):
        return None
    expires_at = session_data.get("expires_at")
    if not isinstance(expires_at, (int, float)) or not time.time() < expires_at:
        return None
    return session_data


def _api_key():
    """Resolve the session's API-key record, or None if it is gone.

    Re-read per request (never cached): a revoked, expired, or deleted
    key ends the session's access on the very next request. Storage
    misses raise NotFoundError, translated to None here.
    """
    from campus.storage import errors as storage_errors

    session_data = _api_key_session()
    if session_data is None:
        return None
    key_id = session_data.get("api_key_id")
    if not isinstance(key_id, str) or not key_id:
        return None
    try:
        record = apikeys_resource[key_id].get()
    except storage_errors.NotFoundError:
        return None
    if record is None or not record.is_active():
        return None
    return record


def is_authenticated() -> bool:
    """Check the Flask session for a live audit UI login (OAuth or
    API-key). API-key logins additionally require the key record to
    still be active."""
    if _oauth_session() is not None:
        return True
    return _api_key() is not None


def _session_user_id() -> str | None:
    """Return the logged-in identity, if any: the campus.auth user id
    for OAuth logins, or the key's owner_id label for API-key logins
    (a display string, never resolved against a user store)."""
    oauth = _oauth_session()
    if oauth is not None:
        user_id = oauth.get("user_id")
        if isinstance(user_id, str) and user_id:
            return user_id
        return None
    key_session = _api_key_session()
    if key_session is not None:
        owner_id = key_session.get("owner_id")
        if isinstance(owner_id, str) and owner_id:
            return owner_id
    return None


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
    """Check whether the logged-in session may use the trace viewer.

    OAuth logins: membership in the AUDIT_ADMINS allowlist (read per
    request so allowlist changes take effect without touching the
    login session). API-key logins (#915): the re-resolved key record
    must be active and hold scopes covering traces:read — the same
    read privilege the versioned API demands of its callers.
    """
    oauth = _oauth_session()
    if oauth is not None:
        user_id = oauth.get("user_id")
        return (
            isinstance(user_id, str)
            and user_id.strip().lower() in _admin_emails()
        )
    key_record = _api_key()
    if key_record is None:
        return False
    return any(
        scope_matches(granted, UI_READ_SCOPE)
        for granted in key_record.scopes
    )


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


def _key_login_error(message: str, status: int) -> flask.Response:
    """Re-render the paste-key form with an error (#915).

    A fresh CSRF token is issued each render — the form re-submits
    cleanly after any failure.
    """
    csrf_token = secrets.token_urlsafe(32)
    flask.session[KEY_LOGIN_CSRF_KEY] = csrf_token
    return flask.Response(
        flask.render_template(
            'login_key.html', error=message, csrf_token=csrf_token
        ),
        status=status,
        mimetype="text/html",
    )


def _key_expiry_epoch(record: typing.Any) -> float:
    """Convert a key record's expires_at to epoch seconds.

    Storage records carry plain strings for union-annotated fields
    (mirrors APIKey.is_expired's handling); far-future for anything
    unparseable so the session TTL never extends past a real date by
    accident of a bad value.
    """
    from campus.common import schema

    value = record.expires_at
    if isinstance(value, str):
        try:
            value = schema.DateTime(value)
        except (TypeError, ValueError):
            return float("inf")
    try:
        return value.to_datetime().timestamp()
    except (AttributeError, OverflowError, OSError, ValueError):
        return float("inf")


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
        In development the page also links to the API-key sign-in
        form (#915).
        """
        if is_authenticated():
            if is_admin():
                return flask.redirect(flask.url_for("audit_ui.traces"))
            return _forbidden_page()
        return flask.render_template(
            'login.html',
            apikey_login_available=_is_development(),
        )

    @bp.route('/login/key', methods=['GET', 'POST'])
    def login_key() -> werkzeug.Response | str:
        """Sign in with an audit API key (#915, development only).

        GET renders a paste-key form (CSRF-protected); POST verifies
        the key in-process against the apikeys store — the same
        verify() the versioned API uses — and establishes an API-key
        session when the key is active and its scopes cover
        traces:read. The plaintext key is used once for verification
        and never stored: the session carries only the key id, the
        owner_id label, and an expiry.

        Development-only by construction: both methods 404 in every
        other environment.
        """
        if not _is_development():
            flask.abort(404)
        if flask.request.method == 'GET':
            if is_authenticated() and is_admin():
                return flask.redirect(flask.url_for("audit_ui.traces"))
            csrf_token = secrets.token_urlsafe(32)
            flask.session[KEY_LOGIN_CSRF_KEY] = csrf_token
            return flask.render_template(
                'login_key.html', csrf_token=csrf_token
            )

        # POST: validate the CSRF token (single-use — a failed attempt
        # must not leave a valid token replayable).
        issued = flask.session.pop(KEY_LOGIN_CSRF_KEY, None)
        submitted = flask.request.form.get('csrf_token', '')
        if not isinstance(issued, str) or not hmac.compare_digest(
                issued, str(submitted)):
            return _key_login_error(
                "Your form session expired. Please try again.", 400
            )
        api_key = (flask.request.form.get('api_key') or '').strip()
        if not api_key:
            return _key_login_error("Enter an API key.", 400)
        # One generic failure for unknown, revoked, and expired keys
        # alike, so the form does not leak which keys exist.
        record = apikeys_resource.verify(api_key)
        if record is None:
            logger.warning("Audit UI API-key sign-in failed: invalid key")
            return _key_login_error(
                "Invalid API key. Check that you copied the full key "
                "(audit_v1_…) and that it has not been revoked or expired.",
                401,
            )
        if not any(
                scope_matches(granted, UI_READ_SCOPE)
                for granted in record.scopes):
            logger.warning(
                "Audit UI API-key sign-in denied: key %s lacks %s",
                record.id, UI_READ_SCOPE,
            )
            return _key_login_error(
                f"This key does not include the {UI_READ_SCOPE} scope "
                "needed for the trace viewer.",
                403,
            )
        # The session expiry is capped by the key's own expires_at:
        # is_expired() guards the record, but the cookie should not
        # outlive the key either.
        expires_at = time.time() + KEY_SESSION_TTL_SECONDS
        if record.expires_at is not None:
            expires_at = min(expires_at, _key_expiry_epoch(record))
        # Signing in one way clears the other: a browser moving from
        # an OAuth session to a key session (or back) should never
        # carry both.
        flask.session.pop(SESSION_KEY, None)
        flask.session[APIKEY_SESSION_KEY] = {
            "api_key_id": record.id,
            "owner_id": str(record.owner_id),
            "expires_at": expires_at,
        }
        logger.info(
            "Audit UI API-key sign-in: key %s (owner %s)",
            record.id, record.owner_id,
        )
        return flask.redirect(flask.url_for("audit_ui.traces"))

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
        # Mutual exclusivity with API-key sessions (#915): the newest
        # login wins, the browser never carries both session shapes.
        flask.session.pop(APIKEY_SESSION_KEY, None)
        return flask.redirect(flask.url_for("audit_ui.traces"))

    @bp.route('/logout')
    def logout() -> werkzeug.Response:
        """Sign the browser out of the Audit Web UI.

        OAuth sessions: revoke the access token (best-effort), clear
        the session, and route through the auth service's browser
        logout. API-key sessions (#915): clear the local session only —
        the key itself stays valid for API/CLI use; revoking it is a
        key-management action, not part of signing out of the viewer.
        """
        session_data = flask.session.pop(SESSION_KEY, None)
        key_session = flask.session.pop(APIKEY_SESSION_KEY, None)
        flask.session.pop(LOGIN_STATE_KEY, None)
        if key_session is not None and session_data is None:
            flask.flash("You have been signed out of the Audit Web UI.")
            return flask.redirect(flask.url_for("audit_ui.index"))
        if isinstance(session_data, dict) and session_data.get("access_token"):
            try:
                auth = AuthClient()
            except OSError as e:
                logger.warning("Logout could not build auth client: %s", e)
            else:
                auth.revoke_token(session_data["access_token"])
        flask.flash("You have been signed out of the Audit Web UI.")
        # Route the browser through the auth service's browser-session
        # logout (#791): the OAuth login left a live campusauth SSO
        # cookie that outlives this session. The landing page rides
        # along as post_logout_redirect_uri — the auth service honors
        # it when this deployment's origin is a registered client
        # redirect_uri origin (#789), otherwise lands on its own "/".
        auth_logout_url = url.add_query(
            f"{_get_base_url()}/auth/v1/logout",
            post_logout_redirect_uri=url.full_url_for("audit_ui.index"),
        )
        return flask.redirect(auth_logout_url)

    return bp
