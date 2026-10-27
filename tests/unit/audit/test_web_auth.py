"""Unit tests for the audit web UI OAuth gate.

These tests verify the browser OAuth gate required by
docs/web-ui-requirements.md §5 (issue #696):

- The landing page and static assets are public; every other UI page
  redirects unauthenticated requests to /audit/login.
- Unauthenticated data endpoint requests get 401 JSON.
- Authenticated users not on the AUDIT_ADMINS allowlist get a 403 page
  (403 JSON on /audit/api/*); an unset/empty allowlist denies everyone.
- AUDIT_ADMINS is the campus.audit *superadmin* list (#928): a member
  holds both web-UI capabilities (read traces, manage keys), and
  current_actor() names the actor for audit attribution.
- The gate fails closed (503/401) when the OAuth client is unconfigured
  (the landing page stays reachable).
- GET /audit/login renders the login page (authenticated visitors are
  redirected to the trace list); GET /audit/login/start creates a
  campus auth session and redirects to the auth service's authorize
  endpoint.
- The callback validates state, exchanges the code, and establishes the
  session; authenticated pages render and show login state.
- Logout revokes the token, clears the session, and redirects to the
  landing page.

The gate's auth-service transport is replaced with an in-memory fake via
AuthClient.json_client_class (mirrors AuditClient's test injection).

File: tests/unit/audit/test_web_auth.py
Issue: #696
"""

import json
import os
import time
import unittest
from contextlib import suppress
from unittest import mock
from urllib.parse import parse_qs, urlparse

import flask

from campus.audit.http.interface import JsonResponse

PUBLIC_URL = "https://campus.test"
CLIENT_ID = "auditweb.test"
CLIENT_SECRET = "auditweb-secret"
SESSION_ID = "campus_session_123"
ACCESS_TOKEN = "tok_abc123"
USER_ID = "teacher@nyjc.edu.sg"
ADMIN_ID = "ng_jun_siang@nyjc.edu.sg"


class FakeResponse(JsonResponse):
    """JSON response double for the auth transport.

    An explicit JsonResponse subclass so the client double satisfies
    JsonClient (#926); the boolean/error helpers are inherited. The
    gate only reads status_code, json(), and text.
    """

    def __init__(self, status_code: int, body: dict):
        self._status_code = status_code
        self._body = body

    @property
    def status_code(self) -> int:
        return self._status_code

    @property
    def headers(self) -> dict[str, str]:
        return {}

    def json(self) -> dict:
        return self._body

    @property
    def text(self) -> str:
        return json.dumps(self._body)


class FakeAuthClient:
    """In-memory double for the gate's campus.auth HTTP client.

    Implements the full JsonClient protocol surface so assigning it to
    AuthClient.json_client_class type-checks (#926); only post is ever
    called.
    """

    calls: list[tuple[str, dict]] = []

    def __init__(self, base_url: str | None = None, **kwargs: object):
        self.base_url: str | None = base_url or "https://auth.test"

    def get(self, path: str, params: dict | None = None) -> FakeResponse:
        return FakeResponse(404, {"error": f"unexpected path {path}"})

    def post(self, path: str, json: dict | None = None) -> FakeResponse:
        # Record {} for bodyless posts so assertions can subscript bodies.
        type(self).calls.append((path, json or {}))
        if path == "/auth/v1/sessions/campus/":
            return FakeResponse(200, {
                "id": SESSION_ID,
                "provider": "campus",
                "client_id": CLIENT_ID,
                "redirect_uri": f"{PUBLIC_URL}/audit/callback",
                "authorization_code": "code_123",
            })
        if path == "/auth/v1/token":
            return FakeResponse(200, {
                "access_token": ACCESS_TOKEN,
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "",
                "user_id": USER_ID,
            })
        if path == "/auth/v1/oauth/revoke":
            return FakeResponse(200, {})
        return FakeResponse(404, {"error": f"unexpected path {path}"})

    def put(self, path: str, json: dict | None = None) -> FakeResponse:
        return FakeResponse(404, {"error": f"unexpected path {path}"})

    def delete(self, path: str, json: dict | None = None) -> FakeResponse:
        return FakeResponse(404, {"error": f"unexpected path {path}"})

    def patch(self, path: str, json: object = None) -> FakeResponse:
        return FakeResponse(404, {"error": f"unexpected path {path}"})


def create_gated_app() -> flask.Flask:
    """Build an app wired like campus.audit.init_app gates the UI."""
    from campus.audit.web import auth, data, ui

    app = flask.Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret-key"

    ui_blueprint = ui.create_blueprint()
    ui_blueprint.before_request(auth.require_login_page)
    app.register_blueprint(ui_blueprint)

    data_blueprint = data.create_blueprint()
    data_blueprint.before_request(auth.require_login_api)
    app.register_blueprint(data_blueprint)

    app.register_blueprint(auth.create_blueprint())

    # Test probe: report the session's capabilities and actor (#928).
    # Registered outside the gated blueprints so it also answers for
    # unauthenticated sessions.
    @app.get("/__capabilities")
    def capabilities():
        actor = auth.current_actor()
        return {
            "view_traces": auth.can_view_traces(),
            "manage_keys": auth.can_manage_keys(),
            "actor": list(actor) if actor else None,
        }

    return app


class TestAuditWebAuthGate(unittest.TestCase):
    """Verify the OAuth gate's routing, session handling, and fail-closed
    behaviour."""

    @classmethod
    def setUpClass(cls):
        # Lazy import: campus.audit pulls in storage modules at import time.
        # See AGENTS.md - Storage Initialization Order.
        from campus.audit.resources.traces import TracesResource

        TracesResource.init_storage()
        cls.app = create_gated_app()

    def setUp(self):
        FakeAuthClient.calls = []
        # canonical_origin() requires PUBLIC_URL; the gate credentials
        # must be present for non-fail-closed paths. USER_ID is on the
        # admin allowlist so the authenticated tests below see 200s.
        env_patch = mock.patch.dict(os.environ, {
            # ENV is pinned: get_base_url("campus.auth") resolves to the
            # canonical origin under testing; the developer shell may
            # carry its own ENV (setdefault would not override it).
            "ENV": "testing",
            "PUBLIC_URL": PUBLIC_URL,
            "AUDIT_OAUTH_CLIENT_ID": CLIENT_ID,
            "AUDIT_OAUTH_CLIENT_SECRET": CLIENT_SECRET,
            "AUDIT_ADMINS": USER_ID,
        })
        env_patch.start()
        self.addCleanup(env_patch.stop)
        from campus.audit.web.auth import AuthClient
        AuthClient.json_client_class = FakeAuthClient
        self.addCleanup(self._reset_auth_client)
        self.client = self.app.test_client()

    def _reset_auth_client(self):
        from campus.audit.web.auth import AuthClient
        AuthClient.json_client_class = None

    def _log_in(self):
        """Preset an authenticated audit session."""
        with self.client.session_transaction() as sess:
            sess["audit_oauth"] = {
                "access_token": ACCESS_TOKEN,
                "expires_at": time.time() + 3600,
                "scope": "",
                "user_id": USER_ID,
            }

    def test_landing_page_is_public(self):
        """The landing page and static assets render without a login."""
        response = self.client.get("/audit/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Browse traces", response.data)
        static_css = self.client.get("/audit/static/css/main.css")
        self.assertEqual(static_css.status_code, 200)

    def test_unauthenticated_trace_list_redirects_to_login(self):
        """The trace list redirects unauthenticated browsers to the
        login page."""
        response = self.client.get("/audit/traces")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.headers["Location"].endswith("/audit/login")
        )

    def test_unauthenticated_trace_detail_redirects(self):
        """Detail pages are gated like the list page."""
        response = self.client.get(f"/audit/traces/{'a' * 32}")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.headers["Location"].endswith("/audit/login")
        )

    def test_unauthenticated_data_endpoint_returns_401(self):
        """/audit/api/* answers 401 JSON instead of redirecting."""
        response = self.client.get("/audit/api/traces")
        self.assertEqual(response.status_code, 401)
        self.assertIn("error", response.get_json())

    def test_non_admin_page_gets_403(self):
        """An authenticated user not on AUDIT_ADMINS gets the 403 page."""
        self._log_in()

        with mock.patch.dict(os.environ, {"AUDIT_ADMINS": ADMIN_ID}):
            response = self.client.get("/audit/traces")
            self.assertEqual(response.status_code, 403)
            self.assertIn(b"Access denied", response.data)
            self.assertIn(USER_ID.encode(), response.data)
            self.assertIn(b"AUDIT_ADMINS", response.data)
            # The landing page stays reachable; the login page shows the
            # forbidden page to the signed-in non-admin (no login loop)
            self.assertEqual(self.client.get("/audit/").status_code, 200)
            self.assertEqual(
                self.client.get("/audit/login").status_code, 403
            )

    def test_non_admin_api_gets_403_json(self):
        """A logged-in non-admin gets 403 JSON on data endpoints."""
        self._log_in()

        with mock.patch.dict(os.environ, {"AUDIT_ADMINS": ADMIN_ID}):
            response = self.client.get("/audit/api/traces")

        self.assertEqual(response.status_code, 403)
        self.assertIn("error", response.get_json())

    def test_admin_gate_fails_closed_when_unset(self):
        """An empty AUDIT_ADMINS denies even authenticated users."""
        self._log_in()

        with mock.patch.dict(os.environ, {"AUDIT_ADMINS": ""}):
            response = self.client.get("/audit/traces")

        self.assertEqual(response.status_code, 403)

    def test_admin_list_is_case_insensitive_and_tolerates_spaces(self):
        """Allowlist entries are trimmed and compared case-insensitively."""
        self._log_in()

        with mock.patch.dict(
                os.environ,
                {"AUDIT_ADMINS": f"  {USER_ID.upper()} , {ADMIN_ID} "},
        ):
            response = self.client.get("/audit/traces")

        self.assertEqual(response.status_code, 200)

    def test_superadmin_holds_both_capabilities(self):
        """A member of the superadmin list holds both capabilities:
        reading traces and managing API keys (#928)."""
        self._log_in()

        caps = self.client.get("/__capabilities").get_json()
        self.assertTrue(caps["view_traces"])
        self.assertTrue(caps["manage_keys"])

    def test_non_superadmin_holds_neither_capability(self):
        """An authenticated account off the list holds neither: the
        list is the superadmin class, so there is no lesser
        authenticated class (#928)."""
        self._log_in()

        with mock.patch.dict(os.environ, {"AUDIT_ADMINS": ADMIN_ID}):
            caps = self.client.get("/__capabilities").get_json()

        self.assertFalse(caps["view_traces"])
        self.assertFalse(caps["manage_keys"])

    def test_current_actor_names_the_superadmin(self):
        """current_actor() reports the superadmin class and the
        campus.auth user id, for audit attribution (#928)."""
        from campus.audit.web import auth

        self._log_in()

        caps = self.client.get("/__capabilities").get_json()
        self.assertEqual(
            caps["actor"], [auth.ACTOR_SUPERADMIN, USER_ID]
        )

    def test_current_actor_is_none_without_a_session(self):
        """With no session there is no actor to attribute."""
        caps = self.client.get("/__capabilities").get_json()
        self.assertIsNone(caps["actor"])
        self.assertFalse(caps["view_traces"])
        self.assertFalse(caps["manage_keys"])

    def test_forbidden_page_explains_the_missing_capability(self):
        """The 403 page says a Campus account needs the superadmin list
        (#928) rather than only 'not on the allowlist'."""
        self._log_in()

        with mock.patch.dict(os.environ, {"AUDIT_ADMINS": ADMIN_ID}):
            response = self.client.get("/audit/traces")

        self.assertEqual(response.status_code, 403)
        self.assertIn(b"superadmin", response.data)
        self.assertIn(b"AUDIT_ADMINS", response.data)

    def test_unconfigured_gate_returns_503_on_pages(self):
        """Without OAuth client config, gated pages fail closed with 503."""
        with mock.patch.dict(
                os.environ,
                {
                    "AUDIT_OAUTH_CLIENT_ID": "",
                    "AUDIT_OAUTH_CLIENT_SECRET": "",
                },
        ):
            response = self.client.get("/audit/traces")
        self.assertEqual(response.status_code, 503)
        self.assertIn(b"AUDIT_OAUTH_CLIENT_ID", response.data)

    def test_unconfigured_gate_keeps_landing_public(self):
        """Without OAuth client config, the landing page still renders."""
        with mock.patch.dict(
                os.environ,
                {
                    "AUDIT_OAUTH_CLIENT_ID": "",
                    "AUDIT_OAUTH_CLIENT_SECRET": "",
                },
        ):
            response = self.client.get("/audit/")
        self.assertEqual(response.status_code, 200)

    def test_unconfigured_gate_returns_401_on_api(self):
        """Without OAuth client config, data endpoints still 401."""
        with mock.patch.dict(
                os.environ,
                {
                    "AUDIT_OAUTH_CLIENT_ID": "",
                    "AUDIT_OAUTH_CLIENT_SECRET": "",
                },
        ):
            response = self.client.get("/audit/api/traces")
        self.assertEqual(response.status_code, 401)

    def test_login_page_renders_for_unauthenticated(self):
        """GET /audit/login renders the login page with a start link."""
        response = self.client.get("/audit/login")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Log in to Campus Audit", response.data)
        self.assertIn(b'href="/audit/login/start"', response.data)
        # No auth flow was started by rendering the page
        self.assertEqual(FakeAuthClient.calls, [])

    def test_login_page_redirects_authenticated_to_traces(self):
        """An authenticated visitor at /audit/login goes to the list."""
        self._log_in()

        response = self.client.get("/audit/login")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/audit/traces"))

    def test_login_start_creates_session_and_redirects_to_authorize(self):
        """GET /audit/login/start creates a campus session and redirects
        to the auth service authorize endpoint with the session id as
        state.
        """
        from urllib.parse import parse_qs, urlparse

        response = self.client.get("/audit/login/start")

        self.assertEqual(response.status_code, 302)
        location = response.headers["Location"]
        parsed = urlparse(location)
        self.assertTrue(parsed.path.endswith("/auth/v1/authorize"))
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        self.assertEqual(params["client_id"], CLIENT_ID)
        self.assertEqual(params["response_type"], "code")
        self.assertEqual(params["redirect_uri"],
                         f"{PUBLIC_URL}/audit/callback")
        self.assertEqual(params["state"], SESSION_ID)
        # A campus auth session was created server-side
        session_posts = [
            (path, body) for path, body in FakeAuthClient.calls
            if path == "/auth/v1/sessions/campus/"
        ]
        self.assertEqual(len(session_posts), 1)
        self.assertEqual(session_posts[0][1]["client_id"], CLIENT_ID)
        self.assertEqual(session_posts[0][1]["redirect_uri"],
                         f"{PUBLIC_URL}/audit/callback")
        # The pending state is kept for the callback's CSRF check
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["audit_login_state"], SESSION_ID)

    def test_callback_exchanges_code_and_establishes_session(self):
        """A valid callback exchanges the code and logs the user in."""
        with self.client.session_transaction() as sess:
            sess["audit_login_state"] = SESSION_ID

        response = self.client.get(
            "/audit/callback",
            query_string={"code": "code_123", "state": SESSION_ID},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/audit/traces"))
        # The code was exchanged confidentially (client_secret present)
        token_posts = [
            (path, body) for path, body in FakeAuthClient.calls
            if path == "/auth/v1/token"
        ]
        self.assertEqual(len(token_posts), 1)
        self.assertEqual(token_posts[0][1]["code"], "code_123")
        self.assertEqual(token_posts[0][1]["client_id"], CLIENT_ID)
        self.assertEqual(token_posts[0][1]["client_secret"], CLIENT_SECRET)
        # The login lives in the session, including the user identity
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["audit_oauth"]["access_token"],
                             ACCESS_TOKEN)
            self.assertEqual(sess["audit_oauth"]["user_id"], USER_ID)

    def test_authenticated_page_renders_with_login_state(self):
        """After login, pages render and the header shows the user and
        logout control (spec §2)."""
        self._log_in()

        response = self.client.get("/audit/traces")

        self.assertEqual(response.status_code, 200)
        self.assertIn(USER_ID.encode(), response.data)
        self.assertIn(b"/audit/logout", response.data)

    def test_authenticated_data_endpoint_serves_traces(self):
        """After login, data endpoints return trace data (200)."""
        self._log_in()

        response = self.client.get("/audit/api/traces")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertIsInstance(body["traces"], list)

    def test_callback_rejects_state_mismatch(self):
        """A state that does not match the pending login is rejected."""
        with self.client.session_transaction() as sess:
            sess["audit_login_state"] = SESSION_ID

        response = self.client.get(
            "/audit/callback",
            query_string={"code": "code_123", "state": "forged_state"},
        )

        self.assertEqual(response.status_code, 400)
        token_posts = [
            (path, body) for path, body in FakeAuthClient.calls
            if path == "/auth/v1/token"
        ]
        self.assertEqual(token_posts, [])

    def test_callback_rejects_missing_pending_state(self):
        """A callback without a pending login (e.g. replayed URL) is
        rejected."""
        response = self.client.get(
            "/audit/callback",
            query_string={"code": "code_123", "state": SESSION_ID},
        )
        self.assertEqual(response.status_code, 400)

    def test_callback_reports_oauth_error(self):
        """An error redirect from the auth service surfaces as 400."""
        with self.client.session_transaction() as sess:
            sess["audit_login_state"] = SESSION_ID

        response = self.client.get(
            "/audit/callback",
            query_string={"error": "access_denied",
                          "state": SESSION_ID},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"access_denied", response.data)

    def test_logout_clears_session_revokes_token_and_redirects(self):
        """Logout revokes the token, routes the browser through the
        auth-service logout carrying the landing target (#791), and
        re-gates the protected pages."""
        self._log_in()

        response = self.client.get("/audit/logout")

        self.assertEqual(response.status_code, 302)
        location = urlparse(response.headers["Location"])
        self.assertEqual(location.scheme + "://" + location.netloc, PUBLIC_URL)
        self.assertEqual(location.path, "/auth/v1/logout")
        self.assertEqual(
            parse_qs(location.query)["post_logout_redirect_uri"],
            [f"{PUBLIC_URL}/audit/"]
        )
        revoke_posts = [
            (path, body) for path, body in FakeAuthClient.calls
            if path == "/auth/v1/oauth/revoke"
        ]
        self.assertEqual(len(revoke_posts), 1)
        self.assertEqual(revoke_posts[0][1]["token"], ACCESS_TOKEN)
        with self.client.session_transaction() as sess:
            self.assertNotIn("audit_oauth", sess)
        # The landing page shows the signed-out confirmation...
        landing = self.client.get("/audit/", follow_redirects=True)
        self.assertEqual(landing.status_code, 200)
        self.assertIn(b"signed out", landing.data)
        # ...and protected routes are inaccessible again
        response = self.client.get("/audit/traces")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.headers["Location"].endswith("/audit/login")
        )

    def test_expired_session_token_is_logged_out(self):
        """An expired access token in the session counts as logged out."""
        with self.client.session_transaction() as sess:
            sess["audit_oauth"] = {
                "access_token": ACCESS_TOKEN,
                "expires_at": time.time() - 1,
                "scope": "",
                "user_id": USER_ID,
            }

        response = self.client.get("/audit/traces")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.headers["Location"].endswith("/audit/login")
        )


class TestAdminAllowlistParsing(unittest.TestCase):
    """Verify AUDIT_ADMINS parsing (comma-separated emails,
    case-insensitive, whitespace-tolerant, fail-closed when unset)."""

    def test_entries_are_trimmed_lowercased_and_empties_ignored(self):
        from campus.audit.web import auth

        with mock.patch.dict(
                os.environ,
                {"AUDIT_ADMINS": " A@Example.com ,b@nyjc.edu.sg,, "},
        ):
            self.assertEqual(
                auth._admin_emails(),
                frozenset({"a@example.com", "b@nyjc.edu.sg"}),
            )

    def test_unset_or_empty_variable_allows_no_one(self):
        from campus.audit.web import auth

        env_without_admins = {k: v for k, v in os.environ.items()
                              if k != "AUDIT_ADMINS"}
        with mock.patch.dict(os.environ, env_without_admins, clear=True):
            self.assertEqual(auth._admin_emails(), frozenset())
        with mock.patch.dict(os.environ, {"AUDIT_ADMINS": "  "}):
            self.assertEqual(auth._admin_emails(), frozenset())


class FailingAuthClient:
    """Auth-service double that always fails, for the error paths.

    Full JsonClient surface, like FakeAuthClient (#926); only post is
    ever called.
    """

    def __init__(self, base_url: str | None = None, **kwargs: object):
        self.base_url: str | None = base_url or "https://auth.test"

    def get(self, path: str, params: dict | None = None) -> FakeResponse:
        return FakeResponse(500, {"error": "auth service is down"})

    def post(self, path: str, json: dict | None = None) -> FakeResponse:
        return FakeResponse(500, {"error": "auth service is down"})

    def put(self, path: str, json: dict | None = None) -> FakeResponse:
        return FakeResponse(500, {"error": "auth service is down"})

    def delete(self, path: str, json: dict | None = None) -> FakeResponse:
        return FakeResponse(500, {"error": "auth service is down"})

    def patch(self, path: str, json: object = None) -> FakeResponse:
        return FakeResponse(500, {"error": "auth service is down"})


class TestAuditWebOAuthSignInEvents(unittest.TestCase):
    """Verify the audit trail of the web UI OAuth sign-in (#932).

    A superadmin signing in through Campus Auth authenticates the
    browser, but no credential of its own — the trail records the
    account, not a key. The event types are therefore distinct from
    the API-key sign-in's audit.apikeys.*: audit.ui.auth.*.
    """

    @classmethod
    def setUpClass(cls):
        # Lazy import: campus.audit pulls in storage modules at import
        # time. See AGENTS.md - Storage Initialization Order.
        from campus.audit.resources.traces import TracesResource

        TracesResource.init_storage()
        cls.app = create_gated_app()

    def setUp(self):
        FakeAuthClient.calls = []
        env_patch = mock.patch.dict(os.environ, {
            "ENV": "testing",
            "PUBLIC_URL": PUBLIC_URL,
            "AUDIT_OAUTH_CLIENT_ID": CLIENT_ID,
            "AUDIT_OAUTH_CLIENT_SECRET": CLIENT_SECRET,
            "AUDIT_ADMINS": USER_ID,
            "AUDIT_EVENTS_ENABLED": "1",
        })
        env_patch.start()
        self.addCleanup(env_patch.stop)
        from campus.audit.web.auth import AuthClient
        AuthClient.json_client_class = FakeAuthClient
        self.addCleanup(self._reset_auth_client)
        self.client = self.app.test_client()
        # The events land in the shared traces table, which other unit
        # tests expect to be empty — remember what was there so
        # tearDown can remove only what this test added.
        self._spans_before = {s["id"] for s in self._all_spans()}

    def tearDown(self):
        from campus.audit.resources.traces import traces_storage
        from campus.storage import errors as storage_errors

        for span in self._all_spans():
            if span["id"] in self._spans_before:
                continue
            with suppress(storage_errors.NotFoundError):
                traces_storage.delete_by_id(span["id"])

    def _reset_auth_client(self):
        from campus.audit.web.auth import AuthClient
        AuthClient.json_client_class = None

    def _all_spans(self):
        """Every span in the traces table."""
        from campus.audit.resources.traces import traces_storage

        return traces_storage.get_matching({}, limit=500)

    def _events(self, event_type):
        from tests.fixtures.audit_events import get_audit_spans

        return get_audit_spans(event_type)

    def _data(self, event):
        """The event's tags plus its api_key_id."""
        from tests.fixtures.audit_events import parse_audit_span_data

        return parse_audit_span_data(event)

    def _newest(self, event_type):
        events = self._events(event_type)
        self.assertTrue(events, f"no {event_type} event was emitted")
        return events[0]

    def _callback(self, **query):
        """Drive the callback with a pending login state."""
        with self.client.session_transaction() as sess:
            sess["audit_login_state"] = SESSION_ID
        query.setdefault("code", "code_123")
        query.setdefault("state", SESSION_ID)
        return self.client.get("/audit/callback", query_string=query)

    def test_successful_sign_in_emits_auth_success_event(self):
        """A completed OAuth sign-in emits audit.ui.auth.success with
        the account and whether it is a superadmin."""
        import json

        response = self._callback()

        self.assertEqual(response.status_code, 302)
        event = self._newest("audit.ui.auth.success")
        data = self._data(event)
        self.assertEqual(data["event_type"], "audit.ui.auth.success")
        self.assertEqual(data["actor_class"], "superadmin")
        self.assertEqual(data["surface"], "audit-web-oauth")
        self.assertEqual(data["user_id"], USER_ID)
        self.assertTrue(data["superadmin"])
        # The access token is exchanged server-side and kept in the
        # session: it must not appear in the event.
        self.assertNotIn(ACCESS_TOKEN, json.dumps(event, default=str))

    def test_state_mismatch_emits_auth_failed_event(self):
        """A callback whose state does not match is refused, and the
        failure is recorded."""
        response = self._callback(state="forged_state")

        self.assertEqual(response.status_code, 400)
        event = self._newest("audit.ui.auth.failed")
        data = self._data(event)
        self.assertEqual(data["event_type"], "audit.ui.auth.failed")
        self.assertEqual(data["reason"], "invalid_state")

    def test_missing_code_emits_auth_failed_event(self):
        """A callback without a code is refused, and recorded."""
        response = self._callback(code="")

        self.assertEqual(response.status_code, 400)
        event = self._newest("audit.ui.auth.failed")
        self.assertEqual(self._data(event)["reason"], "missing_code")

    def test_auth_service_error_emits_auth_failed_event(self):
        """An error reported by the auth service is refused, and
        recorded."""
        response = self._callback(error="access_denied")

        self.assertEqual(response.status_code, 400)
        event = self._newest("audit.ui.auth.failed")
        self.assertEqual(self._data(event)["reason"], "auth_service_error")

    def test_auth_service_unavailable_emits_auth_failed_event(self):
        """A login that cannot even start is recorded too."""
        from campus.audit.web.auth import AuthClient

        AuthClient.json_client_class = FailingAuthClient

        response = self.client.get("/audit/login/start")

        self.assertEqual(response.status_code, 502)
        event = self._newest("audit.ui.auth.failed")
        self.assertEqual(
            self._data(event)["reason"], "auth_service_unavailable"
        )

    def test_non_superadmin_sign_in_is_marked_as_such(self):
        """An account off the superadmin list can complete the flow; the
        event says so, so the trail answers "who tried to get in"."""
        with mock.patch.dict(os.environ, {"AUDIT_ADMINS": "other@nyjc.edu.sg"}):
            response = self._callback()

        self.assertEqual(response.status_code, 302)
        event = self._newest("audit.ui.auth.success")
        data = self._data(event)
        self.assertEqual(data["user_id"], USER_ID)
        self.assertFalse(data["superadmin"])

    def test_no_event_when_audit_events_disabled(self):
        """Audit events are opt-in, like every other audit event."""
        with mock.patch.dict(os.environ, {"AUDIT_EVENTS_ENABLED": "0"}):
            before = len(self._events("audit.ui.auth.success"))
            response = self._callback()
            after = len(self._events("audit.ui.auth.success"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
