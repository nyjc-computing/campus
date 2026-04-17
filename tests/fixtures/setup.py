"""tests.fixtures.setup

Functions for setting up testing environment fixtures common to all tests.
"""

from campus.common import env


def set_test_env_vars():
    """Set basic testing environment variables."""
    env.set('ENV', "testing")
    # Set DEPLOY to auth service context so campus_python uses relative URLs
    # This allows tests to work with locally running services
    env.set('DEPLOY', "campus.auth")


def set_postgres_env_vars():
    """Set PostgreSQL environment variables for devcontainer setup."""
    env.set('PGHOST', "postgres")
    env.set('PGPORT', "5432")
    env.set('PGUSER', "devuser")
    env.set('PGPASSWORD', "devpass")


def set_mongodb_env_vars():
    """Set MongoDB environment variables for devcontainer setup."""
    env.set('MONGODB_HOST', "mongo")
    env.set('MONGODB_PORT', "27017")
    env.set('MONGO_INITDB_ROOT_USERNAME', "devuser")
    env.set('MONGO_INITDB_ROOT_PASSWORD', "devpass")


def get_db_uri(database_name: str) -> str:
    """Get a database URI string using existing postgres env vars.

    Args:
        database_name: Name of the database (e.g., "vaultdb")

    Returns:
        Database URI string

    Raises:
        OSError: If required postgres environment variables are not set
    """
    host = env.PGHOST
    port = env.PGPORT
    user = env.PGUSER
    password = env.PGPASSWORD

    return f"postgresql://{user}:{password}@{host}:{port}/{database_name}"


def set_db_uri(env_var_name: str, database_name: str):
    """Set a database URI environment variable using existing postgres env vars.

    Args:
        env_var_name: Name of the environment variable to set (e.g., "POSTGRESDB_URI")
        database_name: Name of the database (e.g., "storagedb")

    Raises:
        OSError: If required postgres environment variables are not set
    """
    uri = get_db_uri(database_name)
    setattr(env, env_var_name, uri)
