"""tests.fixtures.storage

Functions for initialising campus.storage for testing use
"""

from . import require, vault

def init_storage():
    """Populate campus.storage with required data for testing.

    ENV must be 'testing' and client credentials must be set before calling
    this function.
    """
    require.env("testing")
    client_id = require.envvar("CLIENT_ID")
    require.envvar("CLIENT_SECRET")

    # Vault must already be initialised
    # Test client must have access to storage secrets
    vault.give_vault_access("storage", all=True)
    
    import campus.vault

    # campus.storage needs POSTGRESDB_URI use local instance
    storage_vault = campus.vault.get_vault("storage")
    storage_vault.set(
        "POSTGRESDB_URI",
        "postgresql://devuser:devpass@db:5432/storagedb"
    )
