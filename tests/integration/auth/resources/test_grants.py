"""campus.tests.integration.auth.resources.test_grants

Integration tests for the access-grant store (#883, #884).

Covers GrantsResource — the generalized (grantee, resource,
permission) store behind the epic — and ClientAccessResource, the
vault compatibility layer that must keep the pre-#884 vault_access
semantics (OR-on-grant, clear-on-revoke, delete-at-zero,
replace-on-update) against the same rows.

IMPORTANT: Lazy imports are required to avoid storage initialization
before test mode is configured (see AGENTS.md - Storage Initialization
Order).
"""

import unittest

from campus.common.errors import api_errors


class GrantsTestCase(unittest.TestCase):
    """Shared fixture: tmpfile SQLite backend, schema initialized."""

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

    @classmethod
    def tearDownClass(cls):
        """Clean test storage after all tests."""
        import campus.storage.testing
        campus.storage.testing.clear_all_data()

    def setUp(self):
        """Clean storage before each test without destroying schema."""
        import campus.storage.testing
        campus.storage.testing.clear_all_data()


class TestGrantsStore(GrantsTestCase):
    """GrantsResource semantics per resource grammar."""

    def test_vault_grant_ors_into_existing_mask(self):
        from campus.auth.resources.grant import grants
        grants.grant("client", "cl_a", "vault", "label1", bits=1)
        grants.grant("client", "cl_a", "vault", "label1", bits=2)
        row = grants.get("client", "cl_a", "vault", "label1")
        self.assertEqual(int(row["bits"]), 3)

    def test_vault_revoke_clears_bits_and_deletes_at_zero(self):
        from campus.auth.resources.grant import grants
        grants.grant("client", "cl_a", "vault", "label1", bits=3)
        grants.revoke("client", "cl_a", "vault", "label1", bits=1)
        self.assertEqual(
            int(grants.get("client", "cl_a", "vault", "label1")["bits"]),
            2,
        )
        grants.revoke("client", "cl_a", "vault", "label1", bits=2)
        self.assertIsNone(grants.get("client", "cl_a", "vault", "label1"))

    def test_vault_update_replaces_and_zero_deletes(self):
        from campus.auth.resources.grant import grants
        grants.update("client", "cl_a", "vault", "label1", bits=3)
        grants.update("client", "cl_a", "vault", "label1", bits=4)
        self.assertEqual(
            int(grants.get("client", "cl_a", "vault", "label1")["bits"]),
            4,
        )
        grants.update("client", "cl_a", "vault", "label1", bits=0)
        self.assertIsNone(grants.get("client", "cl_a", "vault", "label1"))

    def test_vault_check_matches_any_held_bit(self):
        from campus.auth.resources.grant import grants
        grants.grant("client", "cl_a", "vault", "label1", bits=2)
        self.assertTrue(
            grants.check("client", "cl_a", "vault", "label1", bits=6)
        )
        self.assertFalse(
            grants.check("client", "cl_a", "vault", "label1", bits=1)
        )
        # A vacuous mask checks False (the pre-#884 held & 0 semantics)
        self.assertFalse(
            grants.check("client", "cl_a", "vault", "label1", bits=0)
        )

    def test_level_grant_never_downgrades(self):
        from campus.auth.resources.grant import grants
        grants.grant("user", "u1", "users", level="read")
        grants.grant("user", "u1", "users", level="write")
        self.assertEqual(
            grants.get("user", "u1", "users")["level"], "write"
        )
        grants.grant("user", "u1", "users", level="mod")
        self.assertEqual(
            grants.get("user", "u1", "users")["level"], "write"
        )

    def test_level_revoke_guarantees_revoked_level_fails_check(self):
        from campus.auth.resources.grant import grants
        grants.grant("user", "u1", "users", level="admin")
        grants.revoke("user", "u1", "users", level="read")
        self.assertIsNone(grants.get("user", "u1", "users"))
        grants.grant("user", "u1", "users", level="read")
        grants.revoke("user", "u1", "users", level="write")
        self.assertIsNotNone(grants.get("user", "u1", "users"))

    def test_level_check_uses_monotonic_algebra(self):
        from campus.auth.resources.grant import grants
        grants.grant("user", "u1", "clients", level="write")
        self.assertTrue(
            grants.check("user", "u1", "clients", level="write")
        )
        self.assertTrue(
            grants.check("user", "u1", "clients", level="read")
        )
        self.assertFalse(
            grants.check("user", "u1", "clients", level="admin")
        )
        # A different resource's grant never matches
        self.assertFalse(
            grants.check("user", "u1", "users", level="read")
        )

    def test_validation_rejects_mixed_permission_legs(self):
        from campus.auth.resources.grant import grants
        with self.assertRaises(api_errors.InvalidRequestError):
            grants.grant("client", "cl_a", "users", bits=1)
        with self.assertRaises(api_errors.InvalidRequestError):
            grants.grant("client", "cl_a", "vault", "l", level="read")
        with self.assertRaises(api_errors.InvalidRequestError):
            grants.grant("client", "cl_a", "vault", "l", bits=16)
        with self.assertRaises(api_errors.InvalidRequestError):
            grants.grant("user", "u1", "users", level="owner")
        with self.assertRaises(api_errors.InvalidRequestError):
            grants.grant("service", "s1", "users", level="read")
        with self.assertRaises(api_errors.InvalidRequestError):
            grants.grant("user", "u1", "posts", level="read")

    def test_list_filters_the_matrix(self):
        from campus.auth.resources.grant import grants
        grants.grant("user", "u1", "users", level="admin")
        grants.grant("user", "u1", "clients", level="read")
        grants.grant("client", "cl_a", "vault", "label1", bits=3)
        self.assertEqual(
            len(grants.list(grantee_type="user", grantee_id="u1")), 2
        )
        self.assertEqual(len(grants.list(resource_type="vault")), 1)
        self.assertEqual(len(grants.list()), 3)


class TestClientAccessCompat(GrantsTestCase):
    """ClientAccessResource preserves vault_access semantics (#884)."""

    def test_round_trip_through_the_grant_store(self):
        from campus.auth.resources.client import ClientsResource
        access = ClientsResource()["cl_compat"].access

        access.grant("label1", 1)
        self.assertEqual(access.get("label1"), 1)
        access.grant("label1", 2)
        self.assertEqual(access.get("label1"), 3)
        self.assertEqual(access.list(), {"label1": 3})
        self.assertTrue(access.check("label1", 2))

        access.revoke("label1", 1)
        self.assertEqual(access.get("label1"), 2)
        access.update("label1", 8)
        self.assertEqual(access.get("label1"), 8)
        access.update("label1", 0)
        self.assertEqual(access.get("label1"), 0)

        from campus.auth.resources.grant import grants
        self.assertIsNone(
            grants.get("client", "cl_compat", "vault", "label1")
        )

    def test_rows_written_via_grants_store_surface_in_access(self):
        from campus.auth.resources.client import ClientsResource
        from campus.auth.resources.grant import grants
        grants.grant("client", "cl_b", "vault", "shared", bits=5)

        access = ClientsResource()["cl_b"].access
        self.assertEqual(access.get("shared"), 5)
        self.assertEqual(access.list(), {"shared": 5})


if __name__ == "__main__":
    unittest.main()
