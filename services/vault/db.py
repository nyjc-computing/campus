"""services.vault.db

Direct PostgreSQL database access for the vault service.

This module provides direct PostgreSQL connectivity to avoid circular dependencies
with the storage module. The vault needs to be independent since other services
may depend on it for secrets management.

Lazy Loading Pattern:
This module uses lazy loading to defer importing psycopg2 until first use. This improves
startup time and reduces memory usage when the vault is not needed.

Implementation:
- psycopg2 imports are in TYPE_CHECKING block for type hints only
- Runtime placeholders (_psycopg2, _RealDictCursor) start as None
- Private function _get_psycopg2_modules() handles lazy loading implementation details
- importlib.import_module() loads modules on first database operation
- Global variables cache imports to avoid repeated loading

Benefits:
- Faster application startup when vault not immediately needed
- Reduced memory footprint in applications that don't use vault
- Optional dependency - apps can run without psycopg2 if vault unused

Environment Variables:
- VAULTDB_URI: PostgreSQL connection string for vault database (required)

Usage:
    from services.vault.db import get_connection, execute_query
    
    with get_connection() as conn:
        results = execute_query(conn, "SELECT * FROM vault WHERE label = %s", ("api-keys",))
"""

import importlib
import os
from contextlib import contextmanager
from typing import Generator, Any, Optional, TypeAlias, TYPE_CHECKING

# Lazy Loading Pattern Implementation:
# Import database modules only for type checking, not at runtime
if TYPE_CHECKING:
    import psycopg2
    from psycopg2.extras import RealDictCursor

_PsycoConn: TypeAlias = "psycopg2.extensions.connection"

# Runtime placeholders - start as None, populated on first use
_psycopg2: Any | None = None   # Will hold psycopg2 module when loaded
_RealDictCursor: Any | None = None   # Will hold RealDictCursor class when loaded


def _get_psycopg2_modules():
    """Get psycopg2 modules, loading them lazily on first use.
    
    Returns:
        Tuple of (psycopg2 module, RealDictCursor class)
        
    Note:
        This function handles the lazy loading implementation details,
        keeping the business logic in connection methods clean and focused.
    """
    global _psycopg2, _RealDictCursor
    if _psycopg2 is None:      # Lazy loading: import only on first real use
        _psycopg2 = importlib.import_module("psycopg2")
        _RealDictCursor = importlib.import_module(
            "psycopg2.extras").RealDictCursor
    return _psycopg2, _RealDictCursor


def get_connection() -> _PsycoConn:
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

    # Get psycopg2 modules (lazy loaded)
    psycopg2_module, real_dict_cursor = _get_psycopg2_modules()
    
    # Use the dynamically imported modules
    conn = psycopg2_module.connect(vault_db_uri, cursor_factory=real_dict_cursor)
    conn.autocommit = False
    return conn


@contextmanager
def get_connection_context() -> Generator[_PsycoConn, None, None]:
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
    conn: _PsycoConn,
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
    with conn.cursor() as cursor:
        cursor.execute(query, params)

        if fetch_one:
            row = cursor.fetchone()
            return dict(row) if row else None
        elif fetch_all:
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        else:
            return None
