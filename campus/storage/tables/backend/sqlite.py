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
table.insert_one({PK: "123", "created_at": "2023-01-01T00:00:00Z", "name": "John"})
user = table.get_by_id("123")
table.update_by_id("123", {"name": "Jane"})
table.delete_by_id("123")
```
"""

import dataclasses
import json
import sqlite3
from typing import Any, Dict, List, Optional

from campus.common import devops
from campus.common.utils import datacls
from campus.model import Model, constraints
from ..interface import TableInterface, PK


_TYPEMAP = {
    str: "TEXT",
    int: "INTEGER",
    float: "REAL",
    bool: "INTEGER",
}


def _field_to_sql_schema(field: dataclasses.Field) -> str:
    """Convert a dataclass field to a SQL column definition."""
    field_name = field.name
    field_type = field.type
    sql_type = _TYPEMAP.get(field_type, "TEXT")
    sql_field_constraints = []

    if field_name == "__constraints__":
        match field.default:
            case constraints.Unique():
                unique_fields = field.default.fields
                unique_constraint = ", ".join(unique_fields)
                return f"UNIQUE ({unique_constraint})"
            case _:
                raise ValueError(
                    f"Unsupported constraint type: {field.default}"
                )
    elif field_name == PK:
        sql_field_constraints.append("PRIMARY KEY")
    if constraints.UNIQUE in field.metadata.get("constraints", []):
        sql_field_constraints.append("UNIQUE")
    if not datacls.is_optional(field):
        sql_field_constraints.append("NOT NULL")

    constraints_sql = " ".join(sql_field_constraints)
    return f"\"{field_name}\" {sql_type} {constraints_sql}"


def _model_to_sql_schema(name: str, model: type[Model]) -> str:
    """Convert a dataclass model to SQL schema."""
    columns = []
    constraints_ = []
    for field in model.fields().values():
        if not field.metadata.get("storage", True):
            continue  # skip non-storage fields
        if field.name == "__constraints__":
            constraints_.append(field)
            continue
        columns.append(_field_to_sql_schema(field))
    for field in constraints_:
        columns.append(_field_to_sql_schema(field))
    columns_sql = ", ".join(columns)
    return f"CREATE TABLE IF NOT EXISTS \"{name}\" ({columns_sql});"


class SQLiteTable(TableInterface):
    """SQLite implementation of the table storage interface.

    This implementation uses the full schema defined by the model, storing each
    field as a separate column in the SQLite table. This allows SQLite to enforce
    constraints properly during testing.
    """

    # Class-level connection to ensure all tables share the same in-memory database
    _connection: Optional[sqlite3.Connection] = None

    def __init__(self, name: str):
        """Initialize the SQLite table interface."""
        super().__init__(name)
        self._ensure_connection()

    @classmethod
    def _ensure_connection(cls):
        """Ensure we have a database connection."""
        if cls._connection is None:
            cls._connection = sqlite3.connect(
                ":memory:", check_same_thread=False)
            cls._connection.row_factory = sqlite3.Row

    def _get_table_columns(self) -> List[str]:
        """Get the list of column names for this table.

        Returns an empty list if the table doesn't exist yet.
        """
        assert self._connection is not None, "Database connection not initialized"
        cursor = self._connection.cursor()
        try:
            cursor.execute(f"PRAGMA table_info({self.name})")
            # row[1] is the column name
            columns = [row[1] for row in cursor.fetchall()]
            return columns
        except sqlite3.OperationalError:
            # Table doesn't exist yet
            return []

    def _serialize_row(self, row: Dict[str, Any]) -> tuple:
        """Serialize a row for storage using actual table columns.

        This method gets the actual columns from the table and creates a tuple
        with values in the correct order, using None for missing values.
        """
        columns = self._get_table_columns()
        values = []
        for col in columns:
            value = row.get(col)
            # Convert complex types to JSON strings for storage
            if value is not None and not isinstance(value, (str, int, float, bool, type(None))):
                value = json.dumps(value)
            values.append(value)
        return tuple(values)

    def _deserialize_row(self, sqlite_row) -> Dict[str, Any]:
        """Deserialize a row from storage using actual table columns."""
        if sqlite_row is None:
            return {}

        row = {}
        for key in sqlite_row.keys():
            value = sqlite_row[key]
            # Try to parse JSON strings back to objects
            if isinstance(value, str) and value and (value.startswith('{') or value.startswith('[')):
                try:
                    value = json.loads(value)
                except (json.JSONDecodeError, ValueError):
                    pass  # Keep as string if not valid JSON
            row[key] = value

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
        """Insert a row into the table using actual table columns."""
        assert self._connection is not None, "Database connection not initialized"

        columns = self._get_table_columns()
        if not columns:
            raise RuntimeError(
                f"Table '{self.name}' does not exist. Call init_from_model() or init_from_schema() first.")

        placeholders = ", ".join(["?" for _ in columns])
        columns_sql = ", ".join([f'"{col}"' for col in columns])
        values = []

        for col in columns:
            value = row.get(col)
            # Convert complex types to JSON strings for storage
            if value is not None and not isinstance(value, (str, int, float, bool, type(None))):
                value = json.dumps(value)
            values.append(value)

        cursor = self._connection.cursor()
        cursor.execute(
            f"INSERT INTO {self.name} ({columns_sql}) VALUES ({placeholders})",
            tuple(values)
        )
        self._connection.commit()

    def update_by_id(self, row_id: str, update: Dict[str, Any]):
        """Update a row by its ID using actual table columns."""
        # Get the existing row
        existing_row = self.get_by_id(row_id)
        if not existing_row:  # Empty dict means not found
            return

        # Merge the update
        updated_row = existing_row.copy()
        updated_row.update(update)

        # Build UPDATE statement for only the columns being updated
        assert self._connection is not None, "Database connection not initialized"
        columns = self._get_table_columns()

        # Filter to only columns that exist in the table and are in the updated row
        set_clauses = []
        values = []
        for col in columns:
            if col != PK and col in updated_row:  # Don't update the primary key
                set_clauses.append(f'"{col}" = ?')
                value = updated_row[col]
                # Convert complex types to JSON strings for storage
                if value is not None and not isinstance(value, (str, int, float, bool, type(None))):
                    value = json.dumps(value)
                values.append(value)

        if not set_clauses:
            return  # Nothing to update

        values.append(row_id)  # For the WHERE clause
        set_sql = ", ".join(set_clauses)

        cursor = self._connection.cursor()
        cursor.execute(
            f"UPDATE {self.name} SET {set_sql} WHERE id = ?",
            tuple(values)
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

    @devops.block_env(devops.PRODUCTION)
    def init_from_model(self, name: str, model: type[Model]) -> None:
        """Initialize the table from a Campus model definition."""
        self._ensure_connection()
        assert self._connection is not None, "Database connection not initialized"
        create_table_sql = _model_to_sql_schema(name, model)
        cursor = self._connection.cursor()
        try:
            cursor.execute(create_table_sql)
        except Exception as e:
            raise
        else:
            self._connection.commit()

    @devops.block_env(devops.PRODUCTION)
    def init_from_schema(self, schema: str) -> None:
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
