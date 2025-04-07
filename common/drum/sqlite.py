# Use a hardcoded db file for testing

import sqlite3
from collections.abc import Callable
from typing import Any, Literal, NamedTuple

Record = dict[str, Any]


def dict_factory(cursor, row) -> Record:
    """An sqlite3 row factory that returns a dictionary."""
    d = {
        col[0]: row[idx]
        for idx, col in enumerate(cursor.description)
    }
    return d

def get_conn() -> sqlite3.Connection:
    """Get a prepared connection to the sqlite3 database."""
    conn = sqlite3.connect(
        'test.db',
        isolation_level=None,
    )
    conn.execute('PRAGMA foreign_keys = ON')
    conn.row_factory = dict_factory
    return conn


class DrumResponse(NamedTuple):
    """Represents a response from a Drum operation."""
    status: Literal["ok", "error"]
    message: str
    data: Any | None = None


class SqliteDrum:
    """SQLite implementation of the Drum interface."""
    def __init__(self):
        pass

    def _execute_callback(
            self,
            *args,
            callback: Callable[[sqlite3.Cursor], Any] | None = None,
            commit: bool = True
    ) -> DrumResponse:
        """Execute a typical query, using a callback to handle the
        cursor.
        """
        conn = get_conn()
        try:
            cursor = conn.execute(*args)
        except sqlite3.DatabaseError as e:
            return DrumResponse('error', str(e), e)
        # Don't catch other kinds of errors
        else:
            if callback:
                result = callback(cursor)
                return DrumResponse('ok', 'Query executed', result)
            if commit:
                conn.commit()
                return DrumResponse('ok', 'Query executed', cursor)
        finally:
            conn.close()
        raise AssertionError("unreachable")

    def get_by_id(self, group: str, id: str) -> DrumResponse:
        """Retrieve a record from table by its id"""
        resp = self._execute_callback(
            f"""SELECT FROM {group} WHERE id = ?""",
            (id,),
            callback=lambda cursor: cursor.fetchone()
        )
        match resp:
            case ("error", msg, _):
                return DrumResponse("error", msg)
            case ("ok", _, None):
                return DrumResponse("error", "Record not found")
            case ("ok", _, record):
                return DrumResponse("ok", "Record found", record)
            case _:
                raise ValueError(f"Unexpected case: {resp}")

    def delete_by_id(self, group: str, id: str) -> DrumResponse:
        """Delete a record from table by its id"""
        resp = self._execute_callback(
            f"""DELETE FROM {group} WHERE id = ?""",
            (id,),
        )
        match resp:
            case ("error", msg, _):
                return DrumResponse("error", msg)
            case ("ok", _, cursor):
                assert cursor is not None
                if cursor.rowcount == 0:
                    return DrumResponse("ok", "Record not found")
                else:
                    return DrumResponse("ok", "Record deleted")

    def insert(self, group: str, record: Record) -> DrumResponse:
        """Insert a new record into the table"""
        assert "id" in record, "Record must have an id"
        keys = ", ".join(record.keys())
        placeholders = ", ".join("?" * len(record))
        resp = self._execute_callback(
            f"""INSERT INTO {group} ({keys}) VALUES ({placeholders})""",
            tuple(record.values()),
        )
        match resp:
            case ("error", msg, _):
                return DrumResponse("error", msg)
            case ("ok", _, cursor):
                assert cursor is not None
                return DrumResponse("ok", "Record inserted", cursor.lastrowid)
