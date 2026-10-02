"""HTTP contract tests for the token bridge (/auth/v1/broker).

These tests verify the custodial release of upstream access tokens
(#705), per docs/auth-token-invariants.md:

- C1: releases require a campus bearer token for the user, presented
  by a confidential client flagged for bridge access. Public clients,
  unflagged clients, and client-credentials (basic) callers with no
  user context are denied fail-closed.
- C2: responses carry the access token, its expiry, and its scope —
  never a refresh token.
- C3: min_scopes are capped by the client's upstream allowlist and the
  user's actual upstream grant; denials are machine-readable.
- B1/B2: the credentials API no longer exposes third-party-provider
  credentials (they embed upstream refresh tokens).
"""

import unittest

import campus.model
from campus.common import env, schema
from tests.fixtures import services
from tests.fixtures.tokens import get_basic_auth_headers

GOOGLE_SCOPE = "https://www.googleapis.com/auth/classroom.rosters"
GOOGLE_UNGRANTED_SCOPE = (
    "https://www.googleapis.com/auth/classroom.announcements"
)
USER_ID = schema.UserID("broker@nyjc.edu.sg")
GOOGLE_CLIENT_ID = "test-google-client-id"


class TestTokenBrokerContract(unittest.TestCase):
    """HTTP contract tests for the token bridge."""

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

        from campus.auth import resources as auth_resources

        # The proxy/vault lookups need the google label seeded (the
        # harness does not seed it); no network calls happen.
        auth_resources.vault["google"]["CLIENT_ID"] = GOOGLE_CLIENT_ID
        auth_resources.vault["google"]["CLIENT_SECRET"] = "test-google-client-secret"

        # Bridge-enabled confidential client
        response = self.client.post(
            "/auth/v1/clients/",
            json={
                "name": "broker-contract-client",
                "description": "Client for token bridge contract tests",
                "token_bridge": True,
                "upstream_scopes": {
                    "google": [GOOGLE_SCOPE, GOOGLE_UNGRANTED_SCOPE],
                },
            },
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.bridge_client_id = response.get_json()["id"]

        # The user's stored Google credential (as the proxy would keep
        # it), keyed under Campus's own Google client id
        auth_resources.credentials["google"][USER_ID].update(
            client_id=GOOGLE_CLIENT_ID,
            token=campus.model.OAuthToken(
                id="google-access-token-1",
                expires_in=3600,
                scopes=["email", "profile", GOOGLE_SCOPE],
            ),
        )
        # The caller's campus bearer token, bound to the bridge client
        auth_resources.credentials["campus"][USER_ID].update(
            client_id=self.bridge_client_id,
            token=campus.model.OAuthToken(
                id="campus-broker-bearer",
                expires_in=3600,
                scopes=["read"],
            ),
        )
        self.bearer_headers = {"Authorization": "Bearer campus-broker-bearer"}

    def _bearer(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def _bridge_client_with_token(self, name: str, token_id: str, **client_kwargs):
        """Create a client + campus token for the user bound to it."""
        payload = {
            "name": name,
            "description": name,
            **client_kwargs,
        }
        response = self.client.post(
            "/auth/v1/clients/",
            json=payload,
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        client_id = response.get_json()["id"]

        from campus.auth import resources as auth_resources
        auth_resources.credentials["campus"][USER_ID].update(
            client_id=client_id,
            token=campus.model.OAuthToken(
                id=token_id, expires_in=3600, scopes=["read"],
            ),
        )
        return client_id

    def test_release_returns_minimal_upstream_token(self):
        """C1/C2: happy path returns the token with no refresh token."""
        response = self.client.post(
            "/auth/v1/broker/google/",
            json={},
            headers=self.bearer_headers,
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["provider"], "google")
        self.assertEqual(data["user_id"], str(USER_ID))
        self.assertEqual(data["access_token"], "google-access-token-1")
        self.assertEqual(data["token_type"], "Bearer")
        self.assertGreater(data["expires_in"], 0)
        self.assertIn(GOOGLE_SCOPE, data["scope"])
        # C2: refresh tokens and provider fields never leave
        self.assertNotIn("refresh_token", data)
        self.assertNotIn("provider_fields", data)

    def test_unflagged_client_denied(self):
        """C1: a confidential client without the bridge flag is denied."""
        other_id = self._bridge_client_with_token(
            "broker-unflagged-client", "campus-unflagged-bearer",
        )
        self.assertIsNotNone(other_id)

        response = self.client.post(
            "/auth/v1/broker/google/",
            json={},
            headers=self._bearer("campus-unflagged-bearer"),
        )

        self.assertEqual(response.status_code, 403)

    def test_public_client_denied(self):
        """C1: public clients are never eligible, flag or not."""
        # guest is public (seeded); bind a campus token to it anyway
        from campus.auth import resources as auth_resources
        auth_resources.credentials["campus"][USER_ID].update(
            client_id="guest",
            token=campus.model.OAuthToken(
                id="campus-public-bearer", expires_in=3600, scopes=["read"],
            ),
        )

        response = self.client.post(
            "/auth/v1/broker/google/",
            json={},
            headers=self._bearer("campus-public-bearer"),
        )

        self.assertEqual(response.status_code, 403)

    def test_basic_auth_without_user_context_denied(self):
        """C1: client-credentials auth has no user to release for."""
        response = self.client.post(
            "/auth/v1/broker/google/",
            json={},
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 403)

    def test_unknown_bearer_token_returns_401(self):
        """C1: an unresolvable bearer token is 401 invalid_token
        (RFC 6750 §3.1), not 404 (#729)."""
        response = self.client.post(
            "/auth/v1/broker/google/",
            json={},
            headers=self._bearer("campus-garbage-token"),
        )

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "AUTH_TOKEN_INVALID")
        self.assertIn("message", data["error"])
        self.assertIn("request_id", data["error"])

    def test_min_scopes_beyond_grant_denied_with_missing_list(self):
        """C3: a grant that does not cover min_scopes is denied.

        GOOGLE_UNGRANTED_SCOPE is allowlisted for the client but absent
        from the user's stored Google grant, so the denial comes from
        the grant check (C3b), not the allowlist check (C3a).
        """
        response = self.client.post(
            "/auth/v1/broker/google/",
            json={"min_scopes": [GOOGLE_UNGRANTED_SCOPE]},
            headers=self.bearer_headers,
        )

        self.assertEqual(response.status_code, 403)
        data = response.get_json()
        self.assertIn("classroom.announcements", str(data))

    def test_min_scopes_beyond_allowlist_rejected(self):
        """C3: min_scopes outside the client's allowlist fail at once."""
        response = self.client.post(
            "/auth/v1/broker/google/",
            json={"min_scopes": [
                "https://www.googleapis.com/auth/drive",
            ]},
            headers=self.bearer_headers,
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "AUTH_INVALID_SCOPE")

    def test_missing_upstream_credential_returns_404(self):
        """C1: no stored credential for the user -> 404, not a token."""
        from campus.auth import resources as auth_resources
        other_user = schema.UserID("someoneelse@nyjc.edu.sg")
        auth_resources.credentials["campus"][other_user].update(
            client_id=self.bridge_client_id,
            token=campus.model.OAuthToken(
                id="campus-other-bearer", expires_in=3600, scopes=["read"],
            ),
        )

        response = self.client.post(
            "/auth/v1/broker/google/",
            json={},
            headers=self._bearer("campus-other-bearer"),
        )

        self.assertEqual(response.status_code, 404)

    def test_unknown_provider_returns_404(self):
        """Only proxied providers are bridgeable."""
        response = self.client.post(
            "/auth/v1/broker/myspace/",
            json={},
            headers=self.bearer_headers,
        )

        self.assertEqual(response.status_code, 404)

    def test_credentials_api_refuses_third_party_provider(self):
        """B1/B2: the credentials API no longer leaks upstream tokens."""
        get_response = self.client.get(
            "/auth/v1/credentials/google/",
            headers=self.auth_headers,
        )
        self.assertEqual(get_response.status_code, 403)

        user_response = self.client.get(
            f"/auth/v1/credentials/google/{USER_ID}",
            headers=self.auth_headers,
        )
        self.assertEqual(user_response.status_code, 403)

        patch_response = self.client.patch(
            f"/auth/v1/credentials/google/{USER_ID}",
            json={"token": {"id": "smuggled", "expires_in": 3600}},
            headers=self.auth_headers,
        )
        self.assertEqual(patch_response.status_code, 403)
