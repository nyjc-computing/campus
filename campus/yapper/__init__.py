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

    from .backends.sqlite import SQLiteYapper
    from .backends.postgres import PostgreSQLYapper

    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")
    env = os.getenv("ENV", "development").lower()

    if not client_id:
        raise ValueError("CLIENT_ID environment variable is required")
    if not client_secret:
        raise ValueError("CLIENT_SECRET environment variable is required")

    # Determine backend based on environment
    match env:
        # case "development" | "testing":
        #     yapper = SQLiteYapper(client_id, **kwargs)
        #     yapper._init_db()
        #     return yapper
        # For now, use the development branch of the yapper db for testing
        # YAPPERDB_URI must be appropriately configured for each environment using yapper.
        case  "development" | "testing" | "staging" | "production":
            try:
                vault = campus_python.Campus().auth.vaults["yapper"]
                yapperdb_uri = vault["YAPPERDB_URI"]
            except Exception as e:
                raise ValueError(
                    f"Failed to retrieve YAPPERDB_URI from vault service for {env} environment. "
                    f"Vault error: {e}. "
                    f"This could indicate vault service connectivity issues or authentication problems."
                ) from e
                
            if not yapperdb_uri:
                raise ValueError(
                    f"YAPPERDB_URI environment variable is required for {env} environment. "
                    "Please provide a PostgreSQL connection URI via YAPPERDB_URI."
                )
            yapper = PostgreSQLYapper(db_uri=yapperdb_uri, **kwargs)
            yapper._init_db()
            return yapper

    raise ValueError(
        f"Unsupported ENV value: {env}. "
        "Use 'development', 'testing', 'staging', or 'production'."
    )
