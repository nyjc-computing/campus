"""storage.tables.backend.postgres

This module provides the PostgreSQL backend for the Tables storage interface.

Environment Variables:
- DB_URI: PostgreSQL connection string (required)

Implementation:
Uses direct column mapping where record keys correspond to table column names.
Tables are assumed to exist with correct schema. Record validation is handled
before storage and is not the responsibility of this module.

Usage Example:
```python
from storage.tables.backend.postgres import PostgreSQLTable

table = PostgreSQLTable("users")
table.insert_one({"id": "123", "created_at": "2023-01-01", "name": "John"})
user = table.get_by_id("123")
table.update_by_id("123", {"name": "Jane"})
table.delete_by_id("123")
```
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.errors import UniqueViolation

from storage.tables.interface import TableInterface, PK

DB_URI = os.environ["DB_URI"]


class PostgreSQLTable(TableInterface):
    """PostgreSQL backend for the Tables storage interface.
    
    Uses direct column mapping: record keys correspond to table column names.
    
    Example:
        table = PostgreSQLTable("users")
        table.insert_one({"id": "123", "created_at": "2023-01-01", "name": "John"})
        user = table.get_by_id("123")
    """

    def __init__(self, name: str):
        """Initialize the PostgreSQL table with a name."""
        super().__init__(name)

    def _get_connection(self):
        """Get a connection to the PostgreSQL database."""
        return psycopg2.connect(DB_URI)

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
                    f"SELECT * FROM {self.name} WHERE id = %s",
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
                column_names, placeholders, values = self._build_columns_and_values(row)
                
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
                    f"UPDATE {self.name} SET {set_clause} WHERE id = %s",
                    params
                )
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
                conn.commit()

    def delete_by_id(self, row_id: str) -> None:
        """Delete a row from the specified table."""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"DELETE FROM {self.name} WHERE id = %s",
                    (row_id,)
                )
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
                conn.commit()
