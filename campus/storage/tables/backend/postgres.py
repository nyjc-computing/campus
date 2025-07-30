"""campus.storage.tables.backend.postgres

This module provides the PostgreSQL backend for the Tables storage interface.

Vault Integration:
The database URI is retrieved from the vault secret 'POSTGRESDB_URI' in the 'storage' 
vault. The storage system depends on the vault service for database credentials.

Implementation:
Uses direct column mapping where record keys correspond to table column names.
Tables are assumed to exist with correct schema. Record validation is handled
before storage and is not the responsibility of this module.

Usage Example:
```python
from campus.storage.tables.backend.postgres import PostgreSQLTable

table = PostgreSQLTable("users")
table.insert_one({"id": "123", "created_at": "2023-01-01", "name": "John"})
user = table.get_by_id("123")
table.update_by_id("123", {"name": "Jane"})
table.delete_by_id("123")
```
"""

import psycopg2
from psycopg2.extras import RealDictCursor

from campus.common import devops
from campus.client import Campus
from campus.storage.tables.interface import TableInterface, PK
from campus.storage.errors import NotFoundError, NoChangesAppliedError


# Singleton Campus client for this backend
_campus_client = Campus()


def _get_db_uri() -> str:
    """Get the database URI from the vault using the client API."""
    try:
        return _campus_client.vault["storage"]["POSTGRESDB_URI"].get()
    except Exception as e:
        raise RuntimeError(
            f"Failed to retrieve database URI from vault secret 'POSTGRESDB_URI' "
            f"in 'storage' vault: {e}"
        ) from e


class PostgreSQLTable(TableInterface):
    """PostgreSQL backend for the Tables storage interface.

    Uses direct column mapping: record keys correspond to table column names.

    Example:
        table = PostgreSQLTable("users")
        table.insert_one({"id": "123", "created_at": "2023-01-01", "name": "John"})
        user = table.get_by_id("123")
    """

    def _get_connection(self):
        """Get a connection to the PostgreSQL database.

        Retrieves the database URI from vault and establishes connection.

        Raises:
            RuntimeError: If vault secret retrieval fails
            psycopg2.Error: If database connection fails
        """
        db_uri = _get_db_uri()
        return psycopg2.connect(db_uri)

    @staticmethod
    def _build_where_clause(query: dict) -> tuple[str, list]:
        """Build WHERE clause from query dictionary."""
        if not query:
            return "", []

        conditions = []
        params = []

        for key, value in query.items():
            conditions.append(f"{key} = %s")
            params.append(value)

        return f"WHERE {' AND '.join(conditions)}", params

    @staticmethod
    def _build_columns_and_values(row: dict) -> tuple[str, str, list]:
        """Build column names, placeholders, and values for INSERT/UPDATE."""
        columns = list(row.keys())
        placeholders = ", ".join(["%s"] * len(columns))
        column_names = ", ".join(columns)
        values = list(row.values())

        return column_names, placeholders, values

    @staticmethod
    def _build_set_clause(update: dict) -> tuple[str, list]:
        """Build SET clause for UPDATE statements."""
        set_parts = []
        params = []

        for key, value in update.items():
            set_parts.append(f"{key} = %s")
            params.append(value)

        return ", ".join(set_parts), params

    def get_by_id(self, row_id: str) -> dict:
        """Retrieve a row by its ID."""
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    f"SELECT * FROM {self.name} WHERE {PK} = %s",
                    (row_id,)
                )
                row = cursor.fetchone()
                return dict(row) if row else {}

    def get_matching(self, query: dict) -> list[dict]:
        """Retrieve rows matching a query."""
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                where_clause, params = self._build_where_clause(query)
                sql = f"SELECT * FROM {self.name} {where_clause}"
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]

    def insert_one(self, row: dict) -> None:
        """Insert a row into the specified table."""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                column_names, placeholders, values = self._build_columns_and_values(
                    row)

                cursor.execute(
                    f"INSERT INTO {self.name} ({column_names}) VALUES ({placeholders})",
                    values
                )
                conn.commit()

    def update_by_id(self, row_id: str, update: dict) -> None:
        """Update a row in the specified table."""
        if not update:
            return

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                set_clause, params = self._build_set_clause(update)
                params.append(row_id)

                cursor.execute(
                    f"UPDATE {self.name} SET {set_clause} WHERE {PK} = %s",
                    params
                )
                if cursor.rowcount == 0:
                    raise NotFoundError(row_id, self.name)
                conn.commit()

    def update_matching(self, query: dict, update: dict) -> None:
        """Update rows matching a query in the specified table."""
        if not update:
            return

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                set_clause, set_params = self._build_set_clause(update)
                where_clause, where_params = self._build_where_clause(query)

                params = set_params + where_params
                sql = f"UPDATE {self.name} SET {set_clause} {where_clause}"

                cursor.execute(sql, params)
                if cursor.rowcount == 0:
                    raise NoChangesAppliedError("update", query, self.name)
                conn.commit()

    def delete_by_id(self, row_id: str) -> None:
        """Delete a row from the specified table."""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"DELETE FROM {self.name} WHERE {PK} = %s",
                    (row_id,)
                )
                if cursor.rowcount == 0:
                    raise NotFoundError(row_id, self.name)
                conn.commit()

    def delete_matching(self, query: dict) -> None:
        """Delete rows matching a query in the specified table."""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                where_clause, params = self._build_where_clause(query)
                cursor.execute(
                    f"DELETE FROM {self.name} {where_clause}",
                    params
                )
                if cursor.rowcount == 0:
                    raise NoChangesAppliedError("delete", query, self.name)
                conn.commit()

    @devops.block_env(devops.PRODUCTION)
    def init_table(self, schema: str) -> None:
        """Initialize the table with the given SQL schema.

        This method is intended for development/testing environments.
        In production, schema management should be handled by migrations.

        Args:
            schema: SQL CREATE TABLE statement defining the table structure.
        """
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(schema)
                conn.commit()


@devops.block_env(devops.PRODUCTION)
def purge_tables() -> None:
    """Purge all tables by dropping and recreating the schema.

    This function is intended for development/testing environments only.
    It drops the entire public schema and recreates it, effectively
    removing all tables and data.

    Raises:
        RuntimeError: If database connection or schema operations fail
    """
    try:
        uri = _get_db_uri()
        conn = psycopg2.connect(uri)
        conn.autocommit = False

        with conn.cursor() as cursor:
            cursor.execute("DROP SCHEMA IF EXISTS public CASCADE;")
            cursor.execute("CREATE SCHEMA public;")

        conn.commit()
        conn.close()

    except Exception as e:
        raise RuntimeError(f"Failed to purge PostgreSQL database: {e}") from e
