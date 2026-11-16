"""Unit tests for campus.yapper backends.

Covers the emit-to-unread delivery flow of the SQLite backend, which
regressed in #225 (the unread INSERT omitted the NOT NULL label column
and bound the whole inserted row dict as event_id).
"""

import pathlib
import tempfile
import unittest

from campus.yapper.backends.sqlite import SQLiteYapper


class TestSQLiteYapperEmit(unittest.TestCase):
    """Tests for SQLiteYapper emit/listen delivery.

    The backend opens a new connection per operation, so tests must use
    a file-backed database; a ":memory:" database would be empty on
    every connection.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = str(pathlib.Path(self._tmp.name) / "yapper.db")

    def tearDown(self):
        self._tmp.cleanup()

    def test_emit_delivers_event_to_subscriber(self):
        """emit() records the event as unread for subscribed clients."""
        yapper = SQLiteYapper(db=self.db, client_id="client-a")
        yapper.start()
        yapper.subscribe("campus.test")

        yapper.emit("campus.test", {"key": "value"})

        events = yapper.listen()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].label, "campus.test")
        self.assertEqual(events[0].data, str({"key": "value"}))
        # listen() clears the unread queue
        self.assertEqual(yapper.listen(), [])

    def test_emit_without_subscription_not_delivered(self):
        """emit() does not record unread rows without a subscription."""
        yapper = SQLiteYapper(db=self.db, client_id="client-a")
        yapper.start()

        yapper.emit("campus.test", {"key": "value"})

        self.assertEqual(yapper.listen(), [])

    def test_emit_delivered_only_to_subscribed_client(self):
        """Two clients on one database: only the subscriber is notified."""
        subscriber = SQLiteYapper(db=self.db, client_id="client-a")
        other = SQLiteYapper(db=self.db, client_id="client-b")
        subscriber.start()
        other.start()
        subscriber.subscribe("campus.test")

        other.emit("campus.test", {"key": "value"})

        self.assertEqual(len(subscriber.listen()), 1)
        self.assertEqual(other.listen(), [])


if __name__ == '__main__':
    unittest.main()
