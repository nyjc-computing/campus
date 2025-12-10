"""campus.storage.tables.backend.postgres

This module provides the PostgreSQL backend for the Tables storage interface.

Vault Integration:
The database URI is retrieved from the vault secret 'POSTGRESDB_URI' in the
'storage' vault. The storage system depends on the vault service for database
credentials.

Implementation:
Uses direct column mapping where record keys correspond to table column names.
Tables are assumed to exist with correct schema. Record validation is handled
before storage and is not the responsibility of this module.

Usage Example:
```python
from campus.storage.tables.backend.postgres import PostgreSQLTable

table = PostgreSQLTable("users")
table.insert_one({PK: "123", "created_at": "2023-01-01T00:00:00Z", "name": "John"})
user = table.get_by_id("123")
table.update_by_id("123", {"name": "Jane"})
table.delete_by_id("123")
```
"""

import dataclasses

import psycopg2
from psycopg2.extras import RealDictCursor

from campus.common import devops, env
from campus.common.utils import datacls
from campus.model import Model, constraints
from campus.storage import errors

from ..interface import PK, TableInterface

_TYPEMAP = {
    str: "TEXT",
    int: "INTEGER",
    float: "REAL",
    bool: "BOOLEAN",
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

def _get_db_uri() -> str:
    """Get the database URI from the vault using the client API."""
    import logging
    logger = logging.getLogger(__name__)
    logger.info("[DB] Fetching POSTGRESDB_URI...")
    db_uri = env.getsecret("POSTGRESDB_URI", env.DEPLOY)
    logger.info("[DB] Got POSTGRESDB_URI")
    return db_uri


class PostgreSQLTable(TableInterface):
    """PostgreSQL backend for the Tables storage interface.

    Uses direct column mapping: record keys correspond to table column names.

    Example:
        table = PostgreSQLTable("users")
        table.insert_one(
            {PK: "123", "created_at": "2023-01-01T00:00:00Z", "name": "John"}
        )
        user = table.get_by_id("123")
    """

    def _get_connection(self):
        """Get a connection to the PostgreSQL database.

        Retrieves the database URI from vault and establishes connection.

        Raises:
            RuntimeError: If vault secret retrieval fails
            psycopg2.Error: If database connection fails
        """
        import logging
        logger = logging.getLogger(__name__)
        logger.info("[DB] Getting database connection...")
        db_uri = _get_db_uri()
        logger.info("[DB] Connecting to PostgreSQL...")
        conn = psycopg2.connect(db_uri)
        logger.info("[DB] Connected successfully")
        return conn

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
                if not row:
                    raise errors.NotFoundError(row_id, self.name)
                return dict(row)

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

                try:
                    cursor.execute(
                        f"INSERT INTO {self.name} ({column_names}) VALUES ({placeholders})",
                        values
                    )
                except psycopg2.IntegrityError as e:
                    conn.rollback()
                    raise errors.ConflictError(
                        message="Conflict occurred during insert",
                        group_name=self.name,
                        details={"row": row, "error": str(e)}
                    ) from e
                except psycopg2.Error as e:
                    conn.rollback()
                    raise
                else:
                    conn.commit()

    def update_by_id(self, row_id: str, update: dict) -> None:
        """Update a row in the specified table."""
        if not update:
            return

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                set_clause, params = self._build_set_clause(update)
                params.append(row_id)

                try:
                    cursor.execute(
                        f"UPDATE {self.name} SET {set_clause} WHERE {PK} = %s",
                        params
                    )
                except psycopg2.Error as e:
                    raise
                else:
                    if cursor.rowcount == 0:
                        raise errors.NotFoundError(
                            row_id, self.name
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

                try:
                    cursor.execute(sql, params)
                except psycopg2.Error as e:
                    raise
                else:
                    if cursor.rowcount == 0:
                        raise errors.NoChangesAppliedError(
                            "update", query, self.name)
                    conn.commit()

    def delete_by_id(self, row_id: str) -> None:
        """Delete a row from the specified table."""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                try:
                    cursor.execute(
                        f"DELETE FROM {self.name} WHERE {PK} = %s",
                        (row_id,)
                    )
                except psycopg2.Error as e:
                    raise
                else:
                    if cursor.rowcount == 0:
                        raise errors.NotFoundError(row_id, self.name)
                    conn.commit()

    def delete_matching(self, query: dict) -> None:
        """Delete rows matching a query in the specified table."""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                where_clause, params = self._build_where_clause(query)
                try:
                    cursor.execute(
                        f"DELETE FROM {self.name} {where_clause}",
                        params
                    )
                except psycopg2.Error as e:
                    raise
                else:
                    if cursor.rowcount == 0:
                        raise errors.NoChangesAppliedError(
                            "delete", query, self.name
                        )
                    conn.commit()
    
    @devops.block_env(devops.PRODUCTION)
    def init_from_model(self, name: str, model: type[Model]) -> None:
        """Initialize the table from a Campus model definition."""
        create_table_sql = _model_to_sql_schema(name, model)
        # Ensure connection is properly closed after operation
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(create_table_sql)
                conn.commit()

    @devops.block_env(devops.PRODUCTION)
    def init_from_schema(self, schema: str) -> None:
        """Initialize the table with the given SQL schema.

        This method is intended for development/testing environments.
        In production, schema management should be handled by migrations.

        Args:
            schema: SQL CREATE TABLE statement defining the table structure.
        """
        # Ensure connection is properly closed after operation
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
