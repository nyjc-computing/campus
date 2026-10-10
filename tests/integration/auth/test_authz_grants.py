"""campus.tests.integration.auth.test_authz_grants

Function-level authorization tests for the generalized resource gate
(#885): require_resource_permission and its require_vault_permission
wrapper, driven directly over flask.g and the access-grant store
(#884) on the tmpfile SQLite backend.

The matrix from the issue: (grant row present/absent) x (token scope
present/absent) x (user/client/operator principal) x vault vs
management resource — plus the #854 invariants: a user principal is
consulted before the operator bypass and never inherits the minting
client's operator role, and the gate fails closed on absent or
malformed rows.

IMPORTANT: Lazy imports are required to avoid storage initialization
before test mode is configured (see AGENTS.md - Storage Initialization
Order).
"""

import os
import unittest
from types import SimpleNamespace
from unittest import mock

import flask

from campus.common.errors import api_errors

OPERATOR_ID = "cl_operator"
OPERATOR_ENV = {"AUTH_OPERATOR_CLIENT_IDS": OPERATOR_ID}
LIMITED_ID = "cl_limited"


def operator_client():
    return SimpleNamespace(id=OPERATOR_ID)


def limited_client():
    return SimpleNamespace(id=LIMITED_ID)


def user_principal(user_id, scopes):
    return {"id": user_id, "scopes": scopes}


class TestResourceGate(unittest.TestCase):
    """The (row x scope x principal x resource) matrix."""

    @classmethod
    def setUpClass(cls):
        """Configure test storage and init the grant store schema."""
        import campus.storage.testing

        campus.storage.testing.configure_test_storage()
        campus.storage.testing.configure_test_db()

        from campus.auth.resources.grant import GrantsResource
        GrantsResource.init_storage()

        from campus.auth.resources.client import ClientsResource
        ClientsResource.init_storage()

        cls.app = flask.Flask(__name__)

    @classmethod
    def tearDownClass(cls):
        """Clean test storage after all tests."""
        import campus.storage.testing
        campus.storage.testing.clear_all_data()

    def setUp(self):
        """Clean storage before each test without destroying schema."""
        import campus.storage.testing
        campus.storage.testing.clear_all_data()

    def gate(self, principal, *args, **kwargs):
        """Invoke require_resource_permission under a synthetic
        principal (a dict of flask.g attributes), inside the operator
        env so the bypass is exercisable."""
        from campus.auth import authz

        with (
            mock.patch.dict(os.environ, OPERATOR_ENV),
            self.app.test_request_context(),
        ):
            for attr, value in principal.items():
                setattr(flask.g, attr, value)
            authz.require_resource_permission(*args, **kwargs)

    def test_operator_bypasses_every_gate(self):
        self.gate(
            {"current_client": operator_client()}, "users", "admin"
        )
        self.gate(
            {"current_client": operator_client()}, "clients", "write"
        )

    def test_user_with_row_and_scope_passes(self):
        from campus.auth.resources.grant import grants
        grants.grant("user", "u1", "users", level="admin")
        self.gate(
            {"current_user": user_principal("u1", ["users:admin"])},
            "users", "write",
        )
        # Monotonic: the row and the scope each cover the lower level
        self.gate(
            {"current_user": user_principal("u1", ["users:admin"])},
            "users", "read",
        )

    def test_user_row_without_scope_is_denied(self):
        from campus.auth.resources.grant import grants
        grants.grant("user", "u1", "users", level="admin")
        with self.assertRaises(api_errors.ForbiddenError):
            self.gate(
                {"current_user": user_principal("u1", [])},
                "users", "write",
            )

    def test_user_scope_without_row_is_denied(self):
        with self.assertRaises(api_errors.ForbiddenError):
            self.gate(
                {"current_user": user_principal("u1", ["users:admin"])},
                "users", "write",
            )

    def test_user_with_neither_leg_is_denied(self):
        with self.assertRaises(api_errors.ForbiddenError):
            self.gate(
                {"current_user": user_principal("u1", ["read"])},
                "users", "read",
            )

    def test_user_row_below_required_level_is_denied(self):
        from campus.auth.resources.grant import grants
        grants.grant("user", "u1", "users", level="read")
        with self.assertRaises(api_errors.ForbiddenError):
            self.gate(
                {"current_user": user_principal("u1", ["users:admin"])},
                "users", "write",
            )

    def test_user_scope_below_required_level_is_denied(self):
        from campus.auth.resources.grant import grants
        grants.grant("user", "u1", "users", level="admin")
        with self.assertRaises(api_errors.ForbiddenError):
            self.gate(
                {"current_user": user_principal("u1", ["users:mod"])},
                "users", "write",
            )

    def test_user_denied_on_the_reserved_vault_vocabulary(self):
        from campus.auth.resources.grant import grants
        # Even a vault-shaped grant row must not open the vocabulary
        grants.grant("client", LIMITED_ID, "vault", "email", bits=15)
        with self.assertRaises(api_errors.ForbiddenError):
            self.gate(
                {"current_user": user_principal("u1", ["read"])},
                "vault", "read", instance="email",
            )

    def test_user_never_inherits_the_operator_role(self):
        # A user bearer minted through the operator client sets
        # current_client to it (#854): the user leg is consulted
        # first, so the bypass must not fire.
        with self.assertRaises(api_errors.ForbiddenError):
            self.gate(
                {
                    "current_user": user_principal("u1", []),
                    "current_client": operator_client(),
                },
                "users", "read",
            )

    def test_client_denied_on_level_vocabularies(self):
        from campus.auth.resources.grant import grants
        # Even a grant row naming the client confers nothing (#854:
        # clients are never designated admins)
        grants.grant("client", LIMITED_ID, "users", level="admin")
        with self.assertRaises(api_errors.ForbiddenError):
            self.gate(
                {"current_client": limited_client()}, "users", "read"
            )

    def test_unauthenticated_caller_denied_everywhere(self):
        with self.assertRaises(api_errors.ForbiddenError):
            self.gate({}, "users", "read")
        with self.assertRaises(api_errors.ForbiddenError):
            self.gate(
                {"current_client": limited_client()},
                "vault", instance="email", bits=1,
            )

    def test_malformed_row_fails_closed(self):
        from campus.auth.resources.grant import grant_storage
        from campus.common import schema
        from campus.common.utils import uid
        grant_storage.insert_one({
            "id": uid.generate_category_uid("grant", length=8),
            "created_at": schema.DateTime.utcnow(),
            "grantee_type": "user",
            "grantee_id": "u1",
            "resource_type": "users",
            "resource_id": "",
            "bits": None,
            "level": None,
        })
        with self.assertRaises(api_errors.ForbiddenError):
            self.gate(
                {"current_user": user_principal("u1", ["users:admin"])},
                "users", "read",
            )


class TestVaultWrapper(unittest.TestCase):
    """require_vault_permission keeps its #854 behavior (#885)."""

    @classmethod
    def setUpClass(cls):
        """Configure test storage and init the schemas."""
        import campus.storage.testing

        campus.storage.testing.configure_test_storage()
        campus.storage.testing.configure_test_db()

        from campus.auth.resources.grant import GrantsResource
        GrantsResource.init_storage()

        from campus.auth.resources.client import ClientsResource
        ClientsResource.init_storage()

        cls.app = flask.Flask(__name__)

    @classmethod
    def tearDownClass(cls):
        """Clean test storage after all tests."""
        import campus.storage.testing
        campus.storage.testing.clear_all_data()

    def setUp(self):
        """Clean storage before each test without destroying schema."""
        import campus.storage.testing
        campus.storage.testing.clear_all_data()

    def vault_gate(self, principal, label, permission):
        from campus.auth import authz

        with (
            mock.patch.dict(os.environ, OPERATOR_ENV),
            self.app.test_request_context(),
        ):
            for attr, value in principal.items():
                setattr(flask.g, attr, value)
            authz.require_vault_permission(label, permission)

    def test_operator_bypasses_bitflags(self):
        self.vault_gate({"current_client": operator_client()}, "any", 15)

    def test_client_with_bits_passes_and_missing_bits_deny(self):
        from campus.auth.resources.grant import grants
        from campus.model.client import ClientAccess
        grants.grant("client", LIMITED_ID, "vault", "email", bits=1)
        self.vault_gate(
            {"current_client": limited_client()},
            "email", ClientAccess.READ,
        )
        with self.assertRaises(api_errors.ForbiddenError):
            self.vault_gate(
                {"current_client": limited_client()},
                "email", ClientAccess.DELETE,
            )
        with self.assertRaises(api_errors.ForbiddenError):
            self.vault_gate(
                {"current_client": limited_client()},
                "ungranted", ClientAccess.READ,
            )

    def test_user_bearer_denied_before_operator_inheritance(self):
        # The #854 ordering: user principals are settled before the
        # operator bypass, so a user minted through the operator
        # client is still denied on vault labels.
        with self.assertRaises(api_errors.ForbiddenError):
            self.vault_gate(
                {
                    "current_user": user_principal("u1", ["read"]),
                    "current_client": operator_client(),
                },
                "email", 1,
            )

    def test_no_principal_requires_a_client(self):
        with self.assertRaises(api_errors.ForbiddenError):
            self.vault_gate({}, "email", 1)


if __name__ == "__main__":
    unittest.main()
