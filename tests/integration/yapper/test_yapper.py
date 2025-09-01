import unittest
import os

# Set up environment variables before importing campus modules
from tests.fixtures import setup
setup.set_test_env_vars()
setup.set_vault_env_vars()

from tests.fixtures.vault import init_vault, give_vault_access
from tests.fixtures.yapper import init_yapper
import campus.yapper


class TestYapper(unittest.TestCase):
    
    def test_setup_vars(self):
        self.assertIsNotNone(os.environ["VAULTDB_URI"])
    
    def test_vault_vars_and_access(self):
        init_vault()
        self.assertIsNotNone(os.environ["CLIENT_SECRET"])
        self.assertIsNotNone(os.environ["CLIENT_ID"])
        
        give_vault_access("yapper", all=True)
    
    def test_yapper_vars(self):
        init_yapper()
        self.assertIsNotNone(os.environ["YAPPERDB_URI"])

    def test_yapper_init(self):
        self.yapperInterface = campus.yapper.create()
        self.assertIsNotNone(self.yapperInterface)

if __name__ == "__main__":
    unittest.main()
