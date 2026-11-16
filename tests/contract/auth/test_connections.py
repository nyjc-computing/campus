"""HTTP contract tests for the connections surface (#733 Phase 2).

Covers the two new surfaces from the approved #730 design (§2.7) plus
the broker-wide completion of the absent-key-deny rule:

- GET /auth/v1/connections/ — the user's upstream connections across
  providers and integrations, metadata only (no token values, ever).
  Bearer auth is self-service; basic auth delegates with an explicit
  user_id.
- DELETE /auth/v1/connections/{provider}/ and
  /auth/v1/connections/{provider}/{integration}/ — disconnect deletes
  the credential rows and their token records and emits
  campus.integrations.disconnect (no token values). Campus tokens are
  not disconnectable here (C5: /oauth/revoke is logout).
- POST /auth/v1/broker/{provider}/ (identity grammar) refuses
  namespaced providers with integration semantics: absent allowlist
  entry ⇒ 400 AUTH_INVALID_SCOPE + deny event; with an entry ⇒ 404
  pointing at the canonical integration route.
"""

import unittest
from unittest import mock

import campus.model
from campus.common import env, schema
from campus.common.errors import api_errors
from tests.fixtures import services
from tests.fixtures.tokens import get_basic_auth_headers

USER_ID = schema.UserID("connections@nyjc.edu.sg")
OTHER_USER_ID = schema.UserID("someoneelse@nyjc.edu.sg")
GOOGLE_CLIENT_ID = "test-connections-google-client"
CLASSROOM_CLIENT_ID = "test-connections-classroom-client"
CLASSROOM_COURSES = "https://www.googleapis.com/auth/classroom.courses.readonly"
CLASSROOM_ROSTERS = "https://www.googleapis.com/auth/classroom.rosters"
USERINFO_EMAIL = "https://www.googleapis.com/auth/userinfo.email"
CLASSROOM_SCOPES = [
    CLASSROOM_COURSES,
    CLASSROOM_ROSTERS,
    USERINFO_EMAIL,
]


def _seed_connection(
        provider: str,
        user_id: schema.UserID,
        token_id: str,
        scopes: list[str],
        client_id: str,
) -> str:
    """Store a credential + token (as a connect/login would keep it)."""
    from campus.auth import resources as auth_resources
    auth_resources.credentials[provider][user_id].update(
        client_id=client_id,
        token=campus.model.OAuthToken(
            id=token_id,
            expires_in=3600,
            refresh_token=f"{token_id}-refresh",
            scopes=scopes,
        ),
    )
    return token_id


class ConnectionsContractTestBase(unittest.TestCase):
    """Shared harness for the connections contract tests."""

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
        self.auth_headers = get_basic_auth_headers(
            env.CLIENT_ID, env.CLIENT_SECRET
        )
        self.classroom_token_id = _seed_connection(
            "google.classroom",
            USER_ID,
            "classroom-access-token-1",
            CLASSROOM_SCOPES,
            CLASSROOM_CLIENT_ID,
        )
        self.google_token_id = _seed_connection(
            "google",
            USER_ID,
            "google-access-token-1",
            [USERINFO_EMAIL],
            GOOGLE_CLIENT_ID,
        )

    def _new_client_and_bearer(self, name: str = "connections-client") -> str:
        """Create a campus client + a user bearer for it (no bridge
        flag needed: connections are user self-service)."""
        payload = {
            "name": name,
            "description": name,
        }
        response = self.client.post(
            "/auth/v1/clients/",
            json=payload,
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        client_id = response.get_json()["id"]

        from campus.auth import resources as auth_resources
        token_id = f"campus-bearer-{client_id[-8:]}"
        auth_resources.credentials["campus"][USER_ID].update(
            client_id=client_id,
            token=campus.model.OAuthToken(
                id=token_id, expires_in=3600, scopes=["read"],
            ),
        )
        return token_id


class TestConnectionsListContract(ConnectionsContractTestBase):
    """GET /auth/v1/connections/ — metadata-only inventory."""

    def test_bearer_lists_own_connections(self):
        """§2.7: bearer auth is self-service; entries carry provider,
        integration, scopes and timestamps — never token values."""
        bearer = self._new_client_and_bearer()

        response = self.client.get(
            "/auth/v1/connections/",
            headers={"Authorization": f"Bearer {bearer}"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        by_provider = {
            entry["provider"]: entry for entry in body["connections"]
        }
        self.assertEqual(
            sorted(by_provider),
            ["google", "google.classroom"],
        )
        classroom = by_provider["google.classroom"]
        self.assertEqual(classroom["integration"], "classroom")
        self.assertEqual(classroom["scopes"], CLASSROOM_SCOPES)
        self.assertIsNotNone(classroom["connected_at"])
        self.assertIsNotNone(classroom["expires_at"])
        identity = by_provider["google"]
        self.assertIsNone(identity["integration"])
        # C2: no token material anywhere in the response
        self.assertNotIn("access_token", response.get_data(as_text=True))
        self.assertNotIn("refresh_token", response.get_data(as_text=True))
        self.assertNotIn(
            self.classroom_token_id, response.get_data(as_text=True)
        )

    def test_campus_tokens_are_not_connections(self):
        """C5: campus login tokens are not connections and are not
        listed — the bearer's own credential stays invisible."""
        bearer = self._new_client_and_bearer()

        response = self.client.get(
            "/auth/v1/connections/",
            headers={"Authorization": f"Bearer {bearer}"},
        )

        providers = [
            entry["provider"] for entry in response.get_json()["connections"]
        ]
        self.assertNotIn("campus", providers)

    def test_basic_auth_requires_user_id(self):
        """§2.7: basic auth carries no user; delegation must name one."""
        response = self.client.get(
            "/auth/v1/connections/",
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 400)

    def test_basic_auth_delegates_with_user_id(self):
        """§2.7: basic auth + user_id sees that user's connections —
        the shape the profile integrations page uses."""
        response = self.client.get(
            "/auth/v1/connections/",
            query_string={"user_id": str(USER_ID)},
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        providers = [
            entry["provider"]
            for entry in response.get_json()["connections"]
        ]
        self.assertEqual(
            sorted(providers),
            ["google", "google.classroom"],
        )

    def test_bearer_ignores_foreign_user_id(self):
        """§2.7: bearer auth acts for its own user only; a user_id
        parameter never widens the inventory."""
        _seed_connection(
            "google.classroom",
            OTHER_USER_ID,
            "other-access-token-1",
            CLASSROOM_SCOPES,
            CLASSROOM_CLIENT_ID,
        )
        bearer = self._new_client_and_bearer()

        response = self.client.get(
            "/auth/v1/connections/",
            query_string={"user_id": str(OTHER_USER_ID)},
            headers={"Authorization": f"Bearer {bearer}"},
        )

        self.assertEqual(response.status_code, 200)
        for entry in response.get_json()["connections"]:
            self.assertNotEqual(
                entry.get("access_token"), "other-access-token-1"
            )
        providers = [
            entry["provider"] for entry in response.get_json()["connections"]
        ]
        # Only the bearer's own connections are listed
        self.assertEqual(sorted(providers), ["google", "google.classroom"])


class TestDisconnectContract(ConnectionsContractTestBase):
    """DELETE /auth/v1/connections/... — explicit disconnect."""

    def test_disconnect_integration_deletes_rows_and_tokens(self):
        """§2.7: disconnect deletes the credential row + its token
        record and emits campus.integrations.disconnect (no token
        values); the identity google credential is untouched."""
        bearer = self._new_client_and_bearer()

        with mock.patch(
                "campus.auth.routes.connections.get_yapper"
        ) as yapper_factory:
            response = self.client.delete(
                "/auth/v1/connections/google/classroom/",
                headers={"Authorization": f"Bearer {bearer}"},
            )

        self.assertEqual(response.status_code, 200)
        from campus.auth import resources as auth_resources
        with self.assertRaises(api_errors.NotFoundError):
            auth_resources.credentials["google.classroom"][USER_ID].get(
                CLASSROOM_CLIENT_ID
            )
        from campus.auth.resources.credentials import token_storage
        self.assertIsNone(token_storage.get_by_id(self.classroom_token_id))
        # Identity google survives an integration disconnect
        credentials = auth_resources.credentials["google"][USER_ID].get(
            GOOGLE_CLIENT_ID
        )
        self.assertIsNotNone(credentials)
        emissions = [
            call.args[1]
            for call in yapper_factory.return_value.emit.call_args_list
            if call.args[0] == "campus.integrations.disconnect"
        ]
        self.assertEqual(len(emissions), 1)
        self.assertEqual(emissions[0]["provider"], "google.classroom")
        self.assertEqual(emissions[0]["integration"], "classroom")
        self.assertEqual(emissions[0]["user_id"], str(USER_ID))
        self.assertEqual(emissions[0]["scopes"], CLASSROOM_SCOPES)
        self.assertNotIn(
            self.classroom_token_id, str(emissions[0])
        )

    def test_disconnect_identity_provider_via_delegate(self):
        """§2.7: basic auth + user_id disconnects a base provider's
        credentials; the audit event carries no integration field."""
        _seed_connection(
            "google.classroom",
            USER_ID,
            self.classroom_token_id,
            CLASSROOM_SCOPES,
            CLASSROOM_CLIENT_ID,
        )

        with mock.patch(
                "campus.auth.routes.connections.get_yapper"
        ) as yapper_factory:
            response = self.client.delete(
                "/auth/v1/connections/google/",
                query_string={"user_id": str(USER_ID)},
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        from campus.auth import resources as auth_resources
        with self.assertRaises(api_errors.NotFoundError):
            auth_resources.credentials["google"][USER_ID].get(
                GOOGLE_CLIENT_ID
            )
        # Only the identity credential is deleted
        credentials = auth_resources.credentials["google.classroom"][
            USER_ID
        ].get(CLASSROOM_CLIENT_ID)
        self.assertIsNotNone(credentials)
        emissions = [
            call.args[1]
            for call in yapper_factory.return_value.emit.call_args_list
            if call.args[0] == "campus.integrations.disconnect"
        ]
        self.assertEqual(len(emissions), 1)
        self.assertEqual(emissions[0]["provider"], "google")
        self.assertNotIn("integration", emissions[0])

    def test_disconnect_namespaced_provider_on_identity_grammar_404(self):
        """The identity grammar never disconnects namespaced providers;
        the 404 points at the integration route (mirrors the broker)."""
        bearer = self._new_client_and_bearer()

        response = self.client.delete(
            "/auth/v1/connections/google.classroom/",
            headers={"Authorization": f"Bearer {bearer}"},
        )

        self.assertEqual(response.status_code, 404)
        from campus.auth import resources as auth_resources
        credentials = auth_resources.credentials["google.classroom"][
            USER_ID
        ].get(CLASSROOM_CLIENT_ID)
        self.assertIsNotNone(credentials)

    def test_disconnect_campus_provider_403(self):
        """C5: campus tokens are revoked via /oauth/revoke, not the
        connections API."""
        bearer = self._new_client_and_bearer()

        response = self.client.delete(
            "/auth/v1/connections/campus/",
            headers={"Authorization": f"Bearer {bearer}"},
        )

        self.assertEqual(response.status_code, 403)
        # The campus credential was untouched: the bearer still resolves
        echo = self.client.get(
            "/auth/v1/connections/",
            headers={"Authorization": f"Bearer {bearer}"},
        )
        self.assertEqual(echo.status_code, 200)

    def test_disconnect_unknown_integration_404(self):
        """Unknown slugs are 404 everywhere."""
        bearer = self._new_client_and_bearer()

        response = self.client.delete(
            "/auth/v1/connections/google/nope/",
            headers={"Authorization": f"Bearer {bearer}"},
        )

        self.assertEqual(response.status_code, 404)

    def test_disconnect_base_provider_mismatch_404(self):
        """§2.4/§2.7: the provider segment must match the integration's
        base provider."""
        bearer = self._new_client_and_bearer()

        response = self.client.delete(
            "/auth/v1/connections/github/classroom/",
            headers={"Authorization": f"Bearer {bearer}"},
        )

        self.assertEqual(response.status_code, 404)

    def test_disconnect_without_connection_404(self):
        """Disconnecting a never-established connection is a 404, not
        a silent 200."""
        bearer = self._new_client_and_bearer()

        response = self.client.delete(
            "/auth/v1/connections/github/",
            headers={"Authorization": f"Bearer {bearer}"},
        )

        self.assertEqual(response.status_code, 404)


class TestBrokerNamespacedGuardContract(ConnectionsContractTestBase):
    """The identity broker route refuses namespaced providers with
    integration semantics (absent-key-deny completed across the
    broker surface, #733)."""

    def _new_bridge_client(
            self,
            upstream_scopes: dict[str, list[str]],
    ) -> str:
        payload = {
            "name": "namespaced-guard-client",
            "description": "namespaced-guard-client",
            "token_bridge": True,
            "upstream_scopes": upstream_scopes,
        }
        response = self.client.post(
            "/auth/v1/clients/",
            json=payload,
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        client_id = response.get_json()["id"]

        from campus.auth import resources as auth_resources
        token_id = f"campus-bearer-{client_id[-8:]}"
        auth_resources.credentials["campus"][USER_ID].update(
            client_id=client_id,
            token=campus.model.OAuthToken(
                id=token_id, expires_in=3600, scopes=["read"],
            ),
        )
        return token_id

    def test_identity_grammar_absent_key_denies(self):
        """A namespaced provider without a non-empty upstream_scopes
        entry denies with AUTH_INVALID_SCOPE + a deny event naming the
        integration — not the generic unknown-provider 404."""
        bearer = self._new_bridge_client({"google": [USERINFO_EMAIL]})

        with mock.patch(
                "campus.auth.routes.broker.get_yapper"
        ) as yapper_factory:
            response = self.client.post(
                "/auth/v1/broker/google.classroom/",
                json={},
                headers={"Authorization": f"Bearer {bearer}"},
            )

        self.assertEqual(response.status_code, 400)
        emissions = [
            call.args[1]
            for call in yapper_factory.return_value.emit.call_args_list
            if call.args[0] == "campus.broker.deny"
        ]
        self.assertEqual(len(emissions), 1)
        self.assertEqual(emissions[0]["provider"], "google.classroom")
        self.assertEqual(emissions[0]["integration"], "classroom")
        self.assertIn(
            "no upstream_scopes entry", emissions[0]["reason"]
        )

    def test_identity_grammar_with_entry_points_at_integration_route(self):
        """A client that IS allowed still cannot release via the
        identity grammar: it is pointed at the canonical route."""
        bearer = self._new_bridge_client(
            {"google.classroom": CLASSROOM_SCOPES},
        )

        response = self.client.post(
            "/auth/v1/broker/google.classroom/",
            json={},
            headers={"Authorization": f"Bearer {bearer}"},
        )

        self.assertEqual(response.status_code, 404)
        message = response.get_json()["error"]["message"]
        self.assertIn("/auth/v1/broker/google/classroom/", message)
