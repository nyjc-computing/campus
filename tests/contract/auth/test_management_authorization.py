"""HTTP contract tests for management-route authorization (#854).

These tests verify that the management blueprints (vaults, clients,
users, credentials) authorize, not merely authenticate:

- vault labels are gated by the client's vault_access bitflags, with
  the operator principal (AUTH_OPERATOR_CLIENT_IDS) bypassing them;
- clients may manage only their own record, and never the
  operator-controlled fields (allowed_scopes, upstream_scopes,
  token_bridge) or vault-access grants;
- user bearer tokens are denied on every management route regardless
  of their scopes.

The fixtures make the default test client (env.CLIENT_ID) the
deployment operator; a second "limited" confidential client and a user
bearer token exercise the denied shapes.
"""

import unittest
import uuid

from campus.common import env
from campus.model.client import ClientAccess
from tests.fixtures import services
from tests.fixtures.tokens import (
    create_test_client_credentials,
    create_test_token,
    get_basic_auth_headers,
    get_bearer_auth_headers,
)

# Vault labels for the label-gating tests. SHARED carries a READ grant
# for the limited client; PRIVATE carries no grant for it at all.
SHARED_VAULT = "authz-shared-label"
PRIVATE_VAULT = "authz-private-label"
# Throwaway label for the operator grant test, so the limited client's
# SHARED grant stays READ-only regardless of test execution order.
GRANT_VAULT = "authz-grant-label"


class TestManagementAuthorization(unittest.TestCase):
    """Authorization contract tests for /auth/v1 management routes."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.auth_app

        # Limited (non-operator) confidential client with a known secret
        cls.limited_id, cls.limited_secret = create_test_client_credentials(
            name="authz-limited-client",
            description="Non-operator client for #854 authorization tests",
        )
        # User bearer token (device-flow-shaped): scopes carry no
        # management authority (#854).
        cls.user_token = create_test_token(
            "authz.user@campus.test",
            scopes=["read", "write"],
            grant_vault_access=False,
        )
        # App-scoped bearer for the limited client (client_credentials
        # grant resolves to the client itself, #739).
        from campus.auth import resources as auth_resources
        app_token = auth_resources.app_credentials.issue(
            cls.limited_id, ["read"]
        )
        cls.app_token = app_token.id

        # Vault fixtures: keys behind each label.
        auth_resources.vault[SHARED_VAULT]["READABLE"] = "yes"
        auth_resources.vault[PRIVATE_VAULT]["SECRET"] = "operator-only"
        # The limited client may read SHARED only.
        auth_resources.client[cls.limited_id].access.grant(
            SHARED_VAULT, ClientAccess.READ
        )

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        self.client = self.app.test_client()
        self.operator_headers = get_basic_auth_headers(
            env.CLIENT_ID, env.CLIENT_SECRET
        )
        self.limited_headers = get_basic_auth_headers(
            self.limited_id, self.limited_secret
        )
        self.user_headers = get_bearer_auth_headers(self.user_token)
        self.app_headers = get_bearer_auth_headers(self.app_token)

    def assert_forbidden(self, response):
        """Assert a 403 with the standard FORBIDDEN error envelope."""
        self.assertEqual(response.status_code, 403)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "FORBIDDEN")

    # --- vault labels: vault_access bitflags gate every verb ---

    def test_vault_read_with_grant_succeeds(self):
        """GET on a label with a READ grant serves the key list and keys."""
        for path in (f"/auth/v1/vaults/{SHARED_VAULT}/",
                     f"/auth/v1/vaults/{SHARED_VAULT}/READABLE"):
            response = self.client.get(path, headers=self.limited_headers)
            self.assertEqual(response.status_code, 200)

    def test_vault_write_denied_with_read_only_grant(self):
        """POST/DELETE on a READ-only label are denied (403)."""
        response = self.client.post(
            f"/auth/v1/vaults/{SHARED_VAULT}/NEWKEY",
            json={"value": "x"},
            headers=self.limited_headers,
        )
        self.assert_forbidden(response)

        response = self.client.delete(
            f"/auth/v1/vaults/{SHARED_VAULT}/READABLE",
            json={},
            headers=self.limited_headers,
        )
        self.assert_forbidden(response)

    def test_vault_denied_without_label_grant(self):
        """A grant on one label confers nothing on another label."""
        for method, path, kwargs in (
            ("get", f"/auth/v1/vaults/{PRIVATE_VAULT}/", {}),
            ("get", f"/auth/v1/vaults/{PRIVATE_VAULT}/SECRET", {}),
            ("post", f"/auth/v1/vaults/{PRIVATE_VAULT}/NEWKEY",
             {"json": {"value": "x"}}),
            ("delete", f"/auth/v1/vaults/{PRIVATE_VAULT}/SECRET",
             {"json": {}}),
        ):
            response = getattr(self.client, method)(
                path, headers=self.limited_headers, **kwargs
            )
            self.assert_forbidden(response)

    def test_vault_user_bearer_denied(self):
        """User bearer tokens cannot touch vaults regardless of scope."""
        for method, path, kwargs in (
            ("get", f"/auth/v1/vaults/{SHARED_VAULT}/", {}),
            ("get", f"/auth/v1/vaults/{SHARED_VAULT}/READABLE", {}),
            ("post", f"/auth/v1/vaults/{SHARED_VAULT}/NEWKEY",
             {"json": {"value": "x"}}),
            ("delete", f"/auth/v1/vaults/{SHARED_VAULT}/READABLE",
             {"json": {}}),
            ("get", f"/auth/v1/vaults/{PRIVATE_VAULT}/SECRET", {}),
        ):
            response = getattr(self.client, method)(
                path, headers=self.user_headers, **kwargs
            )
            self.assert_forbidden(response)

    def test_vault_operator_bypasses_bitflags(self):
        """The operator manages any label without per-label grants."""
        response = self.client.post(
            f"/auth/v1/vaults/{PRIVATE_VAULT}/OPERATORKEY",
            json={"value": "v"},
            headers=self.operator_headers,
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.get(
            f"/auth/v1/vaults/{PRIVATE_VAULT}/", headers=self.operator_headers
        )
        self.assertEqual(response.status_code, 200)

    # --- clients: operator-only registration and cross-client access ---

    def test_client_registration_operator_only(self):
        """POST /clients/ requires the operator principal."""
        # vault_clients.name is UNIQUE: suffix the registered client so
        # re-runs against a persistent store cannot collide.
        suffix = uuid.uuid4().hex[:8]
        payload = {
            "name": "authz-would-be-client",
            "description": "Registered by non-operator",
        }
        response = self.client.post(
            "/auth/v1/clients/", json=payload, headers=self.limited_headers
        )
        self.assert_forbidden(response)

        response = self.client.post(
            "/auth/v1/clients/", json=payload, headers=self.user_headers
        )
        self.assert_forbidden(response)

        response = self.client.post(
            "/auth/v1/clients/",
            json={
                "name": f"authz-operator-registered-{suffix}",
                "description": "Registered by the operator",
            },
            headers=self.operator_headers,
        )
        self.assertEqual(response.status_code, 200)

    def test_client_cross_client_access_denied(self):
        """A non-operator client cannot touch another client's record."""
        operator_id = env.CLIENT_ID
        for method, path, kwargs in (
            ("get", f"/auth/v1/clients/{operator_id}/", {}),
            ("patch", f"/auth/v1/clients/{operator_id}/",
             {"json": {"description": "hijacked"}}),
            ("delete", f"/auth/v1/clients/{operator_id}/", {"json": {}}),
            ("post", f"/auth/v1/clients/{operator_id}/revoke", {"json": {}}),
            # Self-delete is denied too: only the operator retires clients.
            ("delete", f"/auth/v1/clients/{self.limited_id}/", {"json": {}}),
        ):
            response = getattr(self.client, method)(
                path, headers=self.limited_headers, **kwargs
            )
            self.assert_forbidden(response)

    def test_client_access_granting_operator_only(self):
        """Vault-access administration is never self-service (#854)."""
        for headers, _actor in (
            (self.limited_headers, "the client itself"),
            (self.user_headers, "a user bearer"),
        ):
            response = self.client.post(
                f"/auth/v1/clients/{self.limited_id}/access/grant",
                json={"vault": GRANT_VAULT, "permission": ClientAccess.ALL},
                headers=headers,
            )
            self.assert_forbidden(response)

        response = self.client.post(
            f"/auth/v1/clients/{self.limited_id}/access/grant",
            json={"vault": GRANT_VAULT, "permission": ClientAccess.ALL},
            headers=self.operator_headers,
        )
        self.assertEqual(response.status_code, 200)

    def test_client_user_bearer_denied(self):
        """User bearer tokens cannot manage clients regardless of scope."""
        for method, path, kwargs in (
            ("get", "/auth/v1/clients/", {}),
            ("get", f"/auth/v1/clients/{self.limited_id}/", {}),
            ("patch", f"/auth/v1/clients/{self.limited_id}/",
             {"json": {"description": "x"}}),
            ("post", f"/auth/v1/clients/{self.limited_id}/revoke",
             {"json": {}}),
        ):
            response = getattr(self.client, method)(
                path, headers=self.user_headers, **kwargs
            )
            self.assert_forbidden(response)

    def test_client_self_management_allowed(self):
        """A client reads, updates and rotates its own record."""
        response = self.client.get(
            "/auth/v1/clients/", headers=self.limited_headers
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.get(
            f"/auth/v1/clients/{self.limited_id}/",
            headers=self.limited_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["id"], self.limited_id)

        response = self.client.patch(
            f"/auth/v1/clients/{self.limited_id}/",
            json={"description": "Updated by self (#854)"},
            headers=self.limited_headers,
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            f"/auth/v1/clients/{self.limited_id}/revoke",
            json={},
            headers=self.limited_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("secret", response.get_json())
        # Later tests (unittest runs methods alphabetically) must keep
        # authenticating as this client: adopt the rotated secret and
        # rebuild the headers (the old secret stops authenticating).
        type(self).limited_secret = response.get_json()["secret"]
        self.limited_headers = get_basic_auth_headers(
            self.limited_id, self.limited_secret
        )

        response = self.client.get(
            f"/auth/v1/clients/{self.limited_id}/access/",
            headers=self.limited_headers,
        )
        self.assertEqual(response.status_code, 200)

    def test_client_scope_caps_operator_controlled(self):
        """Self-management may not widen its own authority (#854)."""
        for field, value in (
            ("allowed_scopes", ["read", "write", "admin"]),
            ("upstream_scopes", {"google": ["scope"]}),
            ("token_bridge", True),
        ):
            response = self.client.patch(
                f"/auth/v1/clients/{self.limited_id}/",
                json={field: value},
                headers=self.limited_headers,
            )
            self.assert_forbidden(response)

        # The operator may set them.
        response = self.client.patch(
            f"/auth/v1/clients/{self.limited_id}/",
            json={"allowed_scopes": ["read", "write"]},
            headers=self.operator_headers,
        )
        self.assertEqual(response.status_code, 200)

    def test_client_app_bearer_is_client_principal(self):
        """App-scoped bearers (#739) carry their client's authority."""
        response = self.client.get(
            f"/auth/v1/clients/{self.limited_id}/", headers=self.app_headers
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.get(
            f"/auth/v1/clients/{env.CLIENT_ID}/", headers=self.app_headers
        )
        self.assert_forbidden(response)

    # --- users and credentials: operator-only blueprints ---

    def test_users_operator_only(self):
        """GET/POST /users require the operator principal."""
        response = self.client.get("/auth/v1/users/", headers=self.limited_headers)
        self.assert_forbidden(response)
        response = self.client.get("/auth/v1/users/", headers=self.user_headers)
        self.assert_forbidden(response)
        response = self.client.post(
            "/auth/v1/users/",
            json={"email": "authz.new@campus.test", "name": "Authz New"},
            headers=self.limited_headers,
        )
        self.assert_forbidden(response)

        response = self.client.get("/auth/v1/users/", headers=self.operator_headers)
        self.assertEqual(response.status_code, 200)

    def test_credentials_operator_only(self):
        """The credentials API requires the operator principal (#854)."""
        response = self.client.get(
            "/auth/v1/credentials/campus/", headers=self.limited_headers
        )
        self.assert_forbidden(response)
        response = self.client.get(
            "/auth/v1/credentials/campus/", headers=self.user_headers
        )
        self.assert_forbidden(response)

        response = self.client.get(
            "/auth/v1/credentials/campus/", headers=self.operator_headers
        )
        self.assertEqual(response.status_code, 200)


if __name__ == '__main__':
    unittest.main()
