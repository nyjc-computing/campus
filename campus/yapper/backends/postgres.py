"""campus.yapper.backends.postgres

PostgreSQL backend for campus.yapper.
This implementation is intended for production use.
"""

from contextlib import contextmanager
from typing import Generator, TypedDict

import psycopg2
import psycopg2.extras

from campus.yapper.base import ClientId, Event, EventLabel, EventData, YapperInterface


class PostgreSQLResult(TypedDict):
    """Typed dictionary for PostgreSQL query results."""
    fetchall: list[dict]
    lastrowid: int | None
    rowcount: int


def cursor_to_dict(cursor: psycopg2.extras.RealDictCursor) -> PostgreSQLResult:
    """Extract query results and commonly used attributes from cursor."""
    # Check if the cursor has results to fetch
    try:
        rows = cursor.fetchall()
        return {
            # Convert RealDictRow to dict
            "fetchall": [dict(row) for row in rows],
            "lastrowid": None,  # PostgreSQL doesn't have lastrowid like SQLite
            "rowcount": cursor.rowcount,
        }
    except psycopg2.ProgrammingError:
        # No results to fetch (e.g., DDL statements like CREATE TABLE)
        return {
            "fetchall": [],
            "lastrowid": None,
            "rowcount": cursor.rowcount,
        }


class PostgreSQLYapper(YapperInterface):

    def __init__(
            self,
            client_id: ClientId,
            *,
            db_uri: str
    ) -> None:
        super().__init__(client_id)
        self.db_uri = db_uri

    @contextmanager
    def _get_conn(self) -> Generator[psycopg2.extensions.connection, None, None]:
        """Context manager for PostgreSQL database connection."""
        conn = psycopg2.connect(self.db_uri)
        conn.autocommit = True  # Use autocommit mode for performance
        try:
            yield conn
        finally:
            conn.close()

    def _execute(self, query: str, params: tuple = ()) -> PostgreSQLResult:
        """Execute a SQL query."""
        with self._get_conn() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(query, params)
            return cursor_to_dict(cursor)

    def _executemany(self, query: str, params: list[tuple]) -> PostgreSQLResult:
        """Execute a SQL query with multiple parameters."""
        with self._get_conn() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.executemany(query, params)
            return cursor_to_dict(cursor)

    def _init_db(self) -> None:
        """Initialize the PostgreSQL database."""
        self._execute(
            """CREATE TABLE IF NOT EXISTS events (
                id BIGSERIAL PRIMARY KEY,
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
                event_id BIGINT NOT NULL,
                PRIMARY KEY (client_id, label, event_id),
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
        result = self._execute(
            "INSERT INTO events (label, data) VALUES (%s, %s) RETURNING id",
            (label, str(data))
        )
        event_id = result["fetchall"][0]["id"]

        # Get subscriptions
        subscriptions = [
            row["client_id"] for row in self._execute(
                "SELECT client_id FROM subscriptions WHERE label = %s",
                (label,)
            )["fetchall"]
        ]

        # Notify subscriptions
        if subscriptions:
            self._executemany(
                "INSERT INTO unread (client_id, event_id) VALUES (%s, %s)",
                [(client_id, event_id) for client_id in subscriptions]
            )

    def subscribe(self, label: EventLabel) -> None:
        """Subscribe to an event label."""
        self._execute(
            """INSERT INTO subscriptions (client_id, label)
              VALUES (%s, %s)
              ON CONFLICT (client_id, label) DO NOTHING""",
            (self.client_id, label)
        )

    def unsubscribe(self, label: EventLabel) -> None:
        """Unsubscribe from an event label.

        A label value of * will unsubscribe from all labels.
        This is not set as a default value for safety reasons.
        """
        if label == "*":
            self._execute(
                "DELETE FROM subscriptions WHERE client_id = %s",
                (self.client_id,)
            )
        else:
            self._execute(
                "DELETE FROM subscriptions WHERE client_id = %s AND label = %s",
                (self.client_id, label)
            )
        self._sweep()  # Clean up old events

    def _clear_unread(self) -> None:
        """Clear unread events for this client.

        This is performed as part of other operations, and is seldom called on
        its own.
        """
        self._execute(
            "DELETE FROM unread WHERE client_id = %s",
            (self.client_id,)
        )

    def listen(self) -> list[Event]:
        """Listen for events from the message broker."""
        # NOTE: There is a tiny window between the two queries where
        # events could be emitted but not collected before being cleared.
        # In a production system, this should use transactions or
        # a more sophisticated event delivery mechanism.

        # Get and clear unread events
        result = self._execute(
            "SELECT events.label, events.data FROM events "
            "JOIN unread ON events.id = unread.event_id "
            "WHERE unread.client_id = %s",
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
