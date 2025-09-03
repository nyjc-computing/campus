import unittest

from tests.fixtures import services


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
    
    def test_setup_vars(self):
        import os
        # After service setup, VAULTDB_URI should be available
        self.assertIsNotNone(os.environ.get("VAULTDB_URI"))
    
    def test_vault_vars_and_access(self):
        import os
        # After service setup, vault credentials should be available
        self.assertIsNotNone(os.environ.get("CLIENT_SECRET"))
        self.assertIsNotNone(os.environ.get("CLIENT_ID"))
    
    def test_yapper_vars(self):
        # The yapper database URI should be stored in the vault after service setup
        # We can test this by trying to get the vault value
        import campus.vault
        vault = campus.vault.get_vault("yapper")
        yapperdb_uri = vault.get("YAPPERDB_URI")
        self.assertIsNotNone(yapperdb_uri)

    def test_yapper_init(self):
        import campus.yapper
        self.yapperInterface = campus.yapper.create()
        self.assertIsNotNone(self.yapperInterface)


if __name__ == "__main__":
    unittest.main()
