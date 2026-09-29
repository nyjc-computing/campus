"""campus.tests.integration.auth.resources.test_client_seed

Integration tests for the public OAuth client seed.

These tests verify campus.auth.resources.client.ensure_public_client(),
which creates the 'guest' public client (RFC 6749 Section 2.1) used by
the OAuth 2.0 Device Authorization Flow, and must self-heal a missing
row at service startup (#605).

IMPORTANT: Lazy imports are required to avoid storage initialization
before test mode is configured (see AGENTS.md - Storage Initialization Order).
"""

import unittest


class TestEnsurePublicClient(unittest.TestCase):
    """Integration tests for ensure_public_client().

    These tests use the tmpfile-based SQLite pattern for reliable test isolation.
    The database file persists across tests with clear_all_data() providing
    per-test cleanup without destroying the schema.
    """

    @classmethod
    def setUpClass(cls):
        """Configure test storage and import the seed once before all tests."""
        import campus.storage.testing

        # Configure test mode first
        campus.storage.testing.configure_test_storage()

        # Configure tmpfile-based database (fixed path, avoids readonly errors)
        campus.storage.testing.configure_test_db()

        # Lazy import after test mode is configured
        from campus.auth.resources.client import ClientsResource

        # Initialize storage schema (creates tables in the tmpfile database)
        ClientsResource.init_storage()

        cls.ClientsResource = ClientsResource

    @classmethod
    def tearDownClass(cls):
        """Clean up test storage after all tests."""
        import campus.storage.testing
        # Only clear data, don't reset database (preserves connections)
        campus.storage.testing.clear_all_data()

    def setUp(self):
        """Clean storage before each test without destroying schema."""
        import campus.storage.testing
        campus.storage.testing.clear_all_data()

    def _get_seed(self):
        """Lazy-import the seed function under test."""
        from campus.auth.resources.client import ensure_public_client
        return ensure_public_client

    def test_creates_client_when_missing(self):
        """The seed creates the public client in an empty database."""
        import campus.config
        from campus.auth.resources.client import client_storage

        created = self._get_seed()()

        self.assertTrue(created)
        record = client_storage.get_by_id(
            campus.config.PUBLIC_OAUTH_CLIENT_ID
        )
        self.assertEqual(record["id"], campus.config.PUBLIC_OAUTH_CLIENT_ID)
        self.assertTrue(record["is_public"])
        # RFC 6749 Section 2.1: public clients have no secret
        self.assertIsNone(record["secret_hash"])

    def test_seed_is_idempotent(self):
        """Re-running the seed reports no creation and adds no rows."""
        from campus.auth.resources.client import client_storage

        seed = self._get_seed()
        self.assertTrue(seed())
        self.assertFalse(seed())
        self.assertFalse(seed())

        records = client_storage.get_matching({})
        self.assertEqual(len(records), 1)

    def test_seed_does_not_modify_existing_client(self):
        """An existing client with the public client ID is left untouched."""
        import campus.config
        from campus.auth.resources.client import client_storage

        # Pre-create a client occupying the public client ID with
        # different values than the seed would use
        self.ClientsResource().new(
            id=campus.config.PUBLIC_OAUTH_CLIENT_ID,
            name="Pre-existing Client",
            description="Created before the seed ran",
            is_public=True,
        )

        created = self._get_seed()()

        self.assertFalse(created)
        record = client_storage.get_by_id(
            campus.config.PUBLIC_OAUTH_CLIENT_ID
        )
        self.assertEqual(record["name"], "Pre-existing Client")
        self.assertEqual(record["description"], "Created before the seed ran")

    def test_seeded_client_passes_resource_get(self):
        """The seeded record is readable through the client resource."""
        import campus.config
        from campus.auth.resources.client import ClientsResource

        self._get_seed()()

        client = ClientsResource()[campus.config.PUBLIC_OAUTH_CLIENT_ID].get()
        self.assertTrue(client.is_public)
        self.assertIsNone(client.secret_hash)
        self.assertIn(
            "urn:ietf:wg:oauth:2.0:oob",
            client.redirect_uris
        )


if __name__ == "__main__":
    unittest.main()
