"""campus.storage.tables.backend.sqlite

This module provides the SQLite backend for the Tables storage interface.

This is primarily intended for testing and development scenarios where a
lightweight, in-memory database is sufficient. For production use, prefer
the PostgreSQL backend.

Implementation:
Uses SQLite with in-memory databases (:memory:) by default. Tables are
created dynamically based on the first insert operation. All columns
are treated as TEXT for simplicity, with JSON serialization for complex types.

Usage Example:
```python
from campus.storage.tables.backend.sqlite import SQLiteTable

table = SQLiteTable("users")
table.insert_one({PK: "123", "created_at": "2023-01-01", "name": "John"})
user = table.get_by_id("123")
table.update_by_id("123", {"name": "Jane"})
table.delete_by_id("123")
```
"""

import json
import sqlite3
from typing import Any, Dict, List, Optional

from campus.storage.tables.interface import TableInterface, PK

# This constant should match the one in campus.common.schema
PK = "id"


class SQLiteTable(TableInterface):
    """SQLite implementation of the table storage interface."""

    # Class-level connection to ensure all tables share the same in-memory database
    _connection: Optional[sqlite3.Connection] = None

    def __init__(self, name: str):
        """Initialize the SQLite table interface."""
        super().__init__(name)
        self._ensure_connection()
        self._ensure_table()

    @classmethod
    def _ensure_connection(cls):
        """Ensure we have a database connection."""
        if cls._connection is None:
            cls._connection = sqlite3.connect(
                ":memory:", check_same_thread=False)
            cls._connection.row_factory = sqlite3.Row

    def _ensure_table(self):
        """Ensure the table exists."""
        assert self._connection is not None, "Database connection not initialized"
        cursor = self._connection.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.name} (
                id TEXT PRIMARY KEY,
                created_at TEXT,
                data TEXT
            )
        """)
        self._connection.commit()

    def _serialize_row(self, row: Dict[str, Any]) -> tuple:
        """Serialize a row for storage."""
        row_id = row.get(PK)
        created_at = row.get("created_at")

        # Store all other fields as JSON in the data column
        data = {k: v for k, v in row.items() if k not in [PK, "created_at"]}
        data_json = json.dumps(data) if data else "{}"

        return (row_id, created_at, data_json)

    def _deserialize_row(self, sqlite_row) -> Dict[str, Any]:
        """Deserialize a row from storage."""
        if sqlite_row is None:
            return {}

        row = {PK: sqlite_row[PK]}
        if sqlite_row["created_at"]:
            row["created_at"] = sqlite_row["created_at"]

        # Parse the JSON data
        if sqlite_row["data"]:
            data = json.loads(sqlite_row["data"])
            row.update(data)

        return row

    def get_by_id(self, row_id: str) -> Dict[str, Any]:
        """Retrieve a row by its ID."""
        assert self._connection is not None, "Database connection not initialized"
        cursor = self._connection.cursor()
        cursor.execute(f"SELECT * FROM {self.name} WHERE id = ?", (row_id,))
        sqlite_row = cursor.fetchone()
        return self._deserialize_row(sqlite_row)

    def get_matching(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Retrieve rows matching a query."""
        assert self._connection is not None, "Database connection not initialized"
        cursor = self._connection.cursor()

        if not query:
            # Return all rows if no query
            cursor.execute(f"SELECT * FROM {self.name}")
            return [self._deserialize_row(row) for row in cursor.fetchall()]

        # Simple query handling - exact matches only for this implementation
        rows = []
        cursor.execute(f"SELECT * FROM {self.name}")
        for sqlite_row in cursor.fetchall():
            row = self._deserialize_row(sqlite_row)
            if row and self._matches_query(row, query):  # Skip empty rows
                rows.append(row)

        return rows

    def _matches_query(self, row: Dict[str, Any], query: Dict[str, Any]) -> bool:
        """Check if a row matches a query."""
        for key, value in query.items():
            if key not in row or row[key] != value:
                return False
        return True

    def insert_one(self, row: Dict[str, Any]):
        """Insert a row into the table."""
        assert self._connection is not None, "Database connection not initialized"
        row_id, created_at, data_json = self._serialize_row(row)

        cursor = self._connection.cursor()
        cursor.execute(
            f"INSERT INTO {self.name} (id, created_at, data) VALUES (?, ?, ?)",
            (row_id, created_at, data_json)
        )
        self._connection.commit()

    def update_by_id(self, row_id: str, update: Dict[str, Any]):
        """Update a row by its ID."""
        # Get the existing row
        existing_row = self.get_by_id(row_id)
        if not existing_row:  # Empty dict means not found
            return

        # Merge the update
        updated_row = existing_row.copy()
        updated_row.update(update)

        # Store the updated row
        assert self._connection is not None, "Database connection not initialized"
        row_id_new, created_at, data_json = self._serialize_row(updated_row)

        cursor = self._connection.cursor()
        cursor.execute(
            f"UPDATE {self.name} SET created_at = ?, data = ? WHERE id = ?",
            (created_at, data_json, row_id)
        )
        self._connection.commit()

    def update_matching(self, query: Dict[str, Any], update: Dict[str, Any]):
        """Update rows matching a query."""
        matching_rows = self.get_matching(query)
        for row in matching_rows:
            self.update_by_id(row[PK], update)

    def delete_by_id(self, row_id: str):
        """Delete a row by its ID."""
        assert self._connection is not None, "Database connection not initialized"
        cursor = self._connection.cursor()
        cursor.execute(f"DELETE FROM {self.name} WHERE id = ?", (row_id,))
        self._connection.commit()

    def delete_matching(self, query: Dict[str, Any]):
        """Delete rows matching a query."""
        matching_rows = self.get_matching(query)
        for row in matching_rows:
            self.delete_by_id(row[PK])

    def init_table(self, schema: str) -> None:
        """Initialize the table with the given SQL schema.

        This method is intended for development/testing environments.
        For SQLite in-memory databases, tables need to be created with SQL.

        Args:
            schema: SQL CREATE TABLE statement defining the table structure.
        """
        self._ensure_connection()
        assert self._connection is not None, "Database connection not initialized"
        cursor = self._connection.cursor()
        cursor.execute(schema)
        self._connection.commit()

    @classmethod
    def reset_database(cls):
        """Reset the in-memory database. Useful for testing."""
        if cls._connection:
            cls._connection.close()
            cls._connection = None
