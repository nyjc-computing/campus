"""HTTP contract tests for upstream (third-party provider) scopes.

These tests verify Campus's hosted incremental authorization for
upstream providers (#705), per docs/auth-token-invariants.md B3:

- The Google authorize endpoint merges requested upstream scopes with
  the proxy's base scopes (email, profile) and forwards them to
  Google with include_granted_scopes=true.
- The campus /authorize endpoint caps upstream scope requests against
  the requesting client's registered upstream_scopes allowlist —
  fail-closed: a client with no entry for a provider may request none
  of that provider's scopes.
- Client registration round-trips the upstream_scopes allowlist.
"""

import unittest
from urllib.parse import parse_qs, urlparse

from campus.common import env
from tests.fixtures import services
from tests.fixtures.tokens import get_basic_auth_headers

REGISTERED_URI = "https://upstream.example.com/finalize_login"
APP_TARGET = "https://upstream.example.com/link-google"
CLASSROOM_ROSTERS = "https://www.googleapis.com/auth/classroom.rosters"


class TestUpstreamScopesContract(unittest.TestCase):
    """HTTP contract tests for upstream scope requests."""

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

        assert self.app
        self.client = self.app.test_client()
        self.auth_headers = get_basic_auth_headers(env.CLIENT_ID, env.CLIENT_SECRET)

        # The Google proxy loads its OAuth client from the vault on
        # every request; the harness does not seed the "google" label,
        # so seed test credentials here (no network calls happen — the
        # endpoint only builds the authorization redirect).
        from campus.auth import resources as auth_resources
        auth_resources.vault["google"]["CLIENT_ID"] = "test-google-client-id"
        auth_resources.vault["google"]["CLIENT_SECRET"] = "test-google-client-secret"

    def _create_client(
            self,
            upstream_scopes: dict[str, list[str]] | None = None,
    ) -> str:
        """Create a client and return its ID."""
        payload = {
            "name": "upstream-scopes-contract-client",
            "description": "Client for upstream scope contract tests",
            "redirect_uris": [REGISTERED_URI],
            "allowed_scopes": ["read"],
        }
        if upstream_scopes is not None:
            payload["upstream_scopes"] = upstream_scopes
        response = self.client.post(
            "/auth/v1/clients/",
            json=payload,
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        return response.get_json()["id"]

    def _create_session(self, client_id: str) -> str:
        """Create a Campus auth session and return its ID."""
        response = self.client.post(
            "/auth/v1/sessions/campus/",
            json={
                "client_id": client_id,
                "redirect_uri": REGISTERED_URI,
            },
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        return response.get_json()["id"]

    def _query_params(self, location: str) -> dict:
        return parse_qs(urlparse(location).query)

    def test_google_authorize_defaults_to_base_scopes(self):
        """B3: without a scope request only the base scopes are asked."""
        response = self.client.get(
            "/auth/v1/google/authorize",
            query_string={"target": APP_TARGET},
        )

        self.assertEqual(response.status_code, 302)
        location = response.headers.get("Location", "")
        self.assertIn("accounts.google.com", location)
        params = self._query_params(location)
        self.assertEqual(sorted(params["scope"][0].split()), ["email", "profile"])
        self.assertEqual(params["include_granted_scopes"], ["true"])

    def test_google_authorize_merges_extra_scopes(self):
        """B3: extra upstream scopes are merged with the base set."""
        response = self.client.get(
            "/auth/v1/google/authorize",
            query_string={
                "target": APP_TARGET,
                "scope": CLASSROOM_ROSTERS,
            },
        )

        self.assertEqual(response.status_code, 302)
        params = self._query_params(response.headers.get("Location", ""))
        self.assertEqual(
            sorted(params["scope"][0].split()),
            ["email", CLASSROOM_ROSTERS, "profile"],
        )

    def test_authorize_forwards_allowed_upstream_scope(self):
        """B3: upstream scopes within the allowlist reach the Google leg."""
        client_id = self._create_client({"google": [CLASSROOM_ROSTERS]})
        session_id = self._create_session(client_id)

        response = self.client.get(
            "/auth/v1/authorize",
            query_string={
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": REGISTERED_URI,
                "state": session_id,
                "upstream_scope": CLASSROOM_ROSTERS,
            },
        )

        self.assertEqual(response.status_code, 302)
        location = response.headers.get("Location", "")
        self.assertIn("/auth/v1/google/authorize", location)
        self.assertIn("classroom.rosters", location)

    def test_authorize_with_upstream_scope_warns_deprecated(self):
        """Deprecated-call telemetry (#733): upstream_scope at /authorize
        is logged + audited as a deprecated call but still succeeds."""
        client_id = self._create_client({"google": [CLASSROOM_ROSTERS]})
        session_id = self._create_session(client_id)

        with self.assertLogs(
                "campus.auth.provider", level="WARNING"
        ) as captured:
            response = self.client.get(
                "/auth/v1/authorize",
                query_string={
                    "client_id": client_id,
                    "response_type": "code",
                    "redirect_uri": REGISTERED_URI,
                    "state": session_id,
                    "upstream_scope": CLASSROOM_ROSTERS,
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            any("Deprecated upstream_scope" in message for message in captured.output)
        )

    def test_authorize_without_upstream_scope_does_not_warn(self):
        """Deprecated-call telemetry (#733): a plain authorize request
        does not trigger the deprecation warning."""
        client_id = self._create_client()
        session_id = self._create_session(client_id)

        with self.assertNoLogs("campus.auth.provider", level="WARNING"):
            response = self.client.get(
                "/auth/v1/authorize",
                query_string={
                    "client_id": client_id,
                    "response_type": "code",
                    "redirect_uri": REGISTERED_URI,
                    "state": session_id,
                },
            )

        self.assertEqual(response.status_code, 302)

    def test_authorize_rejects_unallowed_upstream_scope(self):
        """B3: upstream scopes beyond the allowlist fail fail-closed."""
        client_id = self._create_client({"google": []})
        session_id = self._create_session(client_id)

        response = self.client.get(
            "/auth/v1/authorize",
            query_string={
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": REGISTERED_URI,
                "state": session_id,
                "upstream_scope": CLASSROOM_ROSTERS,
            },
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "AUTH_INVALID_SCOPE")

    def test_client_without_upstream_entry_rejects_any_upstream_scope(self):
        """B3: no allowlist entry for a provider allows no extras."""
        client_id = self._create_client()
        session_id = self._create_session(client_id)

        response = self.client.get(
            "/auth/v1/authorize",
            query_string={
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": REGISTERED_URI,
                "state": session_id,
                "upstream_scope": CLASSROOM_ROSTERS,
            },
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "AUTH_INVALID_SCOPE")

    def test_client_upstream_scopes_roundtrip(self):
        """B3: registration and PATCH round-trip the upstream allowlist."""
        client_id = self._create_client({"google": [CLASSROOM_ROSTERS]})

        response = self.client.get(
            f"/auth/v1/clients/{client_id}/",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["upstream_scopes"],
            {"google": [CLASSROOM_ROSTERS]},
        )

        patched = self.client.patch(
            f"/auth/v1/clients/{client_id}/",
            json={"upstream_scopes": {"google": []}},
            headers=self.auth_headers,
        )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.get_json()["upstream_scopes"], {"google": []})
