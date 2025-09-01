"""tests.fixtures.env

Functions for setting up the testing environment.
"""

import os

def set_test_env_vars():
    """Set environment variables for testing."""
    os.environ["ENV"] = "testing"
    os.environ["CLIENT_ID"] = "test_client"
    os.environ["CLIENT_SECRET"] = "test_secret"

def set_vault_env_vars():
    os.environ["VAULTDB_URI"] = "postgresql://vaultuser:vaultpass@db_vault:5432/vaultdb"
