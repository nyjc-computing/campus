"""HTTP contract tests for management-route authorization (#854, #865, #881).

These tests verify that the management blueprints (vaults, clients,
users, credentials) authorize, not merely authenticate:

- vault labels are gated by the client's vault_access bitflags, with
  the operator principal (AUTH_OPERATOR_CLIENT_IDS) bypassing them;
- clients are read-only on registration data (#881): they may read
  their own record and rotate their own secret, but never update any
  client record (the 403 points at the clients:write user-principal
  path), touch the operator-controlled fields (allowed_scopes,
  upstream_scopes, token_bridge), or administer vault-access grants;
- user bearer tokens are denied on every management route regardless
  of their scopes — except designated admin users (#865) acting on
  the clients and users blueprints with the matching management
  scope: both the vocabulary's designated-admin listing
  (AUTH_ADMIN_USER_IDS for clients, AUTH_USERS_ADMIN_USER_IDS for
  users — campus-cli#42, campus#872) and the scope are required,
  ANDed.

The fixtures make the default test client (env.CLIENT_ID) the
deployment operator; a second "limited" confidential client and user
bearer tokens exercise the denied shapes.
"""

import unittest
import uuid
from unittest import mock

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
# Throwaway label for the #865 admin-user vault-access grant tests.
ADMIN_GRANT_VAULT = "authz-admin-grant-label"


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
        return data["error"]["message"]

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
        """A client reads and rotates its own record (mutations: #881)."""
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

        # Self-PATCH used to be allowed (#854); #881 narrowed it —
        # mutations must be attributable to a user, so even the
        # client's own record is denied (asserted fully below).
        response = self.client.patch(
            f"/auth/v1/clients/{self.limited_id}/",
            json={"description": "Updated by self (#881 denies this)"},
            headers=self.limited_headers,
        )
        message = self.assert_forbidden(response)
        self.assertIn("clients:write", message)

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

    def test_client_self_patch_denied_881(self):
        """A9/#881: client-principal PATCH of its own record is 403.

        Even benign profile fields (name, description, redirect_uris)
        are user-attributable mutations now: the error must point the
        caller at the clients:write user-principal path, not at the
        operator allowlist.
        """
        for field, value in (
            ("name", "Renamed by self"),
            ("description", "Updated by self"),
            ("redirect_uris", ["https://self.example/cb"]),
        ):
            response = self.client.patch(
                f"/auth/v1/clients/{self.limited_id}/",
                json={field: value},
                headers=self.limited_headers,
            )
            message = self.assert_forbidden(response)
            self.assertIn("clients:write", message)
            self.assertIn("#881", message)

        # The app-scoped bearer is the same client principal (#739) and
        # gets the same denial.
        response = self.client.patch(
            f"/auth/v1/clients/{self.limited_id}/",
            json={"description": "x"},
            headers=self.app_headers,
        )
        message = self.assert_forbidden(response)
        self.assertIn("clients:write", message)

    def test_client_scope_caps_operator_controlled(self):
        """The scope caps stay above every client principal (#854, #881)."""
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


class TestDesignatedAdminUsers(unittest.TestCase):
    """Management-scope authorization for designated admin users (#865).

    The issue's test matrix, per gated clients route: a user principal
    acts only when BOTH legs hold — its id is listed in
    AUTH_ADMIN_USER_IDS AND its token carries the required management
    scope. Designation without the scope and scope without designation
    are both 403, with messages that distinguish the failed leg.

    Operator-client and client-self-service behavior are asserted
    unchanged by TestManagementAuthorization. Every user token here is
    minted through the operator client itself (env.CLIENT_ID is the
    operator in these fixtures), so the non-designated denials also
    prove a user never inherits the operator role of the client it was
    minted through (#854).
    """

    # The designated admins (listed in AUTH_ADMIN_USER_IDS — one per
    # scope variant, since a user's credentials row holds a single
    # live token) and a regular user (not listed) carrying every
    # clients:* scope: scope alone must never confer authority.
    ADMIN_USER_IDS = [
        "authz.865.admin.read@campus.test",
        "authz.865.admin.write@campus.test",
        "authz.865.admin.admin@campus.test",
        # Designated but holding only generic end-user scopes: the
        # capability leg fails.
        "authz.865.admin.plain@campus.test",
    ]
    OTHER_USER = "authz.865.other@campus.test"

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.auth_app

        # Another client's record for the cross-client read/write tests.
        cls.limited_id, cls.limited_secret = create_test_client_credentials(
            name="authz-865-limited-client",
            description="Non-operator client for #865 admin-user tests",
        )
        # A dedicated target the admin user may mutate freely (secret
        # rotation, scope caps, deletion); operator-registered so the
        # tests never widen the limited client's authority.
        suffix = uuid.uuid4().hex[:8]
        response = cls.app.test_client().post(
            "/auth/v1/clients/",
            json={
                "name": f"authz-865-target-{suffix}",
                "description": "Admin-user mutation target (#865)",
            },
            headers=get_basic_auth_headers(env.CLIENT_ID, env.CLIENT_SECRET),
        )
        assert response.status_code == 200, response.get_json()
        cls.target_id = response.get_json()["id"]

        # One token per user (the credentials row holds a single live
        # token), so the designated legs are separate users per scope;
        # the non-designated user carries every clients:* scope at once
        # to prove scope alone suffices for nothing.
        cls.admin_read = create_test_token(
            cls.ADMIN_USER_IDS[0], scopes=["clients:read"]
        )
        cls.admin_write = create_test_token(
            cls.ADMIN_USER_IDS[1], scopes=["clients:write"]
        )
        cls.admin_admin = create_test_token(
            cls.ADMIN_USER_IDS[2], scopes=["clients:admin"]
        )
        cls.admin_plain = create_test_token(
            cls.ADMIN_USER_IDS[3], scopes=["read", "write"]
        )
        cls.other_all = create_test_token(
            cls.OTHER_USER,
            scopes=["clients:read", "clients:write", "clients:admin"],
        )

        # Leg 1 (identity): the designated users, listed at request
        # time (comma-separated). Unset/empty means no user admins —
        # asserted explicitly by test_empty_allowlist_denies_designated_user.
        env.set("AUTH_ADMIN_USER_IDS", ",".join(cls.ADMIN_USER_IDS))

    @classmethod
    def tearDownClass(cls):
        if env.contains("AUTH_ADMIN_USER_IDS"):
            env.delete("AUTH_ADMIN_USER_IDS")
        cls.manager.cleanup()

    def setUp(self):
        self.client = self.app.test_client()
        self.admin_read_headers = get_bearer_auth_headers(self.admin_read)
        self.admin_write_headers = get_bearer_auth_headers(self.admin_write)
        self.admin_admin_headers = get_bearer_auth_headers(self.admin_admin)
        self.admin_plain_headers = get_bearer_auth_headers(self.admin_plain)
        self.other_all_headers = get_bearer_auth_headers(self.other_all)
        self.operator_headers = get_basic_auth_headers(
            env.CLIENT_ID, env.CLIENT_SECRET
        )

    def assert_forbidden(self, response):
        """Assert a 403 with the standard FORBIDDEN error envelope."""
        self.assertEqual(response.status_code, 403)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "FORBIDDEN")
        return data["error"]["message"]

    # --- clients:read — list and get any record ---

    def test_read_matrix(self):
        """Designated+scope acts; each single-leg denial is 403."""
        for path in ("/auth/v1/clients/",
                     f"/auth/v1/clients/{self.limited_id}/"):
            response = self.client.get(path, headers=self.admin_read_headers)
            self.assertEqual(response.status_code, 200)

            # clients:write implies read (scopes.grants implication).
            response = self.client.get(path, headers=self.admin_write_headers)
            self.assertEqual(response.status_code, 200)

            response = self.client.get(path, headers=self.admin_plain_headers)
            message = self.assert_forbidden(response)
            self.assertIn("clients:read", message)

            response = self.client.get(path, headers=self.other_all_headers)
            message = self.assert_forbidden(response)
            self.assertIn("designated admin", message)

    def test_read_unlisted_scope_implied_by_admin(self):
        """clients:admin also implies clients:read."""
        response = self.client.get(
            "/auth/v1/clients/", headers=self.admin_admin_headers
        )
        self.assertEqual(response.status_code, 200)

    # --- clients:write — benign fields on any client ---

    def test_write_matrix(self):
        """PATCH of a benign field follows the same two-leg matrix."""
        response = self.client.patch(
            f"/auth/v1/clients/{self.limited_id}/",
            json={"description": "Updated by clients:write admin (#865)"},
            headers=self.admin_write_headers,
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.patch(
            f"/auth/v1/clients/{self.limited_id}/",
            json={"description": "x"},
            headers=self.admin_read_headers,
        )
        message = self.assert_forbidden(response)
        self.assertIn("clients:write", message)

        response = self.client.patch(
            f"/auth/v1/clients/{self.limited_id}/",
            json={"description": "x"},
            headers=self.other_all_headers,
        )
        message = self.assert_forbidden(response)
        self.assertIn("designated admin", message)

    def test_write_matrix_mutation_is_audited_881(self):
        """A9/#881: the user-principal PATCH emits its audit event.

        The mutation path #881 keeps is the attributable one, so the
        campus.clients.update emission must fire on the clients:write
        leg. (The span's user_id stamp — flask.g.current_user →
        campus.audit — is covered in tests/unit/audit/
        test_tracing_propagation.py, #802; the contract harness cannot
        read cross-service audit spans, #570.)
        """
        with mock.patch(
                "campus.auth.routes.clients.get_yapper"
        ) as yapper_factory:
            response = self.client.patch(
                f"/auth/v1/clients/{self.limited_id}/",
                json={"description": "Audited clients:write update (#881)"},
                headers=self.admin_write_headers,
            )
        self.assertEqual(response.status_code, 200)
        emissions = [
            call.args
            for call in yapper_factory.return_value.emit.call_args_list
        ]
        update_events = [
            payload for event, payload in emissions
            if event == "campus.clients.update"
        ]
        self.assertEqual(len(update_events), 1)
        self.assertEqual(update_events[0].get("client_id"), self.limited_id)

    def test_write_cannot_touch_operator_only_fields(self):
        """clients:write stays below the scope caps; clients:admin may."""
        response = self.client.patch(
            f"/auth/v1/clients/{self.target_id}/",
            json={"allowed_scopes": ["read"]},
            headers=self.admin_write_headers,
        )
        message = self.assert_forbidden(response)
        self.assertIn("clients:admin", message)

        response = self.client.patch(
            f"/auth/v1/clients/{self.target_id}/",
            json={"allowed_scopes": ["read"]},
            headers=self.admin_admin_headers,
        )
        self.assertEqual(response.status_code, 200)

    # --- clients:admin — register, rotate, delete, vault grants ---

    def test_admin_registers_and_deletes(self):
        """Designated+clients:admin registers a client; write cannot."""
        suffix = uuid.uuid4().hex[:8]
        response = self.client.post(
            "/auth/v1/clients/",
            json={
                "name": f"authz-865-registered-{suffix}",
                "description": "Registered by a clients:admin user (#865)",
            },
            headers=self.admin_write_headers,
        )
        message = self.assert_forbidden(response)
        self.assertIn("clients:admin", message)

        response = self.client.post(
            "/auth/v1/clients/",
            json={
                "name": f"authz-865-registered-{suffix}",
                "description": "Registered by a clients:admin user (#865)",
            },
            headers=self.other_all_headers,
        )
        message = self.assert_forbidden(response)
        self.assertIn("designated admin", message)

        response = self.client.post(
            "/auth/v1/clients/",
            json={
                "name": f"authz-865-registered-{suffix}",
                "description": "Registered by a clients:admin user (#865)",
            },
            headers=self.admin_admin_headers,
        )
        self.assertEqual(response.status_code, 200)
        registered_id = response.get_json()["id"]

        # Deletion is clients:admin too — including on this registered
        # client, and for the client itself.
        response = self.client.delete(
            f"/auth/v1/clients/{registered_id}/",
            json={},
            headers=self.admin_admin_headers,
        )
        self.assertEqual(response.status_code, 200)

    def test_admin_rotates_secrets(self):
        """Secret rotation is clients:admin, not clients:write."""
        response = self.client.post(
            f"/auth/v1/clients/{self.target_id}/revoke",
            json={},
            headers=self.admin_write_headers,
        )
        message = self.assert_forbidden(response)
        self.assertIn("clients:admin", message)

        response = self.client.post(
            f"/auth/v1/clients/{self.target_id}/revoke",
            json={},
            headers=self.admin_admin_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("secret", response.get_json())

    def test_admin_administers_vault_access(self):
        """Vault-access grants are clients:admin; views are read."""
        response = self.client.get(
            f"/auth/v1/clients/{self.target_id}/access/",
            headers=self.admin_read_headers,
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            f"/auth/v1/clients/{self.target_id}/access/grant",
            json={"vault": ADMIN_GRANT_VAULT, "permission": ClientAccess.READ},
            headers=self.admin_write_headers,
        )
        message = self.assert_forbidden(response)
        self.assertIn("clients:admin", message)

        response = self.client.post(
            f"/auth/v1/clients/{self.target_id}/access/grant",
            json={"vault": ADMIN_GRANT_VAULT, "permission": ClientAccess.READ},
            headers=self.other_all_headers,
        )
        message = self.assert_forbidden(response)
        self.assertIn("designated admin", message)

        response = self.client.post(
            f"/auth/v1/clients/{self.target_id}/access/grant",
            json={"vault": ADMIN_GRANT_VAULT, "permission": ClientAccess.READ},
            headers=self.admin_admin_headers,
        )
        self.assertEqual(response.status_code, 200)

    # --- reserved vocabularies and fail-closed defaults ---

    def test_reserved_vocabularies_deny_users(self):
        """vaults/credentials stay operator-only (#865 phasing); users
        has its own designated-admin list since campus-cli#42, so a
        clients-designated admin is denied there too — the
        AUTH_ADMIN_USER_IDS listing does not cross vocabularies
        (campus#872)."""
        for method, path, kwargs in (
            ("get", "/auth/v1/users/", {}),
            ("get", "/auth/v1/credentials/campus/", {}),
            ("get", f"/auth/v1/vaults/{SHARED_VAULT}/", {}),
        ):
            response = getattr(self.client, method)(
                path, headers=self.admin_admin_headers, **kwargs
            )
            message = self.assert_forbidden(response)
            if path.endswith("users/"):
                self.assertIn("No access grant designates", message)

    def test_empty_allowlist_denies_designated_user(self):
        """An unset allowlist means no user admins (deploy is a no-op)."""
        env.delete("AUTH_ADMIN_USER_IDS")
        self.addCleanup(
            env.set, "AUTH_ADMIN_USER_IDS", ",".join(self.ADMIN_USER_IDS)
        )
        response = self.client.get(
            "/auth/v1/clients/", headers=self.admin_read_headers
        )
        message = self.assert_forbidden(response)
        self.assertIn("designated admin", message)

class TestDesignatedUsersAdmins(unittest.TestCase):
    """Management-scope authorization for the users blueprint
    (campus-cli#42; store-backed since #887).

    The identity leg is a users:* grant row in the access-grant
    store (#883) — AUTH_USERS_ADMIN_USER_IDS is no longer consulted
    (#887, DB-only ruling). A clients-designated admin (the
    transitional AUTH_ADMIN_USER_IDS list, #888) is not a
    users-admin, and vice versa. Per-action floors: users:read
    lists/gets, users:mod activates, users:write creates and updates
    (implies mod), users:admin deletes (implies write).
    """

    # One grant-row admin per level (a credentials row holds a single
    # live token), plus one designated-but-scopeless user (the
    # capability leg fails) and one user carrying every users:*
    # scope with NO users grant row — listed only in the transitional
    # clients env list: the per-vocabulary isolation proof — neither
    # the scopes nor the wrong vocabulary's designation confer
    # anything.
    USERS_ADMIN_IDS = [
        "authz.42.admin.read@campus.test",
        "authz.42.admin.mod@campus.test",
        "authz.42.admin.write@campus.test",
        "authz.42.admin.admin@campus.test",
        "authz.42.admin.plain@campus.test",
    ]
    CLIENTS_ONLY_ADMIN = "authz.42.clients-only@campus.test"

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.auth_app

        cls.tokens = {
            "read": create_test_token(
                cls.USERS_ADMIN_IDS[0], scopes=["users:read"]
            ),
            "mod": create_test_token(
                cls.USERS_ADMIN_IDS[1], scopes=["users:mod"]
            ),
            "write": create_test_token(
                cls.USERS_ADMIN_IDS[2], scopes=["users:write"]
            ),
            "admin": create_test_token(
                cls.USERS_ADMIN_IDS[3], scopes=["users:admin"]
            ),
            # Designated but holding only generic end-user scopes: the
            # capability leg fails.
            "plain": create_test_token(
                cls.USERS_ADMIN_IDS[4], scopes=["read", "write"]
            ),
            "clients_only": create_test_token(
                cls.CLIENTS_ONLY_ADMIN,
                scopes=[
                    "users:read", "users:mod", "users:write", "users:admin",
                ],
            ),
        }
        # Grant rows are the identity leg (#887): one per admin,
        # at the level their token scope carries. The plain admin is
        # fully designated (admin row) but its token holds no users:*
        # scope — the capability leg fails.
        from campus.auth.resources.grant import grants as grants_store
        for admin_id, level in (
            (cls.USERS_ADMIN_IDS[0], "read"),
            (cls.USERS_ADMIN_IDS[1], "mod"),
            (cls.USERS_ADMIN_IDS[2], "write"),
            (cls.USERS_ADMIN_IDS[3], "admin"),
            (cls.USERS_ADMIN_IDS[4], "admin"),
        ):
            grants_store.grant("user", admin_id, "users", level=level)
        # The transitional clients-designated env list names the
        # every-users-scope user, proving the clients designation and
        # the users grant rows gate disjoint vocabularies (#872, #888).
        env.set("AUTH_ADMIN_USER_IDS", cls.CLIENTS_ONLY_ADMIN)

    @classmethod
    def tearDownClass(cls):
        if env.contains("AUTH_ADMIN_USER_IDS"):
            env.delete("AUTH_ADMIN_USER_IDS")
        cls.manager.cleanup()

    def setUp(self):
        self.client = self.app.test_client()
        self.operator_headers = get_basic_auth_headers(
            env.CLIENT_ID, env.CLIENT_SECRET
        )
        self.headers = {
            key: get_bearer_auth_headers(token)
            for key, token in self.tokens.items()
        }
        # A fresh mutation target per test, so activation state never
        # leaks between tests.
        suffix = uuid.uuid4().hex[:8]
        response = self.client.post(
            "/auth/v1/users/",
            json={
                "email": f"authz.42.target.{suffix}@campus.test",
                "name": "Users-vocab target (#42)",
            },
            headers=self.operator_headers,
        )
        assert response.status_code == 201, response.get_json()
        self.target_id = response.get_json()["id"]

    def assert_forbidden(self, response):
        """Assert a 403 with the standard FORBIDDEN error envelope."""
        self.assertEqual(response.status_code, 403)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "FORBIDDEN")
        return data["error"]["message"]

    # --- users:read — list and get any record ---

    def test_read_matrix(self):
        """Designated+users:read acts; each single-leg denial is 403."""
        for path in ("/auth/v1/users/",
                     f"/auth/v1/users/{self.target_id}/"):
            response = self.client.get(path, headers=self.headers["read"])
            self.assertEqual(response.status_code, 200)

            # users:mod implies read (scopes.grants implication).
            response = self.client.get(path, headers=self.headers["mod"])
            self.assertEqual(response.status_code, 200)

            response = self.client.get(path, headers=self.headers["plain"])
            message = self.assert_forbidden(response)
            self.assertIn("users:read", message)

            response = self.client.get(
                path, headers=self.headers["clients_only"]
            )
            message = self.assert_forbidden(response)
            self.assertIn("No access grant designates", message)

    # --- users:mod — activate (implies read) ---

    def test_activate_matrix(self):
        """Activation is users:mod or higher; users:read cannot."""
        response = self.client.post(
            f"/auth/v1/users/{self.target_id}/activate",
            headers=self.headers["mod"],
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.get_json()["activated_at"])

        for key in ("read", "plain"):
            response = self.client.post(
                f"/auth/v1/users/{self.target_id}/activate",
                headers=self.headers[key],
            )
            message = self.assert_forbidden(response)
            self.assertIn("users:mod", message)

        response = self.client.post(
            f"/auth/v1/users/{self.target_id}/activate",
            headers=self.headers["clients_only"],
        )
        message = self.assert_forbidden(response)
        self.assertIn("No access grant designates", message)

    # --- users:write — create and update (implies mod) ---

    def test_create_matrix(self):
        """Creation is users:write or higher; users:mod cannot."""
        response = self.client.post(
            "/auth/v1/users/",
            json={
                "email": f"authz.42.created.{uuid.uuid4().hex[:8]}@campus.test",
                "name": "Created by users:write (#42)",
            },
            headers=self.headers["write"],
        )
        self.assertEqual(response.status_code, 201)

        for key in ("mod", "plain"):
            response = self.client.post(
                "/auth/v1/users/",
                json={
                    "email": (
                        f"authz.42.denied.{uuid.uuid4().hex[:8]}@campus.test"
                    ),
                    "name": "Denied creation (#42)",
                },
                headers=self.headers[key],
            )
            message = self.assert_forbidden(response)
            self.assertIn("users:write", message)

        response = self.client.post(
            "/auth/v1/users/",
            json={
                "email": (
                    f"authz.42.isolation.{uuid.uuid4().hex[:8]}@campus.test"
                ),
                "name": "Isolation probe (#42)",
            },
            headers=self.headers["clients_only"],
        )
        message = self.assert_forbidden(response)
        self.assertIn("No access grant designates", message)

    def test_update_matrix(self):
        """PATCH renames with users:write; identity fields stay fixed."""
        response = self.client.patch(
            f"/auth/v1/users/{self.target_id}/",
            json={"name": "Renamed by users:write (#42)"},
            headers=self.headers["write"],
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["name"], "Renamed by users:write (#42)"
        )

        response = self.client.patch(
            f"/auth/v1/users/{self.target_id}/",
            json={"name": "x"},
            headers=self.headers["mod"],
        )
        message = self.assert_forbidden(response)
        self.assertIn("users:write", message)

        # A user's id IS its email: identity fields are not patchable.
        # Strict body validation rejects the unknown field outright.
        response = self.client.patch(
            f"/auth/v1/users/{self.target_id}/",
            json={"email": "identity.change@campus.test"},
            headers=self.headers["write"],
        )
        self.assertEqual(response.status_code, 422)

        response = self.client.patch(
            f"/auth/v1/users/{self.target_id}/",
            json={},
            headers=self.headers["write"],
        )
        self.assertEqual(response.status_code, 400)

    # --- users:admin — delete (implies write) ---

    def test_delete_matrix(self):
        """Deletion is users:admin; users:write cannot."""
        response = self.client.delete(
            f"/auth/v1/users/{self.target_id}/",
            json={},
            headers=self.headers["write"],
        )
        message = self.assert_forbidden(response)
        self.assertIn("users:admin", message)

        response = self.client.delete(
            f"/auth/v1/users/{self.target_id}/",
            json={},
            headers=self.headers["clients_only"],
        )
        message = self.assert_forbidden(response)
        self.assertIn("No access grant designates", message)

        response = self.client.delete(
            f"/auth/v1/users/{self.target_id}/",
            json={},
            headers=self.headers["admin"],
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.get(
            f"/auth/v1/users/{self.target_id}/",
            headers=self.operator_headers,
        )
        self.assertIn(response.status_code, (404, 400))

    def test_implied_levels(self):
        """users:write may activate and read; users:admin may rename."""
        response = self.client.get(
            f"/auth/v1/users/{self.target_id}/",
            headers=self.headers["write"],
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            f"/auth/v1/users/{self.target_id}/activate",
            headers=self.headers["write"],
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.patch(
            f"/auth/v1/users/{self.target_id}/",
            json={"name": "Renamed by users:admin"},
            headers=self.headers["admin"],
        )
        self.assertEqual(response.status_code, 200)

    # --- fail-closed defaults and per-vocabulary isolation ---

    def test_no_grant_row_means_no_admin(self):
        """Deleting the grant row removes the designation (#887)."""
        from campus.auth.resources.grant import grants as grants_store
        grants_store.revoke(
            "user", self.USERS_ADMIN_IDS[0], "users", level="read"
        )
        self.addCleanup(
            grants_store.grant,
            "user", self.USERS_ADMIN_IDS[0], "users", level="read",
        )
        response = self.client.get(
            "/auth/v1/users/", headers=self.headers["read"]
        )
        message = self.assert_forbidden(response)
        self.assertIn("No access grant designates", message)


if __name__ == '__main__':
    unittest.main()
