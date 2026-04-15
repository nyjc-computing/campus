"""campus.yapper

A message broker client for Campus, in Python.

This package provides the Yapper class for sending and receiving events.
"""
# This file is required to make this directory a package.
# See https://docs.python.org/3/tutorial/modules.html#packages for more
# information.

# The __all__ variable is used to define the public API of this module.
# See https://docs.python.org/3/tutorial/modules.html#importing-from-a-package
# for more information.
__all__ = [
    "Event",
    "EventHandler",
    "YapperInterface",
    "create",
]

from .base import Event, EventHandler, YapperInterface


def create(**kwargs) -> YapperInterface:
    """Factory function to get a Yapper client instance.

    # TODO: Update docstring (https://github.com/nyjc-computing/campus/issues/177)

    Environment variables:
        CLIENT_ID: Unique identifier for the client (required)
        CLIENT_SECRET: Client secret for authentication (required)
        ENV: Environment type that determines backend ("development", "testing", "staging", "production")
             - "development" or "testing": SQLiteYapper
             - "staging" or "production": PostgreSQLYapper
        YAPPERDB_URI: PostgreSQL connection URI (required for staging/production)
        STORAGE_MODE: If "1", use local resources for testing (no external services)

    Args:
        **kwargs: Backend-specific arguments:
            - For SQLite (development/testing):
                - db (optional): Database file path, defaults to ":memory:"

    Returns:
        YapperInterface: A backend-specific Yapper instance

    Raises:
        ValueError: If CLIENT_ID or CLIENT_SECRET environment variables are not set,
                   or if YAPPERDB_URI is not set for PostgreSQL environments
    """
    # Lazy-import locally to avoid polluting global namespace
    import os

    import campus_python

    from .backends.postgres import PostgreSQLYapper
    from .backends.sqlite import SQLiteYapper

    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")
    env = os.getenv("ENV", "development").lower()
    storage_mode = os.getenv("STORAGE_MODE", "0")

    if not client_id:
        raise ValueError("CLIENT_ID environment variable is required")
    if not client_secret:
        raise ValueError("CLIENT_SECRET environment variable is required")

    # In test mode (STORAGE_MODE=1), use local auth resources directly
    # to avoid connecting to external services
    if storage_mode == "1":
        from campus.auth import resources as auth_resources
        yapper_vault = auth_resources.vault["yapper"]
        yapperdb_uri = yapper_vault["YAPPERDB_URI"]
        yapper = SQLiteYapper(db=yapperdb_uri, client_id=client_id, **kwargs)
        yapper._init_db()
        return yapper

    # For campus.auth deployment, use local resources to avoid circular dependency
    # (service trying to call its own HTTP API during initialization)
    deploy = os.getenv("DEPLOY")
    if deploy == "campus.auth":
        from campus.auth import resources as auth_resources
        yapper_vault = auth_resources.vault["yapper"]
        yapperdb_uri = yapper_vault["YAPPERDB_URI"]
        yapper = PostgreSQLYapper(db_uri=yapperdb_uri, client_id=client_id, **kwargs)
        yapper._init_db()
        return yapper

    # For other deployments, use campus_python to connect to remote vault
    # Create Campus client for vault access
    campus = campus_python.Campus(timeout=60)

    # Determine backend based on environment
    match env:
        case  "development" | "testing" | "staging" | "production":
            try:
                yapper_vault = campus.auth.vaults["campus.yapper"]
                yapperdb_uri = yapper_vault["YAPPERDB_URI"]
            except Exception as e:
                raise ValueError(
                    f"Failed to retrieve YAPPERDB_URI from vault 'campus.yapper' for {env} environment. "
                    f"Vault error: {e}. "
                    f"This could indicate vault service connectivity issues or authentication problems."
                ) from e

            if not yapperdb_uri:
                raise ValueError(
                    f"YAPPERDB_URI environment variable is required for {env} environment. "
                    "Please provide a PostgreSQL connection URI via YAPPERDB_URI."
                )
            yapper = PostgreSQLYapper(db_uri=yapperdb_uri, client_id=client_id, **kwargs)
            yapper._init_db()
            return yapper

    raise ValueError(
        f"Unsupported ENV value: {env}. "
        "Use 'development', 'testing', 'staging', or 'production'."
    )
