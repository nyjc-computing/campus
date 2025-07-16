"""services.vault.db

Direct PostgreSQL database access for the vault service.

This module provides direct PostgreSQL connectivity to avoid circular dependencies
with the storage module. The vault needs to be independent since other services
may depend on it for secrets management.

Environment Variables:
- VAULTDB_URI: PostgreSQL connection string for vault database (required)

Usage:
    from services.vault.db import get_connection, execute_query
    
    with get_connection() as conn:
        results = execute_query(conn, "SELECT * FROM vault WHERE label = %s", ("api-keys",))
"""

import os
from contextlib import contextmanager
from typing import Generator, Any, Optional

import psycopg2
from psycopg2.extras import RealDictCursor


def get_connection() -> psycopg2.extensions.connection:
    """Get a PostgreSQL connection using the VAULTDB_URI environment variable.

    Returns:
        A psycopg2 connection object with autocommit disabled

    Raises:
        ValueError: If VAULTDB_URI environment variable is not set
        psycopg2.Error: If connection to database fails
    """
    vault_db_uri = os.environ.get("VAULTDB_URI")
    if not vault_db_uri:
        raise ValueError("VAULTDB_URI environment variable is required")

    conn = psycopg2.connect(vault_db_uri)
    conn.autocommit = False
    return conn


@contextmanager
def get_connection_context() -> Generator[psycopg2.extensions.connection, None, None]:
    """Context manager for PostgreSQL connections.

    Automatically handles connection cleanup and provides transaction management.
    Commits on successful completion, rolls back on exceptions.

    Yields:
        psycopg2 connection object

    Example:
        with get_connection_context() as conn:
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO vault ...")
                # Automatically commits on success
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_query(
    conn: psycopg2.extensions.connection,
    query: str,
    params: tuple = (),
    fetch_one: bool = False,
    fetch_all: bool = True
) -> Optional[Any]:
    """Execute a SQL query with parameters and return results.

    Args:
        conn: PostgreSQL connection object
        query: SQL query string with %s placeholders
        params: Tuple of parameters for the query
        fetch_one: If True, return single row (or None)
        fetch_all: If True, return all rows as list (default)

    Returns:
        - If fetch_one=True: Single row dict or None
        - If fetch_all=True: List of row dicts (can be empty)
        - If both False: None (for INSERT/UPDATE/DELETE operations)

    Example:
        # Get single record
        user = execute_query(conn, "SELECT * FROM vault WHERE id = %s", ("123",), fetch_one=True)

        # Get multiple records  
        secrets = execute_query(conn, "SELECT * FROM vault WHERE label = %s", ("api-keys",))

        # Insert/Update (no return value needed)
        execute_query(conn, "INSERT INTO vault ...", (...,), fetch_one=False, fetch_all=False)
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(query, params)

        if fetch_one:
            row = cursor.fetchone()
            return dict(row) if row else None
        elif fetch_all:
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        else:
            return None
