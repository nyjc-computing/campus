"""HTTP contract tests for the /auth/v1/grants routes (#883, #886).

These tests verify the grant-administration surface and its guards:

- administration matrix: the operator administers everything; a
  user principal holding <vocabulary>:admin (grant row AND token
  scope, #885) administers exactly that vocabulary; everyone else —
  limited clients, plain user tokens, users with a scope but no row —
  is denied;
- grant-shape guards: no self-grants by user principals, no
  operator-equivalent clients:admin vocabulary rows, credentials and
  user-principal vault grants stay reserved (#889);
- grant/revoke/list/check/delete flows over both grantee types.

The fixtures make the default test client (env.CLIENT_ID) the
deployment operator, mirroring test_management_authorization.py.
"""

import unittest

from campus.common import env
from tests.fixtures import services
from tests.fixtures.tokens import (
    create_test_client_credentials,
    create_test_token,
    get_basic_auth_headers,
    get_bearer_auth_headers,
)

# create_test_token keys the credential (and thus the bearer's
# user dict) by the full email string.
ADMIN_EMAIL = "grants.admin@campus.test"
ADMIN_ID = ADMIN_EMAIL
NOROW_EMAIL = "grants.norow@campus.test"
TARGET_EMAIL = "grants.target@campus.test"
TARGET_ID = TARGET_EMAIL

GRANTS_BASE = "/auth/v1/grants"


class TestGrantsRoutes(unittest.TestCase):
    """Contract tests for the /auth/v1/grants blueprint."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.auth_app

        cls.limited_id, cls.limited_secret = create_test_client_credentials(
            name="grants-limited-client",
            description="Non-operator client for #886 grant tests",
        )
        # Designated users admin: bootstrap row in the store, plus a
        # token carrying the matching scope (both legs, #865/#885).
        cls.admin_token = create_test_token(
            ADMIN_EMAIL, scopes=["users:admin"]
        )
        # A token with the scope but NO grant row: capability without
        # designation confers nothing.
        cls.norow_token = create_test_token(
            NOROW_EMAIL, scopes=["users:admin"]
        )
        cls.target_token = create_test_token(
            TARGET_EMAIL, scopes=["read"]
        )

        from campus.auth.resources.grant import grants as grants_store
        grants_store.grant("user", ADMIN_ID, "users", level="admin")

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
        self.admin_headers = get_bearer_auth_headers(self.admin_token)
        self.norow_headers = get_bearer_auth_headers(self.norow_token)
        self.target_headers = get_bearer_auth_headers(self.target_token)

    def assert_forbidden(self, response):
        """Assert a 403 with the standard FORBIDDEN error envelope."""
        self.assertEqual(response.status_code, 403)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "FORBIDDEN")
        return data["error"]["message"]

    # --- administration matrix ---

    def test_unauthenticated_request_rejected(self):
        response = self.client.get(f"{GRANTS_BASE}/")
        self.assertEqual(response.status_code, 401)

    def test_limited_client_cannot_administer(self):
        response = self.client.get(
            f"{GRANTS_BASE}/", headers=self.limited_headers
        )
        self.assert_forbidden(response)
        response = self.client.post(
            f"{GRANTS_BASE}/",
            json={
                "grantee_type": "user",
                "grantee_id": TARGET_ID,
                "resource_type": "users",
                "level": "read",
            },
            headers=self.limited_headers,
        )
        self.assert_forbidden(response)

    def test_scope_without_row_confers_nothing(self):
        response = self.client.post(
            f"{GRANTS_BASE}/",
            json={
                "grantee_type": "user",
                "grantee_id": TARGET_ID,
                "resource_type": "users",
                "level": "read",
            },
            headers=self.norow_headers,
        )
        self.assert_forbidden(response)

    def test_vocabulary_admin_scoped_listing_only(self):
        response = self.client.get(
            f"{GRANTS_BASE}/?resource_type=users",
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200)
        # Unscoped listing is the operator's full matrix
        response = self.client.get(
            f"{GRANTS_BASE}/", headers=self.admin_headers
        )
        self.assert_forbidden(response)

    def test_cross_vocabulary_administration_denied(self):
        response = self.client.post(
            f"{GRANTS_BASE}/",
            json={
                "grantee_type": "user",
                "grantee_id": TARGET_ID,
                "resource_type": "clients",
                "level": "read",
            },
            headers=self.admin_headers,
        )
        self.assert_forbidden(response)

    # --- operator flows ---

    def test_operator_grants_lists_checks_and_revokes(self):
        # Grant a users level row for the target user
        response = self.client.post(
            f"{GRANTS_BASE}/",
            json={
                "grantee_type": "user",
                "grantee_id": TARGET_ID,
                "resource_type": "users",
                "level": "write",
            },
            headers=self.operator_headers,
        )
        self.assertEqual(response.status_code, 201)
        grant_id = response.get_json()["grant"]["id"]

        # The full matrix lists it
        response = self.client.get(
            f"{GRANTS_BASE}/", headers=self.operator_headers
        )
        rows = response.get_json()["grants"]
        self.assertTrue(any(r["id"] == grant_id for r in rows))

        # Check covers a lower level (monotonic)
        response = self.client.get(
            f"{GRANTS_BASE}/check",
            query_string={
                "grantee_type": "user",
                "grantee_id": TARGET_ID,
                "resource_type": "users",
                "level": "read",
            },
            headers=self.operator_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["granted"])

        # Revoke deletes the covered row
        response = self.client.post(
            f"{GRANTS_BASE}/revoke",
            json={
                "grantee_type": "user",
                "grantee_id": TARGET_ID,
                "resource_type": "users",
                "level": "write",
            },
            headers=self.operator_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json()["grant"])

    def test_operator_grants_vault_bits_for_clients(self):
        response = self.client.post(
            f"{GRANTS_BASE}/",
            json={
                "grantee_type": "client",
                "grantee_id": self.limited_id,
                "resource_type": "vault",
                "resource_id": "grants-test-label",
                "bits": 5,
            },
            headers=self.operator_headers,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["grant"]["bits"], 5)

    def test_operator_deletes_row_by_id(self):
        response = self.client.post(
            f"{GRANTS_BASE}/",
            json={
                "grantee_type": "user",
                "grantee_id": TARGET_ID,
                "resource_type": "users",
                "level": "mod",
            },
            headers=self.operator_headers,
        )
        grant_id = response.get_json()["grant"]["id"]

        response = self.client.delete(
            f"{GRANTS_BASE}/{grant_id}", headers=self.operator_headers
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.delete(
            f"{GRANTS_BASE}/{grant_id}", headers=self.operator_headers
        )
        self.assertEqual(response.status_code, 404)

    # --- grant-shape guards (apply to the operator too) ---

    def test_operator_equivalent_clients_admin_row_rejected(self):
        response = self.client.post(
            f"{GRANTS_BASE}/",
            json={
                "grantee_type": "user",
                "grantee_id": TARGET_ID,
                "resource_type": "clients",
                "level": "admin",
            },
            headers=self.operator_headers,
        )
        message = self.assert_forbidden(response)
        self.assertIn("operator-equivalent", message)

    def test_reserved_credentials_vocabulary_rejected(self):
        response = self.client.post(
            f"{GRANTS_BASE}/",
            json={
                "grantee_type": "user",
                "grantee_id": TARGET_ID,
                "resource_type": "credentials",
                "level": "read",
            },
            headers=self.operator_headers,
        )
        self.assert_forbidden(response)

    def test_user_vault_rows_carry_levels_not_bits(self):
        # #889: user vault grants are per-label level rows; bitflags
        # are the client-grantee grammar.
        response = self.client.post(
            f"{GRANTS_BASE}/",
            json={
                "grantee_type": "user",
                "grantee_id": TARGET_ID,
                "resource_type": "vault",
                "resource_id": "some-label",
                "bits": 1,
            },
            headers=self.operator_headers,
        )
        self.assertEqual(response.status_code, 400)

    # --- anti-escalation ---

    def test_user_admin_cannot_self_grant(self):
        response = self.client.post(
            f"{GRANTS_BASE}/",
            json={
                "grantee_type": "user",
                "grantee_id": ADMIN_ID,
                "resource_type": "users",
                "level": "admin",
            },
            headers=self.admin_headers,
        )
        message = self.assert_forbidden(response)
        self.assertIn("own access grants", message)

    def test_user_admin_manages_own_vocabulary(self):
        response = self.client.post(
            f"{GRANTS_BASE}/",
            json={
                "grantee_type": "user",
                "grantee_id": TARGET_ID,
                "resource_type": "users",
                "level": "read",
            },
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 201)

        response = self.client.post(
            f"{GRANTS_BASE}/revoke",
            json={
                "grantee_type": "user",
                "grantee_id": TARGET_ID,
                "resource_type": "users",
                "level": "read",
            },
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200)

    def test_plain_user_token_denied_everywhere(self):
        for method, path, kwargs in (
            ("get", f"{GRANTS_BASE}/", {}),
            ("get", f"{GRANTS_BASE}/check", {"query_string": {
                "grantee_type": "user",
                "grantee_id": TARGET_ID,
                "resource_type": "users",
                "level": "read",
            }}),
            ("post", f"{GRANTS_BASE}/", {"json": {
                "grantee_type": "user",
                "grantee_id": TARGET_ID,
                "resource_type": "users",
                "level": "read",
            }}),
        ):
            response = getattr(self.client, method)(
                path, headers=self.target_headers, **kwargs
            )
            self.assert_forbidden(response)



class TestGrantsRootMatrix(unittest.TestCase):
    """The super-admin root reads the unfiltered matrix (#906).

    Regression: list_grants used `assert resource_type is not None`
    as flow control behind require_operator — written when
    require_operator always raised for user principals. #900 wired
    is_super_admin() into that gate, so the root fell through to the
    assert and unfiltered lists 500'd. Filtered lists (which route
    to _require_grant_admin, root-wired) always worked.
    """

    ROOT = "grants.906.root@campus.test"
    PLAIN = "grants.906.plain@campus.test"

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.auth_app

        # Generic end-user scopes only: the root needs no management
        # scopes, and the plain user must gain nothing from the env
        # var being set.
        cls.root_token = create_test_token(cls.ROOT, scopes=["read"])
        cls.plain_token = create_test_token(cls.PLAIN, scopes=["read"])
        env.set("AUTH_SUPER_ADMIN", cls.ROOT)

    @classmethod
    def tearDownClass(cls):
        if env.contains("AUTH_SUPER_ADMIN"):
            env.delete("AUTH_SUPER_ADMIN")
        cls.manager.cleanup()

    def setUp(self):
        self.client = self.app.test_client()
        self.root_headers = get_bearer_auth_headers(self.root_token)
        self.plain_headers = get_bearer_auth_headers(self.plain_token)

    def test_root_lists_unfiltered_matrix(self):
        """The exact #906 repro: unfiltered list is 200, not 500."""
        response = self.client.get(GRANTS_BASE + "/", headers=self.root_headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn("grants", response.get_json())

    def test_root_lists_filtered(self):
        """Filtered lists keep working for the root."""
        response = self.client.get(
            GRANTS_BASE + "/",
            query_string={"resource_type": "users"},
            headers=self.root_headers,
        )
        self.assertEqual(response.status_code, 200)

    def test_plain_user_unfiltered_still_denied(self):
        """Non-root users still need the operator (or a vocabulary)."""
        response = self.client.get(
            GRANTS_BASE + "/", headers=self.plain_headers
        )
        self.assertEqual(response.status_code, 403)

    def test_root_check_endpoint_still_passes(self):
        """The shared gate _require_grant_admin stays root-wired."""
        response = self.client.get(
            GRANTS_BASE + "/check",
            query_string={
                "grantee_type": "user",
                "grantee_id": self.ROOT,
                "resource_type": "users",
                "level": "read",
            },
            headers=self.root_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.get_json()["granted"], bool)


if __name__ == "__main__":
    unittest.main()
