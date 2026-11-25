"""HTTP contract tests for device-flow consent disclosure (#867).

The device verification page is the consent surface of the device
flow. Since #865 a device code may carry an explicit scope set
(campus-cli ``--scope`` pass-through) that includes management
scopes, so the page must render the pending code's requested scopes
Google-consent-style before the user authorizes — and refuse
expired/used codes instead of offering Authorize.

Contract invariants:
- A verification page pre-filled with a pending device code renders
  every requested scope (raw scope token plus a human-readable label)
  above the Authorize button, with the requesting client's name.
- An absent scope parameter (default CLI set) renders the default
  scopes the same way.
- An expired or already-used code shows a terminal notice and
  disables Authorize instead of offering it.
- A pre-filled page states when the code was requested and how long it
  stays valid, next to a status badge (#1264). For a pending code the
  badge carries the time left as the server measured it at render;
  for a code past its validity limit the badge already reads Expired,
  so the page is right without its script.
"""

import re
import unittest
from datetime import datetime

from tests.fixtures import services

MANAGEMENT_SCOPES = "clients:read clients:write clients:admin"

STATUS_BADGE = re.compile(
    r'<span id="statusBadge" class="badge badge-(?P<state>\w+)" data-state="(?P=state)"'
    r'(?P<attrs>[^>]*)role="status">(?P<label>[^<]+)</span>'
)
TIME_ELEMENT = re.compile(r'<time datetime="([^"]+)">([^<]+)</time>')


class TestDeviceVerificationConsentContract(unittest.TestCase):
    """HTTP contract tests for scope disclosure on the device page (#867)."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.auth_app

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        self.manager.clear_test_data()
        self.client = self.app.test_client()
        # Phase 2 of #865: widening a client's allowlist is an
        # operator action; the contract test performs the equivalent
        # in-process so a --scope-style device code can be minted.
        from campus.auth.resources import client as client_resource
        client_resource["guest"].update(allowed_scopes=[
            "read", "write", "clients:read", "clients:write",
            "clients:admin",
        ])

    def _create_device_code(self, scope: str | None = None) -> dict:
        """POST device_authorize and return the RFC 8628 response."""
        body = {"client_id": "guest"}
        if scope:
            body["scope"] = scope
        response = self.client.post(
            "/auth/v1/oauth/device_authorize",
            data=body,
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def _get_verification_page(self, user_code: str) -> str:
        """GET the verification page with a logged-in session."""
        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_id'] = 'contract.test@campus.test'
            response = client.get(
                f"/auth/v1/oauth/device?user_code={user_code}"
            )
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    @staticmethod
    def _at_millisecond(when) -> datetime:
        """A stored DateTime truncated to what a <time datetime> carries."""
        parsed = when.to_datetime()
        return parsed.replace(microsecond=parsed.microsecond // 1000 * 1000)

    def test_pending_code_states_when_it_was_requested(self):
        """A pending page shows the badge, the request time and the validity (#1264).

        The times must be the stored record's, so the page cannot
        disagree with when the server will expire the code. The time
        left is what the page's script counts down to flip the badge:
        positive for a just-created code and never more than the TTL.
        """
        import campus.config
        from campus.auth.resources import device_code as device_code_resource

        create_data = self._create_device_code()
        dc = device_code_resource.peek_by_user_code(create_data["user_code"])
        assert dc is not None

        page = self._get_verification_page(create_data["user_code"])

        badge = STATUS_BADGE.search(page)
        self.assertIsNotNone(badge, "status badge missing from the page")
        self.assertEqual(badge.group("state"), "pending")
        self.assertEqual(badge.group("label"), "Pending")
        validity_ms = re.search(r'data-validity-ms="(\d+)"', badge.group("attrs"))
        self.assertIsNotNone(validity_ms, "pending badge must carry the time left")
        ttl_ms = campus.config.DEFAULT_DEVICE_CODE_EXPIRY_SECONDS * 1000
        self.assertGreater(int(validity_ms.group(1)), 0)
        self.assertLessEqual(int(validity_ms.group(1)), ttl_ms)

        times = TIME_ELEMENT.findall(page)
        self.assertEqual([iso for iso, _ in times], [
            self._at_millisecond(dc.created_at).isoformat(timespec="milliseconds"),
            self._at_millisecond(dc.expires_at).isoformat(timespec="milliseconds"),
        ])
        # Without its script the page still shows both times, in UTC
        self.assertEqual([text for _, text in times], [
            self._at_millisecond(dc.created_at).strftime("%Y-%m-%d %H:%M:%S UTC"),
            self._at_millisecond(dc.expires_at).strftime("%Y-%m-%d %H:%M:%S UTC"),
        ])
        # The script reveals the expired notice here when the limit passes
        self.assertIn('id="consentNotice"', page)

    def test_expired_code_renders_expired_badge(self):
        """A code past its limit renders the Expired badge, with nothing to count down.

        Covers both ways a code can be expired: still "pending" in
        storage but past its expiry, and already flipped to "expired".
        """
        from campus.auth.resources import device_code as device_code_resource
        from campus.common import schema

        create_data = self._create_device_code()
        dc = device_code_resource.peek_by_user_code(create_data["user_code"])
        assert dc is not None
        device_code_resource.update(
            dc.id,
            expires_at=str(
                schema.DateTime.utcafter(schema.DateTime.utcnow(), seconds=-60)
            ),
        )

        for stored_state in ("pending", "expired"):
            with self.subTest(stored_state=stored_state):
                if stored_state == "expired":
                    device_code_resource.update(dc.id, state="expired")
                page = self._get_verification_page(create_data["user_code"])

                badge = STATUS_BADGE.search(page)
                self.assertIsNotNone(badge, "status badge missing from the page")
                self.assertEqual(badge.group("state"), "expired")
                self.assertEqual(badge.group("label"), "Expired")
                self.assertNotIn("data-validity-ms", badge.group("attrs"))

    def test_already_used_code_renders_used_badge(self):
        """An already-used code renders the badge as Already used."""
        create_data = self._create_device_code()

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_id'] = 'contract.test@campus.test'
            authorize_response = client.post(
                "/auth/v1/oauth/device/authorize",
                json={
                    "user_code": create_data["user_code"],
                    "user_id": "contract.test@campus.test",
                }
            )
        self.assertEqual(authorize_response.status_code, 200)

        page = self._get_verification_page(create_data["user_code"])

        badge = STATUS_BADGE.search(page)
        self.assertIsNotNone(badge, "status badge missing from the page")
        self.assertEqual(badge.group("state"), "already_used")
        self.assertEqual(badge.group("label"), "Already used")

    def test_requested_scopes_render_for_scope_style_device_code(self):
        """A --scope-style device code renders its scopes (#867).

        The page must disclose what it authorizes: every requested
        scope appears with its raw token, and management scopes get
        human-readable labels — consent without disclosure is what
        #867 closes.
        """
        create_data = self._create_device_code(scope=MANAGEMENT_SCOPES)

        page = self._get_verification_page(create_data["user_code"])

        # Raw scope tokens are on the page
        for scope in ("clients:read", "clients:write", "clients:admin"):
            self.assertIn(f"<code>{scope}</code>", page)
        # So are human-readable labels for the management vocabulary
        self.assertIn("View clients", page)
        self.assertIn("Update clients", page)
        self.assertIn("Manage clients", page)
        # The requesting client is named (Google-consent-style)
        self.assertIn("Public CLI Client", page)
        # And Authorize is offered (code is pending)
        self.assertIn('id="submitBtn"', page)
        self.assertNotIn('id="submitBtn" disabled', page)

    def test_default_scopes_render_for_absent_scope(self):
        """An absent scope (default CLI set) renders the default set."""
        create_data = self._create_device_code()

        page = self._get_verification_page(create_data["user_code"])

        self.assertIn("<code>read</code>", page)
        self.assertIn("<code>write</code>", page)
        # Curated labels for the known default vocabulary
        self.assertIn("View Campus data", page)
        self.assertIn("Manage Campus data", page)
        self.assertNotIn('id="submitBtn" disabled', page)

    def test_expired_code_shows_notice_instead_of_authorize(self):
        """An expired code surfaces a notice and disables Authorize."""
        from campus.auth.resources import device_code as device_code_resource
        from campus.common import schema

        create_data = self._create_device_code()
        dc = device_code_resource.peek_by_user_code(create_data["user_code"])
        assert dc is not None
        # Expire by clock (the realistic path: nothing re-checked the
        # code since creation, so its state is still "pending")
        device_code_resource.update(
            dc.id,
            expires_at=str(
                schema.DateTime.utcafter(
                    schema.DateTime.utcnow(), seconds=-60
                )
            ),
        )

        page = self._get_verification_page(create_data["user_code"])

        self.assertIn("has expired", page)
        self.assertIn('id="submitBtn" disabled', page)

    def test_already_used_code_shows_notice_instead_of_authorize(self):
        """An already-used code surfaces a notice and disables Authorize."""
        create_data = self._create_device_code()

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_id'] = 'contract.test@campus.test'
            authorize_response = client.post(
                "/auth/v1/oauth/device/authorize",
                json={
                    "user_code": create_data["user_code"],
                    "user_id": "contract.test@campus.test",
                }
            )
        self.assertEqual(authorize_response.status_code, 200)

        page = self._get_verification_page(create_data["user_code"])

        self.assertIn("already been used", page)
        self.assertIn('id="submitBtn" disabled', page)

    def test_page_without_prefilled_code_has_no_consent_block(self):
        """No consent block renders when the page has no user code.

        Scopes are disclosed for the code the page knows about (the
        pre-filled verification_uri_complete path); the bare entry
        form renders unchanged.
        """
        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_id'] = 'contract.test@campus.test'
            response = client.get("/auth/v1/oauth/device")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)

        self.assertNotIn("is requesting permission to", page)
        self.assertNotIn('id="submitBtn" disabled', page)
        # Nor the request-status strip, which reads the same record
        self.assertNotIn('id="statusBadge"', page)
        self.assertNotIn("<time ", page)


if __name__ == "__main__":
    unittest.main()
