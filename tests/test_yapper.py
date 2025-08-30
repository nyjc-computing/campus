import unittest
import os

from tests.fixtures.setup import set_test_env_vars
from tests.fixtures.vault import init_vault, give_vault_access
from tests.fixtures.yapper import init_yapper

class TestYapper(unittest.TestCase):
    
    def test_setup_vars(self):
        set_test_env_vars()
        self.assertIsNotNone(os.environ["VAULTDB_URI"])
    
    def test_vault_vars_and_access(self):
        init_vault()
        self.assertIsNotNone(os.environ["CLIENT_SECRET"])
        self.assertIsNotNone(os.environ["CLIENT_ID"])
        
        give_vault_access("yapper", all=True)
    
    def test_yapper_vars(self):
        init_yapper()
        self.assertIsNotNone(os.environ["YAPPERDB_URI"])

if __name__ == "__main__":
    unittest.main()
