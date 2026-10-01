"""HTTP contract tests for the audit web UI OAuth gate.

These tests verify the browser OAuth gate contract required by
docs/web-ui-requirements.md §5 (issue #696):

- Unauthenticated requests to UI pages redirect to /audit/login.
- Unauthenticated requests to /audit/api/* data endpoints get 401 JSON.
- /audit/v1/health stays publicly reachable (the only public /audit/*
  exception per spec §5.1).
- /audit/v1/* API-key authentication is unchanged (still 401 without a
  Bearer audit API key).

The login redirect must not require the auth service: the gate only
checks that the OAuth client is configured before redirecting.

File: tests/contract/audit/test_web_auth_gate.py
Issue: #696
"""

import os
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

    def test_unauthenticated_index_redirects_to_login(self):
        """GET /audit/ redirects unauthenticated browsers to login."""
        response = self.client.get("/audit/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.headers["Location"].endswith("/audit/login")
        )

    def test_unauthenticated_data_endpoint_returns_401(self):
        """GET /audit/api/traces answers 401 JSON when logged out."""
        response = self.client.get("/audit/api/traces")

        self.assertEqual(response.status_code, 401)
        self.assertIn("error", response.get_json())

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
