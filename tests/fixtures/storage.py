"""tests.fixtures.storage

Functions for initialising campus.storage for testing use
"""

from . import mongodb, postgres, require, setup


def init():
    """Initialize storage fixtures for testing.

    This function:
    - Ensures PostgreSQL storagedb database exists (skipped in SQLite test mode)
    - Ensures MongoDB storagedb database exists (skipped in SQLite test mode)
    - Initializes 'storage' vault label
    - Sets POSTGRESDB_URI and MONGODB_URI as vault secrets
    - Sets MONGODB_NAME as vault secret
    - Gives client access to 'storage' label

    ENV must be 'testing' and client credentials must be set before calling.
    """
    require.env("testing")
    client_id = require.envvar("CLIENT_ID")
    require.envvar("CLIENT_SECRET")

    # Skip database setup if using in-memory SQLite for testing
    import campus.storage.testing
    if not campus.storage.testing.is_test_mode():
        postgres.ensure_database_exists("storagedb")
        mongodb.ensure_database_exists("storagedb")

    from campus.auth import resources as auth_resources
    from campus.model.client import ClientAccess

    # Give test client access to vault
    client_resource = auth_resources.client[client_id]
    client_resource.access.grant("campus.api", ClientAccess.ALL)

    # Set up vault with database URIs as secrets
    storage_vault = auth_resources.vault["campus.api"]

    # In test mode, use dummy URIs since we're using SQLite
    if campus.storage.testing.is_test_mode():
        storage_vault["POSTGRESDB_URI"] = "sqlite:///:memory:"
        storage_vault["MONGODB_URI"] = "mongodb://localhost:27017"
        storage_vault["MONGODB_NAME"] = "storagedb"
    else:
        # PostgreSQL URI
        postgres_uri = setup.get_db_uri("storagedb")
        storage_vault["POSTGRESDB_URI"] = postgres_uri

        # MongoDB URI and database name
        mongodb_uri = mongodb.get_mongodb_uri("storagedb")
        storage_vault["MONGODB_URI"] = mongodb_uri
        storage_vault["MONGODB_NAME"] = "storagedb"
