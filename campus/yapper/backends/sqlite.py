"""campus.yapper.backends.sqlite

SQLite backend for campus.yapper.
This implementation is for local testing purposes only.
It is not intended for production use.
"""

from typing import Any, Generator, TypedDict
from contextlib import contextmanager
import sqlite3

from campus.yapper.base import ClientId, Event, EventLabel, EventData, YapperInterface


class SQLiteResult(TypedDict):
    """Typed dictionary for SQLite query results."""
    fetchall: list[dict]
    lastrowid: int | None
    rowcount: int


def dict_factory(cursor: sqlite3.Cursor, row: sqlite3.Row) -> dict[str, Any]:
    """Convert SQLite rows to dictionaries."""
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def cursor_to_dict(cursor: sqlite3.Cursor) -> SQLiteResult:
    """Extract query results and commonly used attributes from cursor."""
    # Test implementation does not expect large result set, fetchall() considered safe.
    return {
        "fetchall": cursor.fetchall(),
        "lastrowid": cursor.lastrowid,
        "rowcount": cursor.rowcount,
    }


class SQLiteYapper(YapperInterface):

    def __init__(self, *, db: str = ":memory:", client_id: ClientId) -> None:
        super().__init__()
        self.db_uri = db
        self.client_id = client_id

    @contextmanager
    def _get_conn(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for SQLite database connection."""
        conn = sqlite3.connect(self.db_uri)
        conn.row_factory = dict_factory
        conn.execute("PRAGMA foreign_keys = ON")
        conn.isolation_level = None  # Use autocommit mode for performance
        try:
            yield conn
        finally:
            conn.close()

    def _execute(self, query: str, params: tuple = ()) -> SQLiteResult:
        """Execute a SQL query."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor_to_dict(cursor)

    def _executemany(self, query: str, params: list[tuple]) -> SQLiteResult:
        """Execute a SQL query with multiple parameters."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params)
            return cursor_to_dict(cursor)

    def _init_db(self) -> None:
        """Initialize the SQLite database."""
        self._execute(
            """CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY,
                label TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );"""
        )
        self._execute(
            """CREATE TABLE IF NOT EXISTS subscriptions (
                client_id TEXT NOT NULL,
                label TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (client_id, label)
            );"""
        )
        self._execute(
            """CREATE TABLE IF NOT EXISTS unread (
                client_id TEXT NOT NULL,
                label TEXT NOT NULL,
                event_id INTEGER NOT NULL,
                PRIMARY KEY (client_id, event_id),
                FOREIGN KEY (event_id)
                    REFERENCES events(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (client_id, label)
                    REFERENCES subscriptions(client_id, label)
                    ON DELETE CASCADE
            );"""
        )

    def emit(self, label: EventLabel, data: EventData | None = None) -> None:
        """Emit an event to the message broker."""
        data = data or {}
        event_id = self._execute(
            "INSERT INTO events (label, data) VALUES (?, ?) RETURNING id",
            (label, str(data))
        )["fetchall"][0]
        # Get subscriptions
        subscriptions = [
            row["client_id"] for row in self._execute(
                "SELECT client_id FROM subscriptions WHERE label = ?",
                (label,)
            )["fetchall"]
        ]
        # Notify subscriptions
        self._executemany(
            "INSERT INTO unread (client_id, event_id) VALUES (?, ?)",
            [(client_id, event_id) for client_id in subscriptions]
        )

    def subscribe(self, label: EventLabel) -> None:
        """Subscribe to an event label."""
        self._execute(
            """INSERT OR IGNORE INTO subscriptions (client_id, label)
              VALUES (?, ?)""",
            (self.client_id, label)
        )

    def unsubscribe(self, label: EventLabel) -> None:
        """Unsubscribe from an event label.

        A label value of * will unsubscribe from all labels.
        This is not set as a default value for safety reasons.
        """
        self._execute(
            (
                "DELETE FROM subscriptions WHERE client_id = ?"
                if label == "*"
                else "DELETE FROM subscriptions WHERE client_id = ? AND label = ?"
            ),
            (self.client_id, label)
        )
        self._sweep()  # Clean up old events

    def _clear_unread(self) -> None:
        """Clear unread events for this client.

        This is performed as part of other operations, and is seldom called on
        its own.
        """
        self._execute(
            "DELETE FROM unread WHERE client_id = ?",
            (self.client_id,)
        )

    def listen(self) -> list[Event]:
        """Listen for events from the message broker."""
        # HACK: There is a tiny window between the two queries where
        # events could be emitted but not collected before being cleared.
        # This is ignored in this test SQLite client, but will be an issue
        # in a real implementation under higher loads.

        # Get and clear unread events
        result = self._execute(
            "SELECT events.label, events.data FROM events "
            "JOIN unread ON events.id = unread.event_id "
            "WHERE unread.client_id = ?",
            (self.client_id,)
        )
        events = result["fetchall"]
        # Clear unread events
        self._clear_unread()
        # Return events
        return [
            Event(row["label"], row["data"])
            for row in events
        ]

    def _sweep(self) -> None:
        """Clear old events without subscriptions."""
        self._execute(
            "DELETE FROM events WHERE id NOT IN "
            "(SELECT DISTINCT event_id FROM unread)"
        )

    def start(self) -> None:
        """Start the Yapper instance."""
        self._init_db()
        super().start()

    def stop(self) -> None:
        """Stop the Yapper instance."""
        self.listen()  # also clears unread
        self.unsubscribe("*")
        self._sweep()
        super().stop()
