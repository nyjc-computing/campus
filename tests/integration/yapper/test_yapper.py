import unittest

from tests.fixtures import services
from campus.common import env


class TestYapper(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Set up local services once for the entire test class."""
        cls.service_manager = services.create_service_manager()
        cls.service_manager.setup()

    @classmethod
    def tearDownClass(cls):
        """Clean up services after all tests in the class."""
        if hasattr(cls, 'service_manager'):
            cls.service_manager.close()

        # Reset test storage to clear SQLite in-memory database
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

    def test_setup_vars(self):
        # After service setup, VAULTDB_URI should be available
        self.assertIsNotNone(env.VAULTDB_URI)

    def test_vault_vars_and_access(self):
        # After service setup, vault credentials should be available
        self.assertIsNotNone(env.CLIENT_SECRET)
        self.assertIsNotNone(env.CLIENT_ID)

    def test_yapper_vars(self):
        # The yapper database URI should be stored in the vault after service setup
        # Test that yapper can access its vault data through the proper service boundary
        import campus_python

        campus = campus_python.Campus(timeout=60)
        yapper_vault = campus.auth.vaults["yapper"]
        yapperdb_uri = yapper_vault["YAPPERDB_URI"]
        self.assertIsNotNone(yapperdb_uri)

    def test_yapper_init(self):
        import campus.yapper
        self.yapperInterface = campus.yapper.create()
        self.assertIsNotNone(self.yapperInterface)


if __name__ == "__main__":
    unittest.main()
