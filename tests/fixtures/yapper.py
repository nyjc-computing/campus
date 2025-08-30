"""tests.fixtures.yapper

Functions for initialising campus.yapper for testing use
"""

from . import require, vault

def init_yapper():
    """Populate campus.yapper with required data for testing.

    ENV must be 'testing' and client credentials must be set before calling
    this function.
    """
    require.env("testing")
    client_id = require.envvar("CLIENT_ID")
    require.envvar("CLIENT_SECRET")

    # Vault must already be initialised
    # Test client must have access to yapper secrets
    vault.give_vault_access("yapper", all=True)
    
    import campus.vault

    # campus.yapper needs YAPPERDB_URI; use local instance
    yapper_vault = campus.vault.get_vault("yapper")
    yapper_vault.set(
        "YAPPERDB_URI",
        "postgresql://devuser:devpass@db:5432/yapperdb"
    )
