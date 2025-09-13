"""tests.fixtures.setup

Functions for setting up testing environment fixtures common to all tests.
"""

import os


def set_test_env_vars():
    """Set basic testing environment variables."""
    os.environ["ENV"] = "testing"


def set_postgres_env_vars():
    """Set PostgreSQL environment variables for devcontainer setup."""
    os.environ["PGHOST"] = "postgres"
    os.environ["PGPORT"] = "5432"
    os.environ["PGUSER"] = "devuser"
    os.environ["PGPASSWORD"] = "devpass"


def set_mongodb_env_vars():
    """Set MongoDB environment variables for devcontainer setup."""
    os.environ["MONGODB_HOST"] = "mongo"
    os.environ["MONGODB_PORT"] = "27017"
    os.environ["MONGO_INITDB_ROOT_USERNAME"] = "devuser"
    os.environ["MONGO_INITDB_ROOT_PASSWORD"] = "devpass"


def get_db_uri(database_name: str) -> str:
    """Get a database URI string using existing postgres env vars.

    Args:
        database_name: Name of the database (e.g., "vaultdb")

    Returns:
        Database URI string

    Raises:
        OSError: If required postgres environment variables are not set
    """
    host = os.environ["PGHOST"]
    port = os.environ["PGPORT"]
    user = os.environ["PGUSER"]
    password = os.environ["PGPASSWORD"]

    return f"postgresql://{user}:{password}@{host}:{port}/{database_name}"


def set_db_uri(env_var_name: str, database_name: str):
    """Set a database URI environment variable using existing postgres env vars.

    Args:
        env_var_name: Name of the environment variable to set (e.g., "VAULTDB_URI")
        database_name: Name of the database (e.g., "vaultdb")

    Raises:
        OSError: If required postgres environment variables are not set
    """
    uri = get_db_uri(database_name)
    os.environ[env_var_name] = uri
