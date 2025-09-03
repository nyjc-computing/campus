"""tests.fixtures.storage

Functions for initialising campus.storage for testing use
"""

from . import mongodb, postgres, require, setup


def init():
    """Initialize storage fixtures for testing.

    This function:
    - Ensures PostgreSQL storagedb database exists
    - Ensures MongoDB storagedb database exists  
    - Initializes 'storage' vault label
    - Sets POSTGRESDB_URI and MONGODB_URI as vault secrets
    - Sets MONGODB_NAME as vault secret
    - Gives client access to 'storage' label

    ENV must be 'testing' and client credentials must be set before calling.
    """
    require.env("testing")
    client_id = require.envvar("CLIENT_ID")
    require.envvar("CLIENT_SECRET")

    postgres.ensure_database_exists("storagedb")
    mongodb.ensure_database_exists("storagedb")

    # Give test client access to storage vault
    import campus.vault
    campus.vault.access.grant_access(
        client_id=client_id,
        label="storage",
        access=campus.vault.access.ALL
    )

    # Set up storage vault with database URIs as secrets
    storage_vault = campus.vault.get_vault("storage")

    # PostgreSQL URI
    postgres_uri = setup.get_db_uri("storagedb")
    storage_vault.set("POSTGRESDB_URI", postgres_uri)

    # MongoDB URI and database name
    mongodb_uri = mongodb.get_mongodb_uri("storagedb")
    storage_vault.set("MONGODB_URI", mongodb_uri)
    storage_vault.set("MONGODB_NAME", "storagedb")
