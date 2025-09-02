"""tests.fixtures.storage

Functions for initialising campus.storage for testing use
"""

from . import require, setup


def init():
    """Initialize storage fixtures for testing.

    This function:
    - Initializes 'storage' vault label
    - Sets POSTGRESDB_URI as a vault secret (not environment variable)
    - Gives client access to 'storage' label

    ENV must be 'testing' and client credentials must be set before calling.
    """
    require.env("testing")
    client_id = require.envvar("CLIENT_ID")
    require.envvar("CLIENT_SECRET")

    import campus.vault

    # Give test client access to storage vault
    campus.vault.access.grant_access(
        client_id=client_id,
        label="storage",
        access=campus.vault.access.ALL
    )

    # Set up storage vault with database URI as a secret
    storage_vault = campus.vault.get_vault("storage")
    db_uri = setup.get_db_uri("storagedb")
    storage_vault.set("POSTGRESDB_URI", db_uri)
