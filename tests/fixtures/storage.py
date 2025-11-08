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

    # Use the new auth resources instead of deprecated campus.vault
    from campus.auth.resources import vault as auth_vault
    from campus.auth.resources import client as auth_client
    from campus.model.client import Client as ModelClient

    # Give test client access to storage vault
    client_res = auth_client[client_id]
    client_res.access.grant("campus.api", ModelClient.access.ALL)

    # Set up storage vault with database URIs as secrets
    storage_vault = auth_vault["campus.api"]

    # PostgreSQL URI
    postgres_uri = setup.get_db_uri("storagedb")
    storage_vault["POSTGRESDB_URI"] = postgres_uri

    # MongoDB URI and database name
    mongodb_uri = mongodb.get_mongodb_uri("storagedb")
    storage_vault["MONGODB_URI"] = mongodb_uri
    storage_vault["MONGODB_NAME"] = "storagedb"
