"""campus.audit.web.auth

Browser OAuth gate for the Audit Web UI (docs/web-ui-requirements.md §5).

The gated surface: all UI pages under /audit (except the public landing
page and this blueprint's static assets) and the /audit/api/* data
endpoints require a logged-in session that holds the right capability;
/audit/v1/* keeps its API-key authentication and is unaffected.

Two capabilities, and how a session earns them (#928):

- can_view_traces(): read the trace list, the trace pages and the
  /audit/api/* data endpoints.
- can_manage_keys(): manage audit API keys (mint, re-scope, rotate,
  revoke). The surface for this is the key-management page (#927).

Superadmin class (temporary stopgap until a proper admin/role gate):

- AUDIT_ADMINS: comma-separated campus.auth user ids (emails), compared
  case-insensitively; whitespace around entries is ignored. Intended
  for a handful of accounts (<= 5).
- A member of this list is a campus.audit **superadmin**: it holds
  both capabilities (manage keys, read traces). The list is read per
  request, so changes take effect without touching the login session.
- An unset or empty variable means no one has access (fail-closed,
  mirroring the OAuth credential handling below).
- Authenticated users not on the list get a 403 page (403 JSON on
  /audit/api/*). The landing page, login page, and static assets stay
  reachable without superadmin rights.

API-key sign-in (#915, development only): a second login path at
/audit/login/key accepts an audit API key (the Bearer credentials
minted via /audit/v1/apikeys) instead of the OAuth flow, so holders of
a scoped key can use the trace viewer in the browser. campus.audit
stays self-contained and user-blind: the key's owner_id is an
email-format label shown as the session identity, never resolved
against any user store.

- An API-key session is never a superadmin by virtue of existing: it
  holds exactly the capabilities its scopes grant — traces:read for
  the trace viewer, apikeys:write for key management. A key may sign in
  with either capability; each surface then checks the one it needs,
  so a key with apikeys:write gains no trace access, and a key with
  traces:read gains no key management. The session stores the key id,
  the owner label, and an expiry — never the plaintext key (cookie
  sessions are signed, not encrypted).
- Every request re-resolves the key record by id, so revocation,
  expiry, and scope changes take effect mid-session.
- The routes exist only when ENV=development (404 elsewhere), keeping
  key-based sign-in a development-environment feature by construction.
- Every sign-in is recorded in the audit trail (#917): a success emits
  audit.apikeys.auth.success with the key id, a failure emits
  audit.apikeys.auth.failed with a reason — the same event types the
  versioned API emits, so one query covers both surfaces. The
  plaintext key is never part of an event.

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

Every outcome of this flow is recorded in the audit trail (#932): a
completed sign-in emits audit.ui.auth.success with the account, a
refusal emits audit.ui.auth.failed with a reason. The event types are
distinct from the API-key sign-in's audit.apikeys.*, because a Campus
account is not an API key.

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
    "can_manage_keys",
    "can_view_traces",
    "create_blueprint",
    "current_actor",
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

# The two web-UI capabilities (#928). AUDIT_ADMINS is the campus.audit
# superadmin list — its members hold both. On the API-key side the
# same capabilities are scope-granted, so a key session is only ever
# as privileged as its scopes.
UI_READ_SCOPE = "traces:read"
UI_KEY_MANAGE_SCOPE = "apikeys:write"

# A key may sign in to the web UI with either capability; each surface
# then checks the capability it needs. apikeys:read (listing keys)
# alone is not enough to sign in — it is an API/CLI privilege, and the
# CLI already covers key listing for operators.
UI_SIGN_IN_SCOPES = (UI_READ_SCOPE, UI_KEY_MANAGE_SCOPE)

# Actor classes for audit attribution (#928): the audit trail must be
# able to tell a superadmin account apart from an API key, and name
# which one acted.
ACTOR_SUPERADMIN = "superadmin"
ACTOR_API_KEY = "api_key"

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

    Expiry alone is not sufficient for access — can_view_traces() and
    can_manage_keys() re-resolve the key record so revocation and scope
    changes apply immediately.
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


def _is_superadmin_user(user_id: str) -> bool:
    """Whether a campus.auth user id is on the superadmin allowlist."""
    return user_id.strip().lower() in _admin_emails()


def _is_superadmin_oauth() -> bool:
    """Whether the OAuth session belongs to a campus.audit superadmin.

    The AUDIT_ADMINS list is read per request, so allowlist changes
    take effect without touching the login session.
    """
    oauth = _oauth_session()
    if oauth is None:
        return False
    user_id = oauth.get("user_id")
    return isinstance(user_id, str) and _is_superadmin_user(user_id)


def _key_has_scope(key_record: typing.Any, required: str) -> bool:
    """Whether an API-key record holds a scope (wildcard-aware)."""
    return any(
        scope_matches(granted, required)
        for granted in key_record.scopes
    )


def can_view_traces() -> bool:
    """Whether the logged-in session may read traces.

    OAuth logins: the session must belong to a campus.audit superadmin
    (the AUDIT_ADMINS list) — a superadmin reads traces by definition.
    API-key logins (#915): the re-resolved key record must be active
    and hold the traces:read scope — the same read privilege
    /audit/v1/traces demands of its callers.
    """
    if _oauth_session() is not None:
        return _is_superadmin_oauth()
    key_record = _api_key()
    if key_record is None:
        return False
    return _key_has_scope(key_record, UI_READ_SCOPE)


def can_manage_keys() -> bool:
    """Whether the logged-in session may manage audit API keys.

    OAuth logins: the session must belong to a campus.audit superadmin
    (the AUDIT_ADMINS list) — managing keys is what superadmin means.
    API-key logins (#915): the re-resolved key record must be active
    and hold the apikeys:write scope — the same privilege
    /audit/v1/apikeys demands of its callers. An API key never gains
    key management by virtue of being a key: it is granted scope by
    scope, exactly like the versioned API.
    """
    if _oauth_session() is not None:
        return _is_superadmin_oauth()
    key_record = _api_key()
    if key_record is None:
        return False
    return _key_has_scope(key_record, UI_KEY_MANAGE_SCOPE)


def current_actor() -> tuple[str, str] | None:
    """Identify the acting principal of the current session.

    Returns (actor_class, actor_id):

    - ("superadmin", <campus.auth user id>) for an OAuth superadmin
      session. campus.audit has no user store and its spans carry
      user_id=None by design, so the id is a label the audit trail
      records, not an account campus.audit resolves.
    - ("api_key", <key id>) for an API-key session. The key id is
      also the span's api_key_id, so the trail attributes the action
      to the key that performed it.

    Returns None when there is no usable session. Used for audit
    attribution of web-originated actions (#917, #927).
    """
    oauth = _oauth_session()
    if oauth is not None:
        user_id = oauth.get("user_id")
        if isinstance(user_id, str) and user_id:
            return (ACTOR_SUPERADMIN, user_id)
        return None
    key_record = _api_key()
    if key_record is None:
        return None
    return (ACTOR_API_KEY, key_record.id)


def require_login_page() -> werkzeug.Response | None:
    """Before-request gate for UI page routes: redirect to login.

    Returns None to allow the request when the session is
    authenticated AND holds the trace-view capability, or when the
    request targets a public endpoint (landing page, static assets).
    An authenticated session without the capability gets a 403 page
    rather than a login redirect (re-authenticating cannot help; the
    page says which capability is missing).
    """
    if flask.request.endpoint in PUBLIC_UI_ENDPOINTS:
        return None
    if is_authenticated():
        if can_view_traces():
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
    403 JSON for a session without the trace-view capability.
    """
    if is_authenticated():
        if can_view_traces():
            return None
        identity = _session_user_id() or "unknown"
        logger.warning(
            "Audit UI data access denied for %s (no %s capability)",
            identity, UI_READ_SCOPE,
        )
        return {
            "error": (
                "Access denied: this session cannot read traces. "
                f"{_missing_capability_reason()}"
            )
        }, 403
    return {"error": "Authentication required. Visit /audit/login."}, 401


def _missing_capability_reason() -> str:
    """Explain why the current session cannot read traces.

    The two session kinds fail for different reasons, and the page
    says which: a Campus account that is not on the superadmin list
    needs an allowlist entry; an API key needs the traces:read scope.
    """
    if _oauth_session() is not None:
        return (
            "Your account is not a campus.audit superadmin. Superadmins "
            "are the accounts on the AUDIT_ADMINS list; they may manage "
            "API keys and read traces."
        )
    key_record = _api_key()
    key_id = key_record.id if key_record is not None else "unknown"
    return (
        f"Your API key ({key_id}) does not include the {UI_READ_SCOPE} "
        "scope, which the trace viewer requires."
    )


def _forbidden_page() -> flask.Response:
    """Render the 403 page for sessions without the trace capability."""
    identity = _session_user_id() or "unknown"
    logger.warning(
        "Audit UI access denied for %s (no %s capability)",
        identity, UI_READ_SCOPE,
    )
    return flask.Response(
        flask.render_template(
            "forbidden.html",
            identity=identity,
            reason=_missing_capability_reason(),
        ),
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


def _emit_sign_in_event(
        *,
        reason: str | None,
        status_code: int,
        started_at_ns: int,
        api_key_id: str | None = None,
        owner_id: str | None = None,
) -> None:
    """Record the outcome of a web UI API-key sign-in (#917).

    Emits audit.apikeys.auth.success when the key was accepted, and
    audit.apikeys.auth.failed with a reason otherwise — the same event
    types the versioned API emits for its own authentication
    (campus/audit/__init__.py), so one query answers "who signed in
    with which key, and what failed" across both surfaces.

    The plaintext key is never part of the event: it lives in the form
    body, and the event's request context reads the body as JSON
    (empty for a form POST). The owner_id label is a display string,
    never an account campus.audit resolves.
    """
    from ..helpers.audit_events import emit_web_event

    data: dict[str, typing.Any] = {
        "actor_class": ACTOR_API_KEY,
        "surface": "audit-web-signin",
    }
    if reason is None:
        event_type = "audit.apikeys.auth.success"
    else:
        event_type = "audit.apikeys.auth.failed"
        data["reason"] = reason
    if owner_id is not None:
        data["owner_id"] = owner_id
    emit_web_event(
        event_type=event_type,
        data=data,
        api_key_id=api_key_id,
        status_code=status_code,
        duration_ms=(time.perf_counter_ns() - started_at_ns) / 1_000_000,
    )


def _emit_oauth_event(
        *,
        reason: str | None,
        status_code: int,
        user_id: str | None = None,
) -> None:
    """Record the outcome of a web UI OAuth sign-in (#932).

    Emits audit.ui.auth.success when Campus Auth issued a session, and
    audit.ui.auth.failed with a reason otherwise. These are deliberately
    distinct from the audit.apikeys.* events of the API-key sign-in: a
    Campus account is not an API key, and the trail should say which
    credential authenticated.

    The campus.auth user id is a label the trail records — campus.audit
    has no user store, and its spans carry user_id=None by design — so
    it goes in the span's tags. The access token never appears: it is
    exchanged server-side and kept in the session, never in a request
    or response body.
    """
    from ..helpers.audit_events import emit_web_event

    data: dict[str, typing.Any] = {
        "actor_class": ACTOR_SUPERADMIN,
        "surface": "audit-web-oauth",
    }
    if reason is None:
        event_type = "audit.ui.auth.success"
    else:
        event_type = "audit.ui.auth.failed"
        data["reason"] = reason
    if user_id is not None:
        data["user_id"] = user_id
        # A non-superadmin can complete the flow and be refused by the
        # pages; recording that distinction makes the trail answer
        # "who tried to get in", not just "who got in".
        data["superadmin"] = _is_superadmin_user(user_id)
    emit_web_event(
        event_type=event_type,
        data=data,
        api_key_id=None,
        status_code=status_code,
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

        A session that may read traces is sent straight to the trace
        list; an authenticated session without that capability gets
        the forbidden page (re-logging in cannot help); everyone else
        sees a page with a button that starts the OAuth flow at
        /audit/login/start (a proper login page rather than an
        immediate redirect to the auth service).
        In development the page also links to the API-key sign-in
        form (#915).
        """
        if is_authenticated():
            if can_view_traces():
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
        session when the key is active and its scopes grant one of the
        web UI's capabilities (traces:read to read traces, apikeys:write
        to manage keys; #928). The plaintext key is used once for
        verification and never stored: the session carries only the key
        id, the owner_id label, and an expiry.

        Development-only by construction: both methods 404 in every
        other environment.
        """
        if not _is_development():
            flask.abort(404)
        if flask.request.method == 'GET':
            if is_authenticated() and can_view_traces():
                return flask.redirect(flask.url_for("audit_ui.traces"))
            csrf_token = secrets.token_urlsafe(32)
            flask.session[KEY_LOGIN_CSRF_KEY] = csrf_token
            return flask.render_template(
                'login_key.html', csrf_token=csrf_token
            )

        # POST: validate the CSRF token (single-use — a failed attempt
        # must not leave a valid token replayable). The comparison runs
        # on bytes: compare_digest() raises TypeError on non-ASCII str,
        # and the submitted token is raw form data.
        started_at_ns = time.perf_counter_ns()
        issued = flask.session.pop(KEY_LOGIN_CSRF_KEY, None)
        submitted = flask.request.form.get('csrf_token', '')
        if not isinstance(issued, str) or not hmac.compare_digest(
                issued.encode('utf-8'), str(submitted).encode('utf-8')):
            _emit_sign_in_event(
                reason="csrf_failed", status_code=400,
                started_at_ns=started_at_ns,
            )
            return _key_login_error(
                "Your form session expired. Please try again.", 400
            )
        api_key = (flask.request.form.get('api_key') or '').strip()
        if not api_key:
            _emit_sign_in_event(
                reason="missing_key", status_code=400,
                started_at_ns=started_at_ns,
            )
            return _key_login_error("Enter an API key.", 400)
        # One generic failure for unknown, revoked, and expired keys
        # alike, so the form does not leak which keys exist.
        record = apikeys_resource.verify(api_key)
        if record is None:
            logger.warning("Audit UI API-key sign-in failed: invalid key")
            _emit_sign_in_event(
                reason="invalid_key", status_code=401,
                started_at_ns=started_at_ns,
            )
            return _key_login_error(
                "Invalid API key. Check that you copied the full key "
                "(audit_v1_…) and that it has not been revoked or expired.",
                401,
            )
        # A key may sign in with either web-UI capability (#928); each
        # surface checks the one it needs afterwards.
        if not any(
                scope_matches(granted, required)
                for granted in record.scopes
                for required in UI_SIGN_IN_SCOPES):
            logger.warning(
                "Audit UI API-key sign-in denied: key %s lacks %s",
                record.id, " or ".join(UI_SIGN_IN_SCOPES),
            )
            _emit_sign_in_event(
                reason="insufficient_scope", status_code=403,
                api_key_id=record.id, started_at_ns=started_at_ns,
            )
            return _key_login_error(
                f"This key does not include the {UI_READ_SCOPE} scope "
                "(to read traces) or the "
                f"{UI_KEY_MANAGE_SCOPE} scope (to manage API keys).",
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
        _emit_sign_in_event(
            reason=None, status_code=302,
            api_key_id=record.id, owner_id=str(record.owner_id),
            started_at_ns=started_at_ns,
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
            _emit_oauth_event(
                reason="auth_service_unavailable", status_code=502,
            )
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
            _emit_oauth_event(
                reason="auth_service_error", status_code=400,
            )
            return _error_page(
                f"The authentication service reported: {error}", 400
            )
        pending_state = flask.session.pop(LOGIN_STATE_KEY, None)
        if not pending_state or not state or state != pending_state:
            _emit_oauth_event(
                reason="invalid_state", status_code=400,
            )
            return _error_page(
                "Invalid or expired login state. Please start again.", 400
            )
        if not code:
            _emit_oauth_event(
                reason="missing_code", status_code=400,
            )
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
            _emit_oauth_event(
                reason="auth_service_unavailable", status_code=502,
            )
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
        _emit_oauth_event(
            reason=None, status_code=302,
            user_id=flask.session[SESSION_KEY]["user_id"],
        )
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
