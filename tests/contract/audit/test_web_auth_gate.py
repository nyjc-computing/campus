"""HTTP contract tests for the audit web UI OAuth gate.

These tests verify the browser OAuth gate contract required by
docs/web-ui-requirements.md §5 (issue #696):

- The landing page (/audit/) is public; other UI pages redirect
  unauthenticated requests to /audit/login.
- Unauthenticated requests to /audit/api/* data endpoints get 401 JSON.
- An authenticated session for a user not on AUDIT_ADMINS gets 403
  (page and JSON).
- /audit/v1/health stays publicly reachable (public /audit/* exceptions
  per spec §5.1: the landing page and the health endpoint).
- /audit/v1/* API-key authentication is unchanged (still 401 without a
  Bearer audit API key).

The login redirect must not require the auth service: the gate only
checks that the OAuth client is configured before redirecting.

File: tests/contract/audit/test_web_auth_gate.py
Issue: #696, #720
"""

import os
import time
import unittest
from unittest import mock

from tests.fixtures import services

PUBLIC_URL = "https://campus.test"
CLIENT_ID = "auditweb-contract.test"
CLIENT_SECRET = "auditweb-contract-secret"


class TestAuditWebGateContract(unittest.TestCase):
    """HTTP contract tests for the /audit/* OAuth gate."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager(shared=False)
        cls.manager.initialize()
        cls.app = cls.manager.audit_app

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        # The gate must see a configured OAuth client so page requests
        # take the redirect path (not the 503 fail-closed path).
        self.env_patch = mock.patch.dict(os.environ, {
            "AUDIT_OAUTH_CLIENT_ID": CLIENT_ID,
            "AUDIT_OAUTH_CLIENT_SECRET": CLIENT_SECRET,
        })
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        assert self.app
        self.client = self.app.test_client()

    def test_landing_page_is_public(self):
        """GET /audit/ renders the landing page without authentication."""
        response = self.client.get("/audit/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Browse traces", response.data)

    def test_unauthenticated_trace_list_redirects_to_login(self):
        """GET /audit/traces redirects unauthenticated browsers to login."""
        response = self.client.get("/audit/traces")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.headers["Location"].endswith("/audit/login")
        )

    def test_unauthenticated_data_endpoint_returns_401(self):
        """GET /audit/api/traces answers 401 JSON when logged out."""
        response = self.client.get("/audit/api/traces")

        self.assertEqual(response.status_code, 401)
        self.assertIn("error", response.get_json())

    def test_non_admin_session_gets_403(self):
        """An authenticated session for a non-allowlisted user gets 403.

        The admin allowlist (AUDIT_ADMINS) gates pages and data
        endpoints for logged-in users; the landing page stays public.
        """
        with mock.patch.dict(
                os.environ,
                {"AUDIT_ADMINS": "admin@nyjc.edu.sg"},
        ):
            with self.client.session_transaction() as sess:
                sess["audit_oauth"] = {
                    "access_token": "contract-token",
                    "expires_at": time.time() + 3600,
                    "scope": "",
                    "user_id": "teacher@nyjc.edu.sg",
                }
            page = self.client.get("/audit/traces")
            api = self.client.get("/audit/api/traces")
            landing = self.client.get("/audit/")

        self.assertEqual(page.status_code, 403)
        self.assertEqual(api.status_code, 403)
        self.assertIn("error", api.get_json())
        self.assertEqual(landing.status_code, 200)

    def test_health_remains_public(self):
        """GET /audit/v1/health is reachable without authentication."""
        response = self.client.get("/audit/v1/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")

    def test_versioned_api_auth_unchanged(self):
        """GET /audit/v1/traces/ still requires an audit API key.

        The browser OAuth gate must not weaken the versioned API's own
        Bearer authentication.
        """
        response = self.client.get("/audit/v1/traces/")

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
