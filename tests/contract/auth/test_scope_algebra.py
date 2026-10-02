"""HTTP contract tests for the Campus scope algebra.

These tests verify the fail-closed scope allowlist introduced with the
token-bridge work (#705), per docs/auth-token-invariants.md:

- A1: a session or device code may only request scopes within the
  client's registered allowed_scopes; violations return 400
  invalid_scope, and an empty allowlist grants nothing.
- A6: the session-creation boundary enforces the allowlist, and the
  /authorize scope parameter may not exceed the session's scopes.
- A7: device authorization validates DEFAULT_CLI_SCOPES against the
  same allowlist.
"""

import unittest

from campus.common import env
from tests.fixtures import services
from tests.fixtures.tokens import get_basic_auth_headers

REGISTERED_URI = "https://scope-algebra.example.com/finalize_login"


class TestScopeAlgebraContract(unittest.TestCase):
    """HTTP contract tests for the fail-closed scope allowlist."""

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

    def _create_client(
            self,
            redirect_uris: list[str],
            allowed_scopes: list[str] | None = None,
    ) -> str:
        """Create a client and return its ID."""
        payload = {
            "name": "scope-algebra-contract-client",
            "description": "Client for scope algebra contract tests",
            "redirect_uris": redirect_uris,
        }
        if allowed_scopes is not None:
            payload["allowed_scopes"] = allowed_scopes
        response = self.client.post(
            "/auth/v1/clients/",
            json=payload,
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("allowed_scopes", data)
        self.assertEqual(data["allowed_scopes"], allowed_scopes or [])
        return data["id"]

    def _create_session(
            self,
            client_id: str,
            scopes: list[str] | None = None,
    ) -> int:
        """Create a Campus auth session, returning the response."""
        payload = {
            "client_id": client_id,
            "redirect_uri": REGISTERED_URI,
        }
        if scopes is not None:
            payload["scopes"] = scopes
        return self.client.post(
            "/auth/v1/sessions/campus/",
            json=payload,
            headers=self.auth_headers,
        )

    def _get_authorize(
            self,
            client_id: str,
            session_id: str,
            scope: str | None = None,
    ):
        """Issue an authorization request as a client app's browser would."""
        query = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": REGISTERED_URI,
            "state": session_id,
        }
        if scope is not None:
            query["scope"] = scope
        return self.client.get("/auth/v1/authorize", query_string=query)

    def test_session_with_allowed_scopes_accepted(self):
        """A1: scopes within the allowlist are granted verbatim."""
        client_id = self._create_client([REGISTERED_URI], ["read", "write"])

        response = self._create_session(client_id, ["read"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["scopes"], ["read"])

    def test_session_with_disallowed_scope_rejected(self):
        """A1: a scope outside the allowlist fails with invalid_scope."""
        client_id = self._create_client([REGISTERED_URI], ["read"])

        response = self._create_session(client_id, ["read", "admin"])

        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "AUTH_INVALID_SCOPE")

    def test_empty_allowlist_grants_nothing(self):
        """A1: a client with no registered scopes cannot request any."""
        client_id = self._create_client([REGISTERED_URI])

        response = self._create_session(client_id, ["read"])

        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "AUTH_INVALID_SCOPE")

    def test_scopeless_session_accepted_on_empty_allowlist(self):
        """An empty scope request passes even with an empty allowlist."""
        client_id = self._create_client([REGISTERED_URI])

        response = self._create_session(client_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["scopes"], [])

    def test_patch_allowed_scopes_updates_allowlist(self):
        """A1: the allowlist is mutable and takes effect immediately."""
        client_id = self._create_client([REGISTERED_URI], ["write"])

        response = self.client.patch(
            f"/auth/v1/clients/{client_id}/",
            json={"allowed_scopes": ["read"]},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["allowed_scopes"], ["read"])

        self.assertEqual(self._create_session(client_id, ["write"]).status_code, 400)
        self.assertEqual(self._create_session(client_id, ["read"]).status_code, 200)

    def test_authorize_scope_within_session_redirects(self):
        """A6: a scope parameter within the session's scopes proceeds."""
        client_id = self._create_client([REGISTERED_URI], ["read", "write"])
        session_id = self._create_session(client_id, ["read"]).get_json()["id"]

        response = self._get_authorize(client_id, session_id, scope="read")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/v1/google/authorize", response.headers.get("Location", ""))

    def test_authorize_scope_exceeding_session_rejected(self):
        """A6: a scope parameter beyond the session's scopes fails."""
        client_id = self._create_client([REGISTERED_URI], ["read", "write"])
        session_id = self._create_session(client_id, ["read"]).get_json()["id"]

        response = self._get_authorize(client_id, session_id, scope="read write")

        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "AUTH_INVALID_SCOPE")

    def test_device_authorize_respects_allowlist(self):
        """A7: device authorization validates the CLI scopes.

        The seeded public client allows the default CLI scopes; a client
        whose allowlist lacks them is rejected fail-closed.
        """
        restricted_id = self._create_client([REGISTERED_URI], ["read"])

        response = self.client.post(
            "/auth/v1/oauth/device_authorize",
            json={"client_id": restricted_id},
        )
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "AUTH_INVALID_SCOPE")

        seeded_response = self.client.post(
            "/auth/v1/oauth/device_authorize",
            json={"client_id": "guest"},
        )
        self.assertEqual(seeded_response.status_code, 200)
