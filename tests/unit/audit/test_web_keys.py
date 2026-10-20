"""Unit tests for the audit web UI key-management page (#927).

These tests verify the page added in campus/audit/web/keys.py
(docs/web-ui-requirements.md §5.2):

- The page is gated on the key-management capability, not the
  trace-view one: a traces:read session is refused, a superadmin
  session and an apikeys:write key session are admitted, and an
  unauthenticated browser is sent to the login page.
- Minting shows the plaintext once, in a no-store response, and never
  stores it in the session.
- The actions (mint, re-scope, rotate, revoke) work, are CSRF-
  protected, and are recorded in the audit trail under the same event
  types the versioned API uses — attributed to the session that made
  them.

File: tests/unit/audit/test_web_keys.py
Issue: #927
"""

import os
import re
import time
import unittest
from contextlib import suppress
from unittest import mock

import flask

OWNER = "student@nyjc.edu.sg"
CSRF_INPUT_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def create_gated_app() -> flask.Flask:
    """Build an app wired like campus.audit.init_app gates the UI."""
    from campus.audit.web import auth, data, keys, ui

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

    # The key-management page carries its own gate (it must not
    # inherit the trace-view one).
    app.register_blueprint(keys.create_blueprint())

    # Test probe: report the session's capabilities and actor (#928).
    @app.get("/__capabilities")
    def capabilities():
        actor = auth.current_actor()
        return {
            "view_traces": auth.can_view_traces(),
            "manage_keys": auth.can_manage_keys(),
            "actor": list(actor) if actor else None,
        }

    return app


class TestAuditWebKeyManagement(unittest.TestCase):
    """Verify the key-management page's gate, actions and audit trail."""

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

    # Helpers ---------------------------------------------------------

    def _all_spans(self):
        from campus.audit.resources.traces import traces_storage

        return traces_storage.get_matching({}, limit=500)

    def _events(self, event_type=None):
        from tests.fixtures.audit_events import get_audit_spans

        return get_audit_spans(event_type)

    def _data(self, event):
        from tests.fixtures.audit_events import parse_audit_span_data

        return parse_audit_span_data(event)

    def _newest(self, event_type):
        events = self._events(event_type)
        self.assertTrue(events, f"no {event_type} event was emitted")
        return events[0]

    def _mint_key(self, scopes="apikeys:write", owner_id=OWNER):
        """Mint a key in-process; returns (record, plaintext)."""
        from campus.audit.resources import apikeys

        self._key_seq += 1
        return apikeys.new(
            name=f"manager key {self._key_seq}",
            owner_id=owner_id,
            scopes=scopes,
        )

    def _csrf_from(self, response) -> str:
        match = CSRF_INPUT_RE.search(response.get_data(as_text=True))
        assert match, "rendered page carries no csrf_token input"
        return match.group(1)

    def _page(self):
        """GET the page, returning (response, csrf_token)."""
        response = self.client.get("/audit/keys")
        return response, self._csrf_from(response)

    def _sign_in_with_key(self, scopes="apikeys:write"):
        """Sign in through the API-key path and return the key."""
        record, plaintext = self._mint_key(scopes=scopes)
        form = self.client.get("/audit/login/key")
        response = self.client.post(
            "/audit/login/key",
            data={
                "csrf_token": self._csrf_from(form),
                "api_key": plaintext,
            },
        )
        self.assertEqual(response.status_code, 302)
        return record, plaintext

    def _sign_in_as_superadmin(self):
        """Preset an OAuth superadmin session."""
        with self.client.session_transaction() as sess:
            sess["audit_oauth"] = {
                "access_token": "tok_superadmin",
                "expires_at": time.time() + 3600,
                "scope": "",
                "user_id": "teacher@nyjc.edu.sg",
            }

    # The gate --------------------------------------------------------

    def test_unauthenticated_browser_is_sent_to_login(self):
        """Without a session the page redirects to the login page."""
        response = self.client.get("/audit/keys")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/audit/login"))

    def test_trace_viewer_key_is_refused(self):
        """A traces:read key may read traces but not manage keys."""
        self._sign_in_with_key(scopes="traces:read")

        response = self.client.get("/audit/keys")

        self.assertEqual(response.status_code, 403)
        self.assertIn(b"apikeys:write", response.data)

    def test_key_manager_key_is_admitted(self):
        """A key holding apikeys:write reaches the page."""
        self._sign_in_with_key()

        response = self.client.get("/audit/keys")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Mint a key", response.data)

    def test_superadmin_is_admitted(self):
        """A campus.audit superadmin reaches the page."""
        self._sign_in_as_superadmin()
        with mock.patch.dict(
                os.environ, {"AUDIT_ADMINS": "teacher@nyjc.edu.sg"}
        ):
            response = self.client.get("/audit/keys")

        self.assertEqual(response.status_code, 200)

    def test_non_superadmin_account_is_refused(self):
        """An authenticated account off the superadmin list is refused."""
        self._sign_in_as_superadmin()

        response = self.client.get("/audit/keys")

        self.assertEqual(response.status_code, 403)

    # Minting --------------------------------------------------------

    def test_mint_shows_the_plaintext_once_and_stores_only_its_hash(self):
        """A minted key's plaintext appears in the response, is served
        no-store, and is never kept in the session."""
        self._sign_in_with_key()
        _, csrf = self._page()

        response = self.client.post("/audit/keys/new", data={
            "csrf_token": csrf,
            "name": "Alice's key",
            "owner_id": OWNER,
            "scopes": "traces:read",
        })

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("audit_v1_", body)
        self.assertIn("no-store", response.headers.get("Cache-Control", ""))
        plaintext = body.split("audit_v1_")[1].split('"')[0].split("<")[0]
        plaintext = f"audit_v1_{plaintext}"
        # The key authenticates, and the plaintext is not in the session.
        from campus.audit.resources import apikeys
        self.assertIsNotNone(apikeys.verify(plaintext))
        with self.client.session_transaction() as sess:
            self.assertNotIn(plaintext, repr(sess))

    def test_mint_requires_a_valid_csrf_token(self):
        """A mint without a CSRF token is refused, and mints nothing."""
        from campus.audit.resources import apikeys

        self._sign_in_with_key()
        before = len(apikeys.list_keys(owner_id=None, active_only=False))

        response = self.client.post("/audit/keys/new", data={
            "name": "Alice's key",
            "owner_id": OWNER,
            "scopes": "traces:read",
        })

        self.assertEqual(response.status_code, 400)
        after = len(apikeys.list_keys(owner_id=None, active_only=False))
        self.assertEqual(before, after)

    def test_mint_validates_its_input(self):
        """A mint without a name, an owner or a scope is refused."""
        self._sign_in_with_key()
        for form, expected in (
            ({"owner_id": OWNER, "scopes": "traces:read"}, "name"),
            ({"name": "k", "scopes": "traces:read"}, "owner"),
            ({"name": "k", "owner_id": OWNER}, "scope"),
        ):
            with self.subTest(expected=expected):
                _, csrf = self._page()
                response = self.client.post("/audit/keys/new", data={
                    "csrf_token": csrf, **form,
                })
                self.assertEqual(response.status_code, 400)

    def test_mint_rejects_a_malformed_expiry(self):
        """A malformed expiry is refused rather than stored."""
        self._sign_in_with_key()
        _, csrf = self._page()

        response = self.client.post("/audit/keys/new", data={
            "csrf_token": csrf,
            "name": "Alice's key",
            "owner_id": OWNER,
            "scopes": "traces:read",
            "expires_at": "not-a-date",
        })

        self.assertEqual(response.status_code, 400)

    # The other actions ----------------------------------------------

    def test_scopes_can_be_changed(self):
        """Re-scoping a key changes what it holds."""
        from campus.audit.resources import apikeys

        record, _ = self._mint_key(scopes="traces:read")
        self._sign_in_with_key()
        _, csrf = self._page()

        response = self.client.post(
            f"/audit/keys/{record.id}/scopes",
            data={"csrf_token": csrf, "scopes": "traces:read,traces:search"},
        )

        self.assertEqual(response.status_code, 200)
        updated = apikeys[record.id].get()
        self.assertEqual(
            sorted(updated.scopes), ["traces:read", "traces:search"]
        )

    def test_rotate_invalidates_the_old_value(self):
        """Rotating a key keeps its id and replaces its value."""
        from campus.audit.resources import apikeys

        record, plaintext = self._mint_key(scopes="traces:read")
        self._sign_in_with_key()
        _, csrf = self._page()

        response = self.client.post(
            f"/audit/keys/{record.id}/rotate", data={"csrf_token": csrf},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(apikeys.verify(plaintext))
        rotated = apikeys[record.id].get()
        self.assertIsNotNone(rotated)
        self.assertEqual(str(rotated.id), str(record.id))

    def test_revoke_disables_the_key(self):
        """Revoking a key stops it authenticating anything."""
        from campus.audit.resources import apikeys

        record, plaintext = self._mint_key(scopes="traces:read")
        self._sign_in_with_key()
        _, csrf = self._page()

        response = self.client.post(
            f"/audit/keys/{record.id}/revoke", data={"csrf_token": csrf},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(apikeys.verify(plaintext))
        self.assertIsNotNone(apikeys[record.id].get())

    def test_actions_are_refused_without_the_capability(self):
        """A trace-viewer session cannot mutate keys, even by POST."""
        record, _ = self._mint_key(scopes="traces:read")
        self._sign_in_with_key(scopes="traces:read")

        response = self.client.post(
            f"/audit/keys/{record.id}/revoke", data={"csrf_token": "x"},
        )

        self.assertEqual(response.status_code, 403)

    # The audit trail -------------------------------------------------

    def test_mint_is_recorded_for_a_key_session(self):
        """A mint is recorded and attributed to the key that made it."""
        record, _ = self._sign_in_with_key()
        _, csrf = self._page()

        self.client.post("/audit/keys/new", data={
            "csrf_token": csrf,
            "name": "Alice's key",
            "owner_id": OWNER,
            "scopes": "traces:read",
        })

        event = self._newest("audit.apikeys.new")
        data = self._data(event)
        self.assertEqual(data["actor_class"], "api_key")
        self.assertEqual(data["api_key_id"], record.id)
        self.assertEqual(data["surface"], "audit-web-keys")

    def test_mint_is_recorded_for_a_superadmin_session(self):
        """A superadmin's mint is attributed to the account."""
        self._sign_in_as_superadmin()
        with mock.patch.dict(
                os.environ, {"AUDIT_ADMINS": "teacher@nyjc.edu.sg"}
        ):
            _, csrf = self._page()
            self.client.post("/audit/keys/new", data={
                "csrf_token": csrf,
                "name": "Alice's key",
                "owner_id": OWNER,
                "scopes": "traces:read",
            })

        event = self._newest("audit.apikeys.new")
        data = self._data(event)
        self.assertEqual(data["actor_class"], "superadmin")
        self.assertEqual(data["user_id"], "teacher@nyjc.edu.sg")
        # No key authenticated this action: the account did.
        self.assertIsNone(data.get("api_key_id"))

    def test_revoke_and_rotate_are_recorded(self):
        """The other actions are recorded under the API's event types."""
        record, _ = self._mint_key(scopes="traces:read")
        self._sign_in_with_key()
        _, csrf = self._page()

        self.client.post(
            f"/audit/keys/{record.id}/rotate", data={"csrf_token": csrf},
        )
        self.assertTrue(self._events("audit.apikeys.regenerate"))

        _, csrf = self._page()
        self.client.post(
            f"/audit/keys/{record.id}/revoke", data={"csrf_token": csrf},
        )
        self.assertTrue(self._events("audit.apikeys.revoke"))

    def test_the_plaintext_never_reaches_the_audit_trail(self):
        """The minted plaintext is not in any emitted span."""
        import json

        self._sign_in_with_key()
        _, csrf = self._page()
        response = self.client.post("/audit/keys/new", data={
            "csrf_token": csrf,
            "name": "Alice's key",
            "owner_id": OWNER,
            "scopes": "traces:read",
        })
        body = response.get_data(as_text=True)
        plaintext = "audit_v1_" + body.split("audit_v1_")[1].split('"')[0]

        for event in self._events():
            self.assertNotIn(plaintext, json.dumps(event, default=str))


if __name__ == "__main__":
    unittest.main()
