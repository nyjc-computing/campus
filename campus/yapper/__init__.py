"""campus.yapper

A message broker client for Campus, in Python.

This package provides the Yapper class for sending and receiving events.

yapper is self-contained: it imports no other campus package. Callers
own credential and vault access — configuration arrives through
arguments or environment variables, never by importing campus.auth
(#970 phase 2 removes that lazy import cycle).
"""

__all__ = [
    "Event",
    "EventHandler",
    "YapperInterface",
    "create",
]

from typing import Callable

from .base import Event, EventHandler, YapperInterface


def create(
    *,
    db_uri: str | None = None,
    db_uri_provider: Callable[[], str] | None = None,
    **kwargs,
) -> YapperInterface:
    """Factory function returning a backend-specific Yapper client.

    Client identity comes from the environment. The event database URI
    is resolved in priority order:

    1. ``db_uri`` argument
    2. ``db_uri_provider()`` — for callers that own local secret
       access (the auth service reads its own vault in-process;
       calling its own HTTP API during initialization would be
       circular)
    3. ``YAPPERDB_URI`` environment variable
    4. the remote campus vault "campus.yapper" via campus_python

    Environment variables:
        CLIENT_ID: Unique identifier for the client (required)
        CLIENT_SECRET: Client secret for authentication (required)
        ENV: development | testing | staging | production
        STORAGE_MODE: "1" selects the SQLite backend for testing. Test
            mode never contacts external services: the URI must arrive
            via 1-3 or create() raises.

    Args:
        db_uri: explicit database URI (highest priority)
        db_uri_provider: zero-arg callable returning the database URI
        **kwargs: backend-specific arguments (e.g. SQLite ``db`` path)

    Returns:
        YapperInterface: SQLiteYapper (STORAGE_MODE=1) or PostgreSQLYapper

    Raises:
        ValueError: If CLIENT_ID or CLIENT_SECRET are unset, if no
            database URI can be resolved, or if ENV is not supported.
    """
    # Lazy-import locally to avoid polluting global namespace
    import os

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

    yapperdb_uri = db_uri
    if yapperdb_uri is None and db_uri_provider is not None:
        yapperdb_uri = db_uri_provider()
    if yapperdb_uri is None:
        yapperdb_uri = os.getenv("YAPPERDB_URI")

    if storage_mode == "1":
        if not yapperdb_uri:
            raise ValueError(
                "STORAGE_MODE=1 (test mode) must not contact external "
                "services: provide the event database URI via the db_uri "
                "argument, a db_uri_provider callable, or YAPPERDB_URI."
            )
        yapper = SQLiteYapper(db=yapperdb_uri, client_id=client_id, **kwargs)
        yapper._init_db()
        return yapper

    if yapperdb_uri is None:
        # Resolve from the remote campus vault via campus_python.
        import campus_python

        if env not in ("development", "testing", "staging", "production"):
            raise ValueError(
                f"Unsupported ENV value: {env}. "
                "Use 'development', 'testing', 'staging', or 'production'."
            )
        campus = campus_python.Campus(timeout=60)
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
            f"YAPPERDB_URI is required for the {env} environment. "
            "Provide a database URI via the db_uri argument, a "
            "db_uri_provider callable, or YAPPERDB_URI."
        )

    yapper = PostgreSQLYapper(db_uri=yapperdb_uri, client_id=client_id, **kwargs)
    yapper._init_db()
    return yapper
