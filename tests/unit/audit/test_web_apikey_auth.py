"""Unit tests for the audit web UI API-key sign-in (#915).

These tests verify the development-only API-key login path added to
campus/audit/web/auth.py (docs/web-ui-requirements.md §5.3):

- GET/POST /audit/login/key 404 outside the development environment;
  the login page links to it only in development.
- The paste form is CSRF-protected (missing/mismatched token → 400).
- A valid key with scopes covering traces:read establishes a session
  (wildcards traces:* and * qualify); the session grants the gated UI
  pages and /audit/api/* like an admin OAuth login.
- The two web-UI capabilities are separate (#928): a key holding
  apikeys:write may sign in but gains no trace access, and a key
  holding traces:read gains no key management.
- Unknown, revoked, and expired keys are refused with one generic
  401; keys lacking the read scope get 403.
- The session stores no plaintext key; revocation, scope downgrade,
  and expiry end access on the next request (record re-resolved
  per request).
- Logout for an API-key session clears the local session only (no
  auth-service hop); the key itself stays valid.

Keys are minted in-process via campus.audit.resources.apikeys (no HTTP
key-management surface needed), mirroring the operator's mint.

File: tests/unit/audit/test_web_apikey_auth.py
Issue: #915
"""

import re
import unittest
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from unittest import mock

import flask

OWNER = "student@nyjc.edu.sg"
CSRF_INPUT_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


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


class TestAuditWebAPIKeyAuth(unittest.TestCase):
    """Verify the API-key sign-in route and session gate."""

    @classmethod
    def setUpClass(cls):
        # Lazy import: campus.audit pulls in storage modules at import
        # time. See AGENTS.md - Storage Initialization Order.
        from campus.audit.resources.apikeys import APIKeysResource
        from campus.audit.resources.traces import TracesResource

        APIKeysResource.init_storage()
        TracesResource.init_storage()
        cls.app = create_gated_app()

    def setUp(self):
        import os

        # ENV=development enables the /audit/login/key route (#915 is
        # a development-only feature); individual tests override it to
        # check the 404. AUDIT_ADMINS is empty so passing these tests
        # cannot happen through the OAuth admin path.
        env_patch = mock.patch.dict(os.environ, {
            "ENV": "development",
            "PUBLIC_URL": "https://campus.test",
            "AUDIT_OAUTH_CLIENT_ID": "auditweb.test",
            "AUDIT_OAUTH_CLIENT_SECRET": "auditweb-secret",
            "AUDIT_ADMINS": "",
            # These tests do not exercise the audit trail; keep the
            # events off so their spans stay out of the shared traces
            # table (the event tests below opt in, and clean up).
            "AUDIT_EVENTS_ENABLED": "0",
        })
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.client = self.app.test_client()
        self._key_seq = 0

    def _mint_key(self, scopes="traces:read", expires_at=None):
        """Mint a key in-process; returns (record, plaintext)."""
        from campus.audit.resources import apikeys

        self._key_seq += 1
        return apikeys.new(
            name=f"unit key {self._key_seq}",
            owner_id=OWNER,
            scopes=scopes,
            expires_at=expires_at,
        )

    def _csrf_from(self, response) -> str:
        """Extract the CSRF token from a rendered paste-key form."""
        match = CSRF_INPUT_RE.search(response.get_data(as_text=True))
        assert match, "rendered form carries no csrf_token input"
        return match.group(1)

    def _sign_in(self, plaintext):
        """Drive the full GET-form → POST-key login dance."""
        form = self.client.get("/audit/login/key")
        return self.client.post(
            "/audit/login/key",
            data={
                "csrf_token": self._csrf_from(form),
                "api_key": plaintext,
            },
        )

    def _events(self, event_type):
        """Audit events of one type, newest first."""
        from tests.fixtures.audit_events import get_audit_spans

        return get_audit_spans(event_type)

    def _event_count(self):
        """Total audit events recorded so far."""
        from tests.fixtures.audit_events import get_audit_spans

        return len(get_audit_spans())

    def test_route_404_outside_development(self):
        """GET and POST /audit/login/key only exist in development."""
        import os

        for env_value in ("testing", "staging", "production"):
            with mock.patch.dict(os.environ, {"ENV": env_value}):
                self.assertEqual(
                    self.client.get("/audit/login/key").status_code, 404
                )
                self.assertEqual(
                    self.client.post(
                        "/audit/login/key", data={"api_key": "x"}
                    ).status_code,
                    404,
                )

    def test_login_page_links_key_signin_only_in_development(self):
        """The login page shows the second button only in development."""
        import os

        page = self.client.get("/audit/login")
        self.assertIn(b"/audit/login/key", page.data)

        with mock.patch.dict(os.environ, {"ENV": "testing"}):
            page = self.client.get("/audit/login")
        self.assertNotIn(b"/audit/login/key", page.data)

    def test_valid_key_signs_in_and_unlocks_ui(self):
        """A traces:read key establishes a session covering pages and
        data endpoints, with the owner label as the identity."""
        _, plaintext = self._mint_key()

        response = self._sign_in(plaintext)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/audit/traces"))
        page = self.client.get("/audit/traces")
        self.assertEqual(page.status_code, 200)
        self.assertIn(OWNER.encode(), page.data)
        data = self.client.get("/audit/api/traces")
        self.assertEqual(data.status_code, 200)
        self.assertIn("traces", data.get_json())

    def test_wildcard_scopes_qualify(self):
        """traces:* and * both satisfy the traces:read requirement."""
        for scopes in ("traces:*", "*"):
            with self.subTest(scopes=scopes):
                _, plaintext = self._mint_key(scopes=scopes)
                self.client = self.app.test_client()
                response = self._sign_in(plaintext)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(
                    self.client.get("/audit/traces").status_code, 200
                )

    def test_unknown_key_is_refused(self):
        """An unknown key gets the generic 401; no session is set."""
        response = self._sign_in("audit_v1_" + "x" * 22)
        self.assertEqual(response.status_code, 401)
        self.assertIn(b"Invalid API key", response.data)
        redirect = self.client.get("/audit/traces")
        self.assertEqual(redirect.status_code, 302)

    def test_key_without_read_scope_is_refused(self):
        """A valid key holding neither web-UI capability (traces:read,
        apikeys:write) gets 403 at login. apikeys:read alone is an
        API/CLI privilege and does not admit a browser session."""
        _, plaintext = self._mint_key(scopes="apikeys:read")

        response = self._sign_in(plaintext)

        self.assertEqual(response.status_code, 403)
        self.assertIn(b"traces:read", response.data)
        self.assertIn(b"apikeys:write", response.data)
        self.assertEqual(
            self.client.get("/audit/traces").status_code, 302
        )

    def test_key_management_key_signs_in_but_cannot_read_traces(self):
        """A key holding apikeys:write may sign in, and gains no trace
        access: the two capabilities are separate (#928)."""
        _, plaintext = self._mint_key(scopes="apikeys:write")

        response = self._sign_in(plaintext)

        self.assertEqual(response.status_code, 302)
        caps = self.client.get("/__capabilities").get_json()
        self.assertFalse(caps["view_traces"])
        self.assertTrue(caps["manage_keys"])
        # The trace surfaces refuse it...
        self.assertEqual(
            self.client.get("/audit/traces").status_code, 403
        )
        self.assertEqual(
            self.client.get("/audit/api/traces").status_code, 403
        )
        # ...and the 403 names the scope it lacks, not the allowlist.
        page = self.client.get("/audit/traces")
        self.assertIn(b"traces:read", page.data)
        self.assertNotIn(b"AUDIT_ADMINS", page.data)

    def test_trace_key_holds_no_key_management(self):
        """A traces:read key may read traces and may not manage keys
        (#928)."""
        _, plaintext = self._mint_key(scopes="traces:read")
        self._sign_in(plaintext)

        caps = self.client.get("/__capabilities").get_json()
        self.assertTrue(caps["view_traces"])
        self.assertFalse(caps["manage_keys"])
        self.assertEqual(
            self.client.get("/audit/traces").status_code, 200
        )

    def test_current_actor_names_the_key(self):
        """current_actor() reports the api_key class and the key id, so
        the audit trail attributes the action to that key (#928)."""
        from campus.audit.web import auth

        record, plaintext = self._mint_key()
        self._sign_in(plaintext)

        caps = self.client.get("/__capabilities").get_json()
        self.assertEqual(
            caps["actor"], [auth.ACTOR_API_KEY, record.id]
        )

    def test_expired_key_cannot_sign_in(self):
        """verify() rejects expired keys, so login fails with 401."""
        from campus.common import schema

        past = schema.DateTime(
            (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        )
        _, plaintext = self._mint_key(expires_at=past)

        response = self._sign_in(plaintext)

        self.assertEqual(response.status_code, 401)

    def test_revocation_ends_session_immediately(self):
        """Revoking the key mid-session un-authenticates the browser."""
        record, plaintext = self._mint_key()
        self._sign_in(plaintext)
        self.assertEqual(
            self.client.get("/audit/traces").status_code, 200
        )

        from campus.audit.resources import apikeys
        apikeys[record.id].revoke()

        self.assertEqual(
            self.client.get("/audit/traces").status_code, 302
        )
        api_data = self.client.get("/audit/api/traces")
        self.assertEqual(api_data.status_code, 401)

    def test_scope_downgrade_ends_session_access(self):
        """Removing traces:read from a live key downgrades the session
        to the 403 path on the next request."""
        record, plaintext = self._mint_key()
        self._sign_in(plaintext)

        from campus.audit.resources import apikeys
        apikeys[record.id].update(scopes=["other:read"])

        response = self.client.get("/audit/traces")
        self.assertEqual(response.status_code, 403)

    def test_session_expiry_treated_as_logged_out(self):
        """A session dict whose expires_at has passed is unauthenticated."""
        import time

        with self.client.session_transaction() as sess:
            sess["audit_apikey"] = {
                "api_key_id": "whatever",
                "owner_id": OWNER,
                "expires_at": time.time() - 1,
            }

        self.assertEqual(
            self.client.get("/audit/traces").status_code, 302
        )

    def test_session_ttl_capped_by_key_expiry(self):
        """The cookie session never outlives the key's expires_at."""
        import time

        from campus.common import schema

        soon = schema.DateTime(
            (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        )
        _, plaintext = self._mint_key(expires_at=soon)
        self._sign_in(plaintext)

        with self.client.session_transaction() as sess:
            expires_at = sess["audit_apikey"]["expires_at"]
        self.assertLessEqual(expires_at, time.time() + 3600)
        self.assertGreater(expires_at, time.time())

    def test_plaintext_key_never_stored_in_session(self):
        """The session carries id/owner/expiry only — not the key."""
        _, plaintext = self._mint_key()
        self._sign_in(plaintext)

        with self.client.session_transaction() as sess:
            key_session = dict(sess.get("audit_apikey", {}))
            raw = repr(sess)

        self.assertNotIn(plaintext, raw)
        self.assertEqual(
            sorted(key_session),
            ["api_key_id", "expires_at", "owner_id"],
        )

    def test_missing_or_mismatched_csrf_rejected(self):
        """POSTs without a valid single-use CSRF token get 400."""
        _, plaintext = self._mint_key()

        no_token = self.client.post(
            "/audit/login/key", data={"api_key": plaintext}
        )
        self.assertEqual(no_token.status_code, 400)

        form = self.client.get("/audit/login/key")
        self.client.post(  # consume the token (single-use)
            "/audit/login/key",
            data={"csrf_token": self._csrf_from(form), "api_key": ""},
        )
        stale = self.client.post(
            "/audit/login/key",
            data={"csrf_token": self._csrf_from(form), "api_key": plaintext},
        )
        self.assertEqual(stale.status_code, 400)

    def test_non_ascii_csrf_token_rejected(self):
        """A non-ASCII csrf_token gets 400, not a 500.

        hmac.compare_digest() raises TypeError when either argument
        holds non-ASCII characters, and the submitted token is raw form
        data — the comparison must run on bytes.
        """
        _, plaintext = self._mint_key()

        form = self.client.get("/audit/login/key")
        response = self.client.post(
            "/audit/login/key",
            data={
                "csrf_token": self._csrf_from(form) + "é",
                "api_key": plaintext,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self.client.get("/audit/traces").status_code, 302
        )

    def test_logout_clears_local_session_only(self):
        """API-key logout stays local: no auth-service redirect, and a
        later request is unauthenticated. The key itself stays valid —
        signing in again with it still works."""
        record, plaintext = self._mint_key()
        self._sign_in(plaintext)

        response = self.client.get("/audit/logout")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/audit/"))
        self.assertEqual(
            self.client.get("/audit/traces").status_code, 302
        )
        again = self._sign_in(plaintext)
        self.assertEqual(again.status_code, 302)

    def test_oauth_login_clears_apikey_session(self):
        """The two session shapes are mutually exclusive: completing
        the OAuth callback replaces a live key session."""
        import json
        from urllib.parse import parse_qs, urlparse

        _, plaintext = self._mint_key()
        self._sign_in(plaintext)
        self.assertEqual(
            self.client.get("/audit/traces").status_code, 200
        )

        class _Resp:
            def __init__(self, status_code, body):
                self.status_code = status_code
                self._body = body

            def json(self):
                return self._body

            @property
            def text(self):
                return json.dumps(self._body)

        class FakeAuth:
            def __init__(self, base_url=None):
                self.base_url = base_url or "https://auth.test"

            def post(self, path, json=None):
                if path == "/auth/v1/sessions/campus/":
                    return _Resp(200, {"id": "sess_1"})
                if path == "/auth/v1/token":
                    return _Resp(200, {
                        "access_token": "tok",
                        "expires_in": 3600,
                        "scope": "",
                        "user_id": "teacher@nyjc.edu.sg",
                    })
                return _Resp(404, {"error": path})

        from campus.audit.web.auth import AuthClient
        AuthClient.json_client_class = FakeAuth
        self.addCleanup(setattr, AuthClient, "json_client_class", None)

        start = self.client.get("/audit/login/start")
        state = parse_qs(urlparse(start.headers["Location"]).query)[
            "state"
        ][0]
        callback = self.client.get(
            f"/audit/callback?code=code_1&state={state}"
        )

        self.assertEqual(callback.status_code, 302)
        with self.client.session_transaction() as sess:
            self.assertNotIn("audit_apikey", sess)
            self.assertIn("audit_oauth", sess)


class TestAuditWebAPIKeySignInEvents(unittest.TestCase):
    """Verify the audit trail of the web UI API-key sign-in (#917).

    The sign-in authenticates with a real credential, so it belongs in
    the same trail the versioned API writes to: a success emits
    audit.apikeys.auth.success, a failure audit.apikeys.auth.failed
    with a reason. The plaintext key must never appear in an event.
    """

    @classmethod
    def setUpClass(cls):
        # Lazy import: campus.audit pulls in storage modules at import
        # time. See AGENTS.md - Storage Initialization Order.
        from campus.audit.resources.apikeys import APIKeysResource
        from campus.audit.resources.traces import TracesResource

        APIKeysResource.init_storage()
        TracesResource.init_storage()
        cls.app = create_gated_app()

    def setUp(self):
        import os

        env_patch = mock.patch.dict(os.environ, {
            "ENV": "development",
            "PUBLIC_URL": "https://campus.test",
            "AUDIT_OAUTH_CLIENT_ID": "auditweb.test",
            "AUDIT_OAUTH_CLIENT_SECRET": "auditweb-secret",
            "AUDIT_ADMINS": "",
            "AUDIT_EVENTS_ENABLED": "1",
        })
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.client = self.app.test_client()
        self._key_seq = 0
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

    def _all_spans(self):
        """Every span in the traces table."""
        from campus.audit.resources.traces import traces_storage

        return traces_storage.get_matching({}, limit=500)

    def _mint_key(self, scopes="traces:read"):
        from campus.audit.resources import apikeys

        self._key_seq += 1
        return apikeys.new(
            name=f"event key {self._key_seq}",
            owner_id=OWNER,
            scopes=scopes,
        )

    def _csrf_from(self, response) -> str:
        match = CSRF_INPUT_RE.search(response.get_data(as_text=True))
        assert match, "rendered form carries no csrf_token input"
        return match.group(1)

    def _sign_in(self, plaintext):
        form = self.client.get("/audit/login/key")
        return self.client.post(
            "/audit/login/key",
            data={
                "csrf_token": self._csrf_from(form),
                "api_key": plaintext,
            },
        )

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

    def test_successful_sign_in_emits_auth_success_event(self):
        """A successful sign-in emits audit.apikeys.auth.success with
        the key id and the owner label."""
        import json

        record, plaintext = self._mint_key()

        response = self._sign_in(plaintext)
        self.assertEqual(response.status_code, 302)

        event = self._newest("audit.apikeys.auth.success")
        data = self._data(event)
        self.assertEqual(data["event_type"], "audit.apikeys.auth.success")
        self.assertEqual(data["api_key_id"], record.id)
        self.assertEqual(data["actor_class"], "api_key")
        self.assertEqual(data["owner_id"], OWNER)
        self.assertEqual(data["surface"], "audit-web-signin")
        # The plaintext key is submitted in the form body, which the
        # event's request context reads as JSON (empty for a form
        # POST) — so it must not be anywhere in the event.
        self.assertNotIn(plaintext, json.dumps(event, default=str))

    def test_invalid_key_emits_auth_failed_event(self):
        """A failed sign-in emits audit.apikeys.auth.failed with a
        reason, and the attempted key never reaches the event."""
        import json

        attempted = "audit_v1_" + "x" * 22
        response = self._sign_in(attempted)
        self.assertEqual(response.status_code, 401)

        event = self._newest("audit.apikeys.auth.failed")
        data = self._data(event)
        self.assertEqual(data["event_type"], "audit.apikeys.auth.failed")
        self.assertEqual(data["reason"], "invalid_key")
        self.assertNotIn(attempted, json.dumps(event, default=str))

    def test_scope_refusal_emits_auth_failed_event(self):
        """A key that holds neither capability is refused, and the
        failure event names the key it belongs to."""
        record, plaintext = self._mint_key(scopes="apikeys:read")

        response = self._sign_in(plaintext)
        self.assertEqual(response.status_code, 403)

        event = self._newest("audit.apikeys.auth.failed")
        data = self._data(event)
        self.assertEqual(data["reason"], "insufficient_scope")
        self.assertEqual(data["api_key_id"], record.id)

    def test_missing_csrf_emits_auth_failed_event(self):
        """A POST without a valid CSRF token is refused, and recorded."""
        response = self.client.post(
            "/audit/login/key", data={"api_key": "audit_v1_" + "y" * 22}
        )
        self.assertEqual(response.status_code, 400)

        event = self._newest("audit.apikeys.auth.failed")
        data = self._data(event)
        self.assertEqual(data["reason"], "csrf_failed")

    def test_no_event_when_audit_events_disabled(self):
        """Audit events are opt-in: with AUDIT_EVENTS_ENABLED=0 the
        sign-in leaves no trace, like every other audit event."""
        import os

        record, plaintext = self._mint_key()
        with mock.patch.dict(os.environ, {"AUDIT_EVENTS_ENABLED": "0"}):
            before = len(self._events("audit.apikeys.auth.success"))
            response = self._sign_in(plaintext)
            after = len(self._events("audit.apikeys.auth.success"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
