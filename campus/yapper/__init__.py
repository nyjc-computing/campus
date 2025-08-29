"""campus.yapper

A message broker client for Campus, in Python.

This package provides the Yapper class for sending and receiving events.
"""
# This file is required to make this directory a package.
# See https://docs.python.org/3/tutorial/modules.html#packages for more
# information.

import os

from .base import Event, EventHandler, YapperInterface
from .backends.sqlite import SQLiteYapper
from .backends.postgres import PostgreSQLYapper


def create(**kwargs) -> YapperInterface:
    """Factory function to get a Yapper client instance.

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
        case "development" | "testing" | "staging" | "production":
            yapperdb_uri = os.getenv("YAPPERDB_URI")
            if not yapperdb_uri:
                raise ValueError(
                    f"YAPPERDB_URI environment variable is required for {env} environment. "
                    "Please provide a PostgreSQL connection URI via YAPPERDB_URI."
                )
            yapper = PostgreSQLYapper(client_id, db_uri=yapperdb_uri, **kwargs)
            yapper._init_db()
            return yapper

    raise ValueError(
        f"Unsupported ENV value: {env}. "
        "Use 'development', 'testing', 'staging', or 'production'."
    )


# The __all__ variable is used to define the public API of this module.
# See https://docs.python.org/3/tutorial/modules.html#importing-from-a-package
# for more information.
__all__ = [
    "Event",
    "EventHandler",
    "YapperInterface",
    "create",
]
