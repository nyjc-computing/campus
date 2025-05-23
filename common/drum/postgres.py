"""common/drum/postgres.py

PostgreSQL implementation of the Drum interface.
"""

import os
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any, Literal, TypedDict

import psycopg2
from psycopg2.extras import RealDictCursor

from common.schema import Message, Response

from .base import PK, Condition, DrumInterface, DrumResponse, Record, Update


def purge() -> None:
    """Purge the database by dropping all tables."""
    conn = get_conn()
    with conn.cursor() as cursor:
        cursor.execute("DROP SCHEMA public CASCADE;")
        cursor.execute("CREATE SCHEMA public;")
    conn.commit()
    conn.close()

def get_conn() -> psycopg2.extensions.connection:
    """Get a prepared connection to the PostgreSQL database."""
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.autocommit = False
    return conn

def get_drum() -> 'PostgresDrum':
    """Get a prepared Drum instance."""
    return PostgresDrum()


class CursorResult(TypedDict):
    """dict representing common cursor attributes."""
    lastrowid: int | None
    rowcount: int
    result: list[Record] | Record | None


class PostgresDrum(DrumInterface):
    """PostgreSQL implementation of the Drum interface."""
    def __init__(self):
        self.transaction = None
        self._responses = None

    @contextmanager
    def use_transaction(self) -> Generator[psycopg2.extensions.connection, None, None]:
        """Context manager to use a transaction.

        This will automatically commit or rollback the transaction
        depending on the status of the responses.
        """
        self.begin_transaction()
        assert self.transaction is not None, "Transaction not started"
        try:
            yield self.transaction
        finally:
            if self.transaction_responses(status="error"):
                self.rollback_transaction()
            else:
                self.commit_transaction()
            self.close_transaction()

    def begin_transaction(self) -> None:
        """Begin a transaction and return the connection."""
        if self.transaction:
            raise RuntimeError("Transaction already in progress")
        self.transaction = get_conn()
        self._responses = []

    def commit_transaction(self) -> None:
        """Commit the transaction."""
        if not self.transaction:
            raise RuntimeError("No transaction in progress")
        self.transaction.commit()

    def rollback_transaction(self) -> None:
        """Rollback the transaction."""
        if not self.transaction:
            raise RuntimeError("No transaction in progress")
        self.transaction.rollback()

    def close_transaction(self) -> None:
        """Close the transaction and release the connection."""
        if not self.transaction:
            raise RuntimeError("No transaction in progress")
        self.transaction.close()
        self.transaction = None
        self._responses = None

    def transaction_responses(
            self,
            status: Literal["ok", "error"] | None = None
    ) -> list[DrumResponse]:
        """Return the results of the transaction."""
        if not self.transaction:
            raise RuntimeError("No transaction in progress")
        assert isinstance(self._responses, list)
        if status:
            return [
                resp for resp in self._responses if resp.status == status
            ]
        else:
            return self._responses.copy()

    def _execute_callback(
            self,
            *args,
            callback: Callable[[psycopg2.extensions.cursor], Any] | None = None,
    ) -> DrumResponse:
        """Execute a typical query, using a callback to handle the cursor.

        Args:
            args: The query and parameters to execute.
            callback: A function that takes a cursor and returns a value.
                If None, the cursor is returned.

            If a transaction is in progress, responses are collected, and
            commit is not automatically called. Otherwise, commit is
            automatically called after the operation.

        Returns:
            A DrumResponse object with the status, message, and data.
        """
        conn = self.transaction or get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            try:
                cursor.execute(*args)
            except (psycopg2.DatabaseError, Exception) as e:
                resp = DrumResponse('error', Message.FAILED, str(e))
                if self.transaction:
                    assert isinstance(self._responses, list)
                    self._responses.append(resp)
                return resp
            else:
                result = CursorResult(
                    lastrowid=cursor.lastrowid,
                    rowcount=cursor.rowcount,
                    result=callback(cursor) if callback else None
                )
                resp = DrumResponse('ok', Message.COMPLETED, result)
                if self.transaction:
                    assert isinstance(self._responses, list)
                    self._responses.append(resp)
                else:
                    # Close the cursor otherwise SQL statements are still in progress
                    cursor.close()
                    conn.commit()
                return resp
            finally:
                if not self.transaction:
                    conn.close()

    def get_all(self, group: str, **filter: Any) -> DrumResponse:
        """Retrieve all records from table"""
        if filter:
            where_clause = " AND ".join(f"{key} = %s" for key in filter)
            resp = self._execute_callback(
                f"""SELECT * FROM {group} WHERE {where_clause}""",
                tuple(filter.values()),
                callback=lambda cursor: cursor.fetchall()
            )
        else:
            resp = self._execute_callback(
                f"""SELECT * FROM {group}""",
                callback=lambda cursor: cursor.fetchall()
            )
        match resp:
            case Response(status="error", message=Message.FAILED, data=err):
                return DrumResponse("error", Message.FAILED, err)
            case Response(status="ok", data=records):
                if records:
                    return DrumResponse("ok", Message.FOUND, records)
                else:
                    return DrumResponse("ok", Message.EMPTY, records)
        raise ValueError(f"Unexpected case: {resp}")

    def get_by_id(self, group: str, id: str) -> DrumResponse:
        """Retrieve a record from table by its id"""
        resp = self._execute_callback(
            f"""SELECT * FROM {group} WHERE {PK} = %s""",
            (id,),
            callback=lambda cursor: cursor.fetchone()
        )
        match resp:
            case Response(status="error", message=Message.FAILED, data=err):
                return DrumResponse("error", Message.FAILED, err)
            case Response(status="ok", data=None):
                return DrumResponse("error", Message.NOT_FOUND)
            case Response(status="ok", data=record):
                return DrumResponse("ok", Message.FOUND, record)
        raise ValueError(f"Unexpected case: {resp}")

    def insert(self, group: str, record: Record) -> DrumResponse:
        """Insert a new record into the table"""
        keys = ", ".join(record.keys())
        placeholders = ", ".join("%s" for _ in record)
        resp = self._execute_callback(
            (
                f"INSERT INTO {group} ({keys}) VALUES ({placeholders})"
                " RETURNING *"
            ),
            tuple(record.values()),
            callback=lambda cursor: cursor.fetchone()
        )
        match resp:
            case Response(status="error", message=Message.FAILED, data=err):
                return DrumResponse("error", Message.FAILED, err)
            case Response(status="ok", data=result):
                # No need to check for rowcount, which is 0
                return DrumResponse("ok", Message.SUCCESS, result["result"])
        raise ValueError(f"Unexpected case: {resp}")

    def delete_by_id(self, group: str, id: str) -> DrumResponse:
        """Delete a record from table by its id"""
        resp = self._execute_callback(
            f"""DELETE FROM {group} WHERE {PK} = %s""",
            (id,)
        )
        match resp:
            case Response(status="error", message=Message.FAILED, data=err):
                return DrumResponse("error", Message.FAILED, err)
            case Response(status="ok", data=result):
                if result["rowcount"] == 0:
                    return DrumResponse("ok", Message.NOT_FOUND)
                else:
                    return DrumResponse("ok", Message.DELETED, result["rowcount"])
        raise ValueError(f"Unexpected case: {resp}")

    def update_by_id(self, group: str, id: str, updates: Update) -> DrumResponse:
        """Update a record in the table by its id"""
        assert PK not in updates, f"Updates must not include a {PK} field"
        set_clause = ", ".join(f"{field} = %s" for field in updates)
        resp = self._execute_callback(
            f"""UPDATE {group} SET {set_clause} WHERE {PK} = %s""",
            tuple(updates.values()) + (id,)
        )
        match resp:
            case Response(status="error", message=Message.FAILED, data=err):
                return DrumResponse("error", Message.FAILED, err)
            case Response(status="ok", data=result):
                if result["rowcount"] == 0:
                    return DrumResponse("ok", Message.NOT_FOUND)
                else:
                    assert result["rowcount"] == 1
                    return DrumResponse("ok", Message.UPDATED)
        raise ValueError(f"Unexpected case: {resp}")

    def set(self, group: str, record: Record) -> DrumResponse:
        """Update an existing record, or insert a new one if it doesn't exist"""
        assert PK in record, f"Record must have a {PK} field"
        record_id = record[PK]
        assert isinstance(record_id, str), f"{PK} must be a string"
        resp = self.get_by_id(group, record_id)
        match resp:
            case Response(status="error", message=Message.FAILED, data=err):
                return DrumResponse("error", Message.FAILED, err)
            case Response(status="ok", message=Message.NOT_FOUND):
                return self.insert(group, record)
            case Response(status="ok", message=Message.FOUND, data=result):
                existing_record = result["result"]
                assert isinstance(existing_record, dict)
                updates = {
                    key: value
                    for key, value in record.items()
                    if existing_record.get(key) != value
                }
                return self.update_by_id(group, record_id, updates)
        raise ValueError(f"Unexpected case: {resp}")

    def get_matching(self, group: str, condition: Condition) -> DrumResponse:
        """Retrieve records from table that match the condition"""
        if not condition:
            raise ValueError("Condition must not be empty")
        where_clause = " AND ".join(f"{key} = %s" for key in condition)
        resp = self._execute_callback(
            f"""SELECT * FROM {group} WHERE {where_clause}""",
            tuple(condition.values()),
            callback=lambda cursor: cursor.fetchall()
        )
        match resp:
            case Response(status="error", message=Message.FAILED, data=err):
                return DrumResponse("error", Message.FAILED, err)
            case Response(status="ok", data=records):
                if records:
                    return DrumResponse("ok", Message.FOUND, records)
                else:
                    return DrumResponse("ok", Message.EMPTY, records)
        raise ValueError(f"Unexpected case: {resp}")

    def delete_matching(self, group: str, condition: Condition) -> DrumResponse:
        """Delete records from table that match the condition"""
        if not condition:
            raise ValueError("Condition must not be empty")
        where_clause = " AND ".join(f"{key} = %s" for key in condition)
        resp = self._execute_callback(
            f"""DELETE FROM {group} WHERE {where_clause}""",
            tuple(condition.values())
        )
        match resp:
            case Response(status="error", message=Message.FAILED, data=err):
                return DrumResponse("error", Message.FAILED, err)
            case Response(status="ok", data=result):
                if result["rowcount"] == 0:
                    return DrumResponse("ok", Message.NOT_FOUND)
                else:
                    return DrumResponse("ok", Message.DELETED, result["rowcount"])
        raise ValueError(f"Unexpected case: {resp}")

    def update_matching(self, group: str, updates: Update, condition: Condition) -> DrumResponse:
        """Update records from table that match the condition"""
        if not condition:
            raise ValueError("Condition must not be empty")
        if PK in updates:
            raise ValueError(f"Updates must not include a {PK} field")
        set_clause = ", ".join(f"{key} = %s" for key in updates)
        where_clause = " AND ".join(f"{key} = %s" for key in condition)
        resp = self._execute_callback(
            f"""UPDATE {group} SET {set_clause} WHERE {where_clause}""",
            tuple(updates.values()) + tuple(condition.values())
        )
        match resp:
            case Response(status="error", message=Message.FAILED, data=err):
                return DrumResponse("error", Message.FAILED, err)
            case Response(status="ok", data=result):
                if result["rowcount"] == 0:
                    return DrumResponse("ok", Message.NOT_FOUND)
                else:
                    return DrumResponse("ok", Message.UPDATED, result["rowcount"])
        raise ValueError(f"Unexpected case: {resp}")
