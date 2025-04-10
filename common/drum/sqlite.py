# Use a hardcoded db file for testing

import sqlite3
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any, Generator

from common.schema import Message, Response

from .base import PK, Condition, DrumResponse, Record, Update


def dict_factory(cursor, row) -> Record:
    """An sqlite3 row factory that returns a dictionary."""
    d = {
        col[0]: row[idx]
        for idx, col in enumerate(cursor.description)
    }
    return d

def get_conn() -> sqlite3.Connection:
    """Get a prepared connection to the sqlite3 database."""
    conn = sqlite3.connect('test.db')
    conn.execute('PRAGMA foreign_keys = ON')
    conn.row_factory = dict_factory
    return conn


class SqliteDrum:
    """SQLite implementation of the Drum interface."""
    def __init__(self):
        self.transaction = None
        self._responses = None

    @contextmanager
    def use_transaction(self) -> Generator[sqlite3.Connection, None, None]:
        self.begin_transaction()
        assert self.transaction is not None
        try:
            yield self.transaction
        finally:
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

    def transaction_responses(self) -> list[DrumResponse]:
        """Return the results of the transaction."""
        if not self.transaction:
            raise RuntimeError("No transaction in progress")
        assert isinstance(self._responses, list)
        return self._responses.copy()

    def _execute_callback(
            self,
            *args,
            callback: Callable[[sqlite3.Cursor], Any] | None = None,
            commit: bool = True,
            conn: sqlite3.Connection | None = None,
    ) -> DrumResponse:
        """Execute a typical query, using a callback to handle the cursor.

        Args:
            args: The query and parameters to execute.
            callback: A function that takes a cursor and returns a value.
                If None, the cursor is returned.
            commit: Whether to commit the transaction.

            If a transaction is in progress, responses are collected, commit is
            ignored.

        Returns:
            A DrumResponse object with the status, message, and data.
        """
        if (self.transaction and commit):
            raise ValueError(
                "A transaction is in progress, cannot commit\n"
                "Hint: unset commit keyword argument"
            )
        # We allow callback while a transaction is in progress, since it is used
        # to perform SELECT queries and should not affect the transaction.
        conn = self.transaction or get_conn()
        try:
            cursor = conn.execute(*args)
        except sqlite3.DatabaseError as e:
            return DrumResponse('error', Message.FAILED, str(e))
        # Don't catch other kinds of errors
        else:
            if callback:
                result = callback(cursor)
                return DrumResponse('ok', Message.COMPLETED, result)
            if self.transaction:
                assert isinstance(self._responses, list)
                self._responses.append(
                    DrumResponse('ok', Message.COMPLETED, cursor.lastrowid)
                )
            elif commit:
                conn.commit()
                return DrumResponse('ok', Message.COMPLETED, cursor)
        finally:
            if not self.transaction:
                conn.close()
        raise AssertionError("unreachable")
    
    def get_all(self, group: str) -> DrumResponse:
        """Retrieve all records from table"""
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
            f"""SELECT FROM {group} WHERE {PK} = ?""",
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
            
    def get_matching(self, group: str, condition: Condition) -> DrumResponse:
        """Retrieve records from table that match the condition"""
        if not condition:
            raise ValueError(
                "Condition must not be empty\n"
                "Hint: use get_all() to retrieve all records"
                )
        where_clause = " AND ".join(
            f"{key} = ?" for key in condition
        )
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

    def delete_by_id(self, group: str, id: str) -> DrumResponse:
        """Delete a record from table by its id"""
        resp = self._execute_callback(
            f"""DELETE FROM {group} WHERE {PK} = ?;""",
            (id,)
        )
        match resp:
            case Response(status="error", message=Message.FAILED, data=err):
                return DrumResponse("error", Message.FAILED, err)
            case Response(status="ok", data=cursor):
                assert cursor is not None
                if cursor.rowcount == 0:
                    return DrumResponse("ok", Message.NOT_FOUND)
                else:
                    return DrumResponse("ok", Message.DELETED, cursor.lastrowid)
            case _:
                raise ValueError(f"Unexpected case: {resp}")
                
    def delete_matching(self, group: str, condition: Condition) -> DrumResponse:
        """Delete records from table that match the condition"""
        if not condition:
            raise ValueError("Condition must not be empty")
        where_clause = " AND ".join(
            f"{key} = ?" for key in condition
        )
        if condition:
            resp = self._execute_callback(
                f"""DELETE FROM {group} WHERE {where_clause};""",
                tuple(condition.values())
            )
        else:
            resp = self._execute_callback(f"""DELETE FROM {group};""")
        match resp:
            case Response(status="error", message=Message.FAILED, data=err):
                return DrumResponse("error", Message.FAILED, err)
            case Response(status="ok", data=cursor):
                assert cursor is not None
                if cursor.rowcount == 0:
                    return DrumResponse("ok", Message.NOT_FOUND)
                else:
                    return DrumResponse("ok", Message.DELETED, cursor.rowcount)
        raise ValueError(f"Unexpected case: {resp}")

    def insert(self, group: str, record: Record) -> DrumResponse:
        """Insert a new record into the table"""
        assert PK in record, f"Record must have a {PK} field"
        keys = ", ".join(record.keys())
        placeholders = ", ".join("?" * len(record))
        resp = self._execute_callback(
            f"""INSERT INTO {group} ({keys}) VALUES ({placeholders})""",
            tuple(record.values())
        )
        match resp:
            case Response(status="error", message=Message.FAILED, data=err):
                return DrumResponse("error", Message.FAILED, err)
            case Response(status="ok", data=cursor):
                assert cursor is not None
                return DrumResponse("ok", Message.SUCCESS, cursor.lastrowid)
        raise ValueError(f"Unexpected case: {resp}")

    def update_by_id(self, group: str, id: str, updates: Update) -> DrumResponse:
        """Update a record in the table by its id"""
        assert PK not in updates, f"Updates must not include a {PK} field"
        set_clause = ", ".join(
            f"{field} = ?" for field in updates
        )
        resp = self._execute_callback(
            f"""UPDATE {group} SET {set_clause} WHERE {PK} = ?""",
            tuple(updates.values()) + (id,)
        )
        match resp:
            case Response(status="error", message=Message.FAILED, data=err):
                return DrumResponse("error", Message.FAILED, err)
            case Response(status="ok", data=cursor):
                assert cursor is not None
                if cursor.rowcount == 0:
                    return DrumResponse("ok", Message.NOT_FOUND)
                else:
                    return DrumResponse("ok", Message.UPDATED, cursor.lastrowid)
            case _:
                raise ValueError(f"Unexpected case: {resp}")
            
    def update_matching(
            self,
            group: str,
            updates: Update,
            condition: Condition,
    ) -> DrumResponse:
        """Update records from table that match the condition"""
        if not condition:
            raise ValueError("Condition must not be empty")
        if PK in updates:
            raise ValueError(
                f"Updates must not include a {PK} field\n"
                "Hint: use set() to update a record by id"
            )
        set_clause = ", ".join(
            f"{key} = ?" for key in updates
        )
        where_clause = " AND ".join(
            f"{key} = ?" for key in condition
        )
        resp = self._execute_callback(
            f"""UPDATE {group} SET {set_clause} WHERE {where_clause};""",
            tuple(updates.values()) + tuple(condition.values())
        )
        match resp:
            case Response(status="error", message=Message.FAILED, data=err):
                return DrumResponse("error", Message.FAILED, err)
            case Response(status="ok", data=cursor):
                assert cursor is not None
                if cursor.rowcount == 0:
                    return DrumResponse("ok", Message.NOT_FOUND)
                else:
                    return DrumResponse("ok", Message.UPDATED, cursor.rowcount)
        raise ValueError(f"Unexpected case: {resp}")

    def set(self, group: str, record: Record) -> DrumResponse:
        """Update an existing record, or insert a new one if it doesn't exist"""
        assert PK in record, f"Record must have a {PK} field"
        # Check if the record exists
        resp = self.get_by_id(group, record[PK])
        match resp:
            case Response(status="error", message=Message.FAILED, data=err):
                return DrumResponse("error", Message.FAILED, err)
            case Response(status="ok", message=Message.NOT_FOUND):
                # Record does not exist, perform an insert
                return self.insert(group, record)
            case Response(status="ok", message=Message.FOUND, data=existing_record):
                assert isinstance(existing_record, dict)  # appease mypy gods
                # Record exists, perform an update
                updates = {
                    key: value
                    for key, value in record.items()
                    if existing_record.get(key) != value
                }
                return self.update_by_id(group, record[PK], updates)
        raise ValueError(f"Unexpected case: {resp}")
