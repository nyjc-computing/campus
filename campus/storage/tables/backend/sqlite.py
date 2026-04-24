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
from campus.model import InternalModel, Model, constraints
from campus.storage import errors as storage_errors
from campus.storage.query import gt, gte, is_operator, lt, lte
from ..interface import TableInterface, PK


# Valid field constraint names
_VALID_CONSTRAINTS = (constraints.UNIQUE,)

_TYPEMAP = {
    str: "TEXT",
    int: "INTEGER",
    float: "REAL",
    bool: "INTEGER",
}


def _validate_field_metadata(field: dataclasses.Field) -> None:
    """Validate field metadata for SQL schema generation.

    Args:
        field: The dataclass field to validate

    Raises:
        TypeError: If metadata values have incorrect types
        ValueError: If metadata values contain invalid entries
    """
    # Validate 'storage' metadata (must be bool)
    if "storage" in field.metadata:
        storage = field.metadata["storage"]
        if not isinstance(storage, bool):
            raise TypeError(
                f"Field '{field.name}': metadata 'storage' must be bool, "
                f"got {type(storage).__name__}"
            )

    # Validate 'constraints' metadata (must be sequence of strings)
    if "constraints" in field.metadata:
        constraints_meta = field.metadata["constraints"]
        if not isinstance(constraints_meta, (list, tuple)):
            raise TypeError(
                f"Field '{field.name}': metadata 'constraints' must be "
                f"list or tuple, got {type(constraints_meta).__name__}"
            )
        for i, c in enumerate(constraints_meta):
            if not isinstance(c, str):
                raise TypeError(
                    f"Field '{field.name}': constraint at index {i} must be str, "
                    f"got {type(c).__name__}"
                )
            if c not in _VALID_CONSTRAINTS:
                raise ValueError(
                    f"Field '{field.name}': invalid constraint '{c}'. "
                    f"Valid constraints: {', '.join(repr(c) for c in _VALID_CONSTRAINTS)}"
                )


def _get_base_type(field_type):
    """Get the base Python type for a field type.

    Returns one of: bool, int, float, str (or None if not a recognized type).
    Handles both built-in types and schema types (which are subclasses).
    """
    # If it's already a base type, return it directly
    if field_type in (bool, int, float, str):
        return field_type

    try:
        # Check in order: bool, int, float, str (bool is subclass of int)
        if issubclass(field_type, bool):
            return bool
        if issubclass(field_type, int):
            return int
        if issubclass(field_type, float):
            return float
        if issubclass(field_type, str):
            return str
    except TypeError:
        # issubclass() raises TypeError if field_type is not a class
        pass
    return None


def _field_to_sql_schema(field: dataclasses.Field) -> str:
    """Convert a dataclass field to a SQL column definition."""
    _validate_field_metadata(field)
    field_name = field.name
    field_type = field.type
    base_type = _get_base_type(field_type) or str
    sql_type = _TYPEMAP[base_type]
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


def _model_to_sql_schema(name: str, model: type[InternalModel | Model]) -> str:
    """Convert a dataclass model to SQL schema."""
    columns = []
    constraints_ = []
    for field in model.fields().values():
        _validate_field_metadata(field)
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

    @classmethod
    def get_connection(cls) -> sqlite3.Connection:
        """Get the database connection, establishing it if needed."""
        if cls._connection is None:
            cls._connection = sqlite3.connect(
                ":memory:", check_same_thread=False)
            cls._connection.row_factory = sqlite3.Row
        return cls._connection

    def _get_table_columns(self) -> List[str]:
        """Get the list of column names for this table.

        Returns an empty list if the table doesn't exist yet.
        """
        cursor = self.get_connection().cursor()
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

    def _deserialize_row(self, sqlite_row) -> Dict[str, Any] | None:
        """Deserialize a row from storage using actual table columns.

        TODO: Type conversion issue - SQLite returns all values as strings in row_factory mode.
        Need to use PRAGMA table_info to get column types and cast values appropriately.
        For example, INTEGER columns should return int, REAL should return float, etc.
        Currently this causes issues with bitwise operations on integer fields like 'access'.

        Returns:
            The deserialized row as a dict, or None if sqlite_row is None
        """
        if sqlite_row is None:
            return None

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
        """Retrieve a row by its ID.

        Raises:
            storage_errors.NotFoundError: If no row exists with the given ID
        """
        cursor = self.get_connection().cursor()
        cursor.execute(f"SELECT * FROM {self.name} WHERE id = ?", (row_id,))
        sqlite_row = cursor.fetchone()
        row = self._deserialize_row(sqlite_row)
        if row is None:
            raise storage_errors.NotFoundError(row_id, self.name)
        return row

    @staticmethod
    def _build_where_clause(query: Dict[str, Any]) -> tuple[str, list]:
        """Build WHERE clause from query dictionary.

        Handles exact matches and comparison operators (gt, gte, lt, lte, between).
        Uses ? placeholders for SQLite parameter binding.
        """
        if not query:
            return "", []

        conditions = []
        params = []

        from campus.storage.query import between as between_op
        for key, value in query.items():
            if is_operator(value):
                # Handle comparison operators
                if isinstance(value, gt):
                    conditions.append(f'"{key}" > ?')
                    params.append(value.value)
                elif isinstance(value, gte):
                    conditions.append(f'"{key}" >= ?')
                    params.append(value.value)
                elif isinstance(value, lt):
                    conditions.append(f'"{key}" < ?')
                    params.append(value.value)
                elif isinstance(value, lte):
                    conditions.append(f'"{key}" <= ?')
                    params.append(value.value)
                elif isinstance(value, between_op):
                    # BETWEEN operator: key >= min AND key <= max
                    min_val, max_val = value.value
                    conditions.append(f'("{key}" >= ? AND "{key}" <= ?)')
                    params.extend([min_val, max_val])
                else:
                    # Unknown operator, fall back to exact match
                    conditions.append(f'"{key}" = ?')
                    params.append(value.value)
            else:
                # Exact match
                conditions.append(f'"{key}" = ?')
                params.append(value)

        return f"WHERE {' AND '.join(conditions)}", params

    def get_matching(
        self,
        query: Dict[str, Any],
        *,
        order_by: str | None = None,
        ascending: bool = True,
        limit: int | None = None,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Retrieve rows matching a query.

        Supports exact matches, comparison operators (gt, gte, lt, lte),
        sorting, and pagination.
        """
        cursor = self.get_connection().cursor()
        where_clause, params = self._build_where_clause(query)
        sql = f"SELECT * FROM {self.name} {where_clause}"

        # Add ORDER BY clause if specified
        if order_by is not None:
            direction = "ASC" if ascending else "DESC"
            sql += f' ORDER BY "{order_by}" {direction}'

        # Add LIMIT clause (SQLite requires LIMIT when using OFFSET)
        # If offset is specified but limit is not, use a very large limit
        if limit is None and offset > 0:
            limit = -1  # SQLite uses -1 to mean "no limit"
        if limit is not None:
            sql += f" LIMIT {limit}"

        # Add OFFSET clause if specified
        if offset > 0:
            sql += f" OFFSET {offset}"

        cursor.execute(sql, params)
        return [row for row in (self._deserialize_row(row) for row in cursor.fetchall()) if row is not None]

    def insert_one(self, row: Dict[str, Any]):
        """Insert a row into the table using actual table columns."""
        conn = self.get_connection()
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

        cursor = conn.cursor()
        cursor.execute(
            f"INSERT INTO {self.name} ({columns_sql}) VALUES ({placeholders})",
            tuple(values)
        )
        conn.commit()

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
        conn = self.get_connection()
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

        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE {self.name} SET {set_sql} WHERE id = ?",
            tuple(values)
        )
        conn.commit()

    def update_matching(self, query: Dict[str, Any], update: Dict[str, Any]):
        """Update rows matching a query."""
        matching_rows = self.get_matching(query)
        for row in matching_rows:
            self.update_by_id(row[PK], update)

    def delete_by_id(self, row_id: str):
        """Delete a row by its ID."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM {self.name} WHERE id = ?", (row_id,))
        conn.commit()

    def delete_matching(self, query: Dict[str, Any]):
        """Delete rows matching a query."""
        matching_rows = self.get_matching(query)
        for row in matching_rows:
            self.delete_by_id(row[PK])

    @devops.block_env(devops.PRODUCTION)
    def init_from_model(self, name: str, model: type[InternalModel | Model]) -> None:
        """Initialize the table from a Campus model definition."""
        conn = self.get_connection()
        create_table_sql = _model_to_sql_schema(name, model)
        cursor = conn.cursor()
        try:
            cursor.execute(create_table_sql)
        except Exception as e:
            raise
        else:
            conn.commit()

    @devops.block_env(devops.PRODUCTION)
    def init_from_schema(self, schema: str) -> None:
        """Initialize the table with the given SQL schema.

        This method is intended for development/testing environments.
        For SQLite in-memory databases, tables need to be created with SQL.

        Args:
            schema: SQL CREATE TABLE statement defining the table structure.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(schema)
        conn.commit()

    @classmethod
    def reset_database(cls):
        """Reset the in-memory database. Useful for testing."""
        if cls._connection:
            cls._connection.close()
            cls._connection = None

    @classmethod
    def clear_database(cls):
        """Clear all data from all tables while preserving table structure.

        This is faster than reset_database() for per-test cleanup since it
        doesn't require recreating tables. Useful for test isolation.
        """
        if cls._connection is None:
            return  # No database to clear

        cursor = cls._connection.cursor()
        # Get all table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        # Delete all rows from each table
        for table in tables:
            cursor.execute(f'DELETE FROM "{table}"')

        cls._connection.commit()
