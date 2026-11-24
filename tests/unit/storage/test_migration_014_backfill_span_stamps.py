"""Tests for migration 014: backfill the ingest stamps onto stored spans
(campus#1243, campus#1244).

campus.audit stamps each span it stores with ``tags.queue_ms`` and, for
producer spans, ``tags.producer_id``. Spans stored before that have
neither. The migration recovers the producer from the historical
``audit.traces.ingest`` event rows and the queue time from each span's
own headers, without touching anything else.
"""

import contextlib
import importlib
import io
import unittest

import campus.model as model
import campus.storage
from campus.common import env

# Configure test storage before importing storage-backed modules
env.set("STORAGE_MODE", "1")

STARTED_AT = "2026-11-24T10:17:58.349921+00:00"
ARRIVAL_MS = "1795515478341"
INGEST = "audit.traces.ingest"

DELIVERED = "1" * 16      # unstamped, header present, delivered by E1
PRESORTED = "2" * 16      # already carries a producer stamp, header present
REJECTED = "3" * 16       # referenced only by a rejected ingest, no header
OTHER_EVENT = "4" * 16    # another audit event, header present
BARE = "5" * 16           # no header, no event
E1 = "a" * 16             # successful ingest event, with a header
E2 = "b" * 16             # rejected ingest event
E3 = "c" * 16             # same path as an ingest, but not an ingest event
NEVER_STORED = "9" * 16   # delivered per E1, but absent from the table


def _migration():
    return importlib.import_module("migrations.014_backfill_span_stamps")


def _row(span_id, *, path="/x", status=200, api_key_id=None, header=None,
         tags=None, request_body=None):
    return model.TraceSpan(
        id=span_id,
        trace_id="0" * 32,
        span_id=span_id,
        method="POST",
        path=path,
        status_code=status,
        started_at=STARTED_AT,
        duration_ms=1.0,
        api_key_id=api_key_id,
        client_ip="127.0.0.1",
        request_headers={"X-Request-Start": header} if header else {},
        request_body=request_body,
        tags=tags or {},
    ).to_storage()


class _SpansTableTestCase(unittest.TestCase):
    def setUp(self):
        self.spans = campus.storage.tables.get_db("spans")
        self.spans.init_from_model("spans", model.TraceSpan)
        with contextlib.suppress(campus.storage.errors.StorageError):
            self.spans.delete_matching({})

    def _row(self, span_id):
        return self.spans.get_by_id(span_id)

    def _seed(self):
        ingest_path = "/audit/v1/traces/"
        self.spans.insert_many([
            _row(DELIVERED, header=ARRIVAL_MS),
            _row(PRESORTED, header=ARRIVAL_MS,
                 tags={"producer_id": "uid-old-key"}),
            _row(REJECTED),
            _row(OTHER_EVENT, header=ARRIVAL_MS,
                 tags={"event_type": "audit.traces.search"}),
            _row(BARE),
            _row(E1, path=ingest_path, status=201, api_key_id="uid-key-1",
                 header=ARRIVAL_MS, tags={"event_type": INGEST},
                 request_body={"spans": [
                     {"span_id": DELIVERED}, {"span_id": PRESORTED},
                     {"span_id": NEVER_STORED},
                 ]}),
            _row(E2, path=ingest_path, status=400, api_key_id="uid-key-2",
                 tags={"event_type": INGEST},
                 request_body={"spans": [{"span_id": REJECTED}]}),
            _row(E3, path=ingest_path, status=201, api_key_id="uid-key-3",
                 tags={"event_type": "audit.other"},
                 request_body={"spans": [{"span_id": BARE}]}),
        ])


class TestProducerMap(_SpansTableTestCase):
    def test_only_delivered_ingest_events_count(self):
        self._seed()
        producers = _migration()._producer_map(self.spans, batch_size=2)
        self.assertEqual(producers, {
            DELIVERED: "uid-key-1",
            PRESORTED: "uid-key-1",
            NEVER_STORED: "uid-key-1",
        })

    def test_first_delivery_wins_for_a_span_sent_twice(self):
        self.spans.insert_many([
            _row("a" * 16, path="/audit/v1/traces/", status=201,
                 api_key_id="uid-first", tags={"event_type": INGEST},
                 request_body={"spans": [{"span_id": DELIVERED}]}),
            _row("b" * 16, path="/audit/v1/traces/", status=201,
                 api_key_id="uid-second", tags={"event_type": INGEST},
                 request_body={"spans": [{"span_id": DELIVERED}]}),
        ])
        producers = _migration()._producer_map(self.spans, batch_size=1)
        self.assertEqual(producers, {DELIVERED: "uid-first"})

    def test_an_empty_table_maps_nothing(self):
        self.assertEqual(_migration()._producer_map(self.spans), {})


class TestBackfill(_SpansTableTestCase):
    EXPECTED = {
        "scanned": 8,
        "producer_stamped": 1,
        "queue_stamped": 4,
        "unchanged": 4,
    }

    def _backfill(self, **kwargs):
        migration = _migration()
        producers = migration._producer_map(self.spans, batch_size=2)
        return migration.backfill(
            self.spans, producers, batch_size=2, **kwargs,
        )

    def test_dry_run_reports_but_changes_nothing(self):
        self._seed()
        self.assertEqual(self._backfill(apply=False), self.EXPECTED)
        for span_id in (DELIVERED, PRESORTED, OTHER_EVENT, E1):
            self.assertNotIn("queue_ms", self._row(span_id)["tags"])
        self.assertNotIn("producer_id", self._row(DELIVERED)["tags"])

    def test_apply_stamps_only_what_was_missing(self):
        self._seed()
        self.assertEqual(self._backfill(apply=True), self.EXPECTED)

        delivered = self._row(DELIVERED)["tags"]
        self.assertEqual(delivered["producer_id"], "uid-key-1")
        self.assertAlmostEqual(delivered["queue_ms"], 8.921, places=2)

        presorted = self._row(PRESORTED)["tags"]
        self.assertEqual(presorted["producer_id"], "uid-old-key")
        self.assertAlmostEqual(presorted["queue_ms"], 8.921, places=2)

        # An audit's own event gets its queue time too (#1245).
        self.assertAlmostEqual(self._row(OTHER_EVENT)["tags"]["queue_ms"], 8.921, places=2)
        self.assertAlmostEqual(self._row(E1)["tags"]["queue_ms"], 8.921, places=2)
        self.assertEqual(self._row(E1)["tags"]["event_type"], INGEST)

        for span_id in (REJECTED, BARE, E2, E3):
            with self.subTest(span_id=span_id):
                self.assertNotIn("producer_id", self._row(span_id)["tags"])
                self.assertNotIn("queue_ms", self._row(span_id)["tags"])

    def test_second_apply_is_a_no_op(self):
        self._seed()
        self._backfill(apply=True)
        self.assertEqual(
            self._backfill(apply=True),
            {"scanned": 8, "producer_stamped": 0, "queue_stamped": 0,
             "unchanged": 8},
        )

    def test_limit_stops_after_that_many_spans(self):
        self._seed()
        counts = self._backfill(apply=True, limit=3)
        self.assertEqual(counts["scanned"], 3)
        self.assertIn("producer_id", self._row(DELIVERED)["tags"])
        # Fourth row in id order: not reached.
        self.assertNotIn("queue_ms", self._row(OTHER_EVENT)["tags"])

    def test_an_empty_table_scans_nothing(self):
        self.assertEqual(
            self._backfill(apply=True),
            {"scanned": 0, "producer_stamped": 0, "queue_stamped": 0,
             "unchanged": 0},
        )


class TestUpgradeAndDowngrade(_SpansTableTestCase):
    def test_upgrade_writes_and_says_what_it_did(self):
        self._seed()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            _migration().upgrade(apply=True)
        self.assertIn("1 stamped with producer_id", output.getvalue())
        self.assertIn("4 stamped with queue_ms", output.getvalue())
        self.assertNotIn("dry run", output.getvalue())
        self.assertEqual(
            self._row(DELIVERED)["tags"]["producer_id"], "uid-key-1",
        )

    def test_upgrade_without_apply_is_a_dry_run(self):
        self._seed()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            _migration().upgrade()
        self.assertIn("dry run", output.getvalue())
        self.assertNotIn("producer_id", self._row(DELIVERED)["tags"])

    def test_downgrade_removes_both_stamps_and_keeps_the_rest(self):
        self._seed()
        migration = _migration()
        migration.upgrade(apply=True)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            migration.downgrade()
        self.assertIn("4 unstamped", output.getvalue())

        for span_id in (DELIVERED, PRESORTED, OTHER_EVENT, E1, REJECTED, BARE):
            with self.subTest(span_id=span_id):
                tags = self._row(span_id)["tags"]
                self.assertNotIn("producer_id", tags)
                self.assertNotIn("queue_ms", tags)
        self.assertEqual(self._row(OTHER_EVENT)["tags"]["event_type"],
                         "audit.traces.search")

    def test_downgrade_is_idempotent(self):
        self._seed()
        migration = _migration()
        migration.upgrade(apply=True)
        migration.downgrade()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            migration.downgrade()
        self.assertIn("0 unstamped", output.getvalue())

    def test_targets_the_audit_database(self):
        self.assertEqual(_migration().TARGET_DB, "audit")


if __name__ == "__main__":
    unittest.main()
