"""Trace pagination keeps caller time filters on continuation pages.

Regression for the 2026-11-24 classroom-journey investigation finding:
`_query_trace_page` overwrote the caller's `started_at` filter with the
cursor's upper bound on every page past the first, so a filtered
search's continuation pages silently returned traces older than
`--since` (a single-day window came back with the full history — 2,406
raw rows for 1,246 unique traces). The fix merges the caller's bound
with the cursor bound into one range operator.
"""

import importlib
import unittest
import uuid

SINCE = "2026-11-24T00:00:00Z"
UNTIL = "2026-11-24T23:59:59Z"


class TestTracePaginationKeepsTimeFilters(unittest.TestCase):
    """search/list continuation pages honor the caller's time bounds."""

    def setUp(self):
        # Rebind the traces module's storage singleton to a per-test
        # sqlite table: the module binds its backend at import time,
        # which in a full-directory run happens before any test code
        # runs and lands on the postgres backend.
        from campus.storage.tables.backend.sqlite import SQLiteTable

        traces_module = importlib.import_module(
            "campus.audit.resources.traces"
        )
        traces_module.traces_storage = SQLiteTable("spans")
        traces_module.TracesResource.init_storage()
        self.traces_storage = traces_module.traces_storage
        self.trace_filter = traces_module.TraceFilter(None, None)
        self.resource = traces_module.TracesResource()
        # Per-test client filter isolates rows in case the sqlite
        # table persists rows across tests.
        self.client_id = f"uid-client-{uuid.uuid4().hex[:8]}"
        self._seed()

    def _seed(self):
        """Ingest 4 in-window traces (11-24 10:00–10:03) and 4 pre-window
        traces (11-23), one span each, all on a unique client_id."""
        from campus import model

        spans = []
        self.in_ids, self.pre_ids = [], []
        for i in range(4):
            in_id = uuid.uuid4().hex
            pre_id = uuid.uuid4().hex
            self.in_ids.append(in_id)
            self.pre_ids.append(pre_id)
            spans.append(model.TraceSpan(
                trace_id=in_id,
                span_id=uuid.uuid4().hex[:16],
                started_at=f"2026-11-24T10:0{i}:00Z",
                method="GET",
                path="/dashboard",
                status_code=200,
                duration_ms=10,
                client_ip="127.0.0.1",
                client_id=self.client_id,
            ).to_storage())
            spans.append(model.TraceSpan(
                trace_id=pre_id,
                span_id=uuid.uuid4().hex[:16],
                started_at=f"2026-11-23T09:0{i}:00Z",
                method="GET",
                path="/dashboard",
                status_code=200,
                duration_ms=10,
                client_ip="127.0.0.1",
                client_id=self.client_id,
            ).to_storage())
        self.traces_storage.insert_many(spans)

    def _search(self, **kwargs):
        kwargs.setdefault("client_id", self.client_id)
        kwargs.setdefault("trace_filter", self.trace_filter)
        return self.resource.search(**kwargs)

    def test_search_continuation_pages_keep_since(self):
        """Page 2 of a --since-bounded search returns only in-window
        traces, not the pre-window history."""
        page1 = self._search(since=SINCE, limit=3)

        self.assertTrue(page1.has_more)
        self.assertTrue(
            {s.trace_id for s in page1.summaries} <= set(self.in_ids)
        )
        self.assertFalse(
            any(s.trace_id in self.pre_ids for s in page1.summaries)
        )

        page2 = self._search(since=SINCE, limit=3, cursor=page1.next_cursor)

        # The leak filled this page with the four 11-23 traces.
        self.assertEqual(
            [s.trace_id for s in page2.summaries],
            [self.in_ids[0]],
        )
        self.assertFalse(page2.has_more)
        for summary in page2.summaries:
            self.assertGreaterEqual(summary.started_at, SINCE)

    def test_search_continuation_pages_keep_since_and_until(self):
        """A since+until window survives continuation too: the caller's
        between() bound and the cursor bound merge into one range."""
        until = "2026-11-24T10:02:59Z"
        page1 = self._search(since=SINCE, until=until, limit=2)

        self.assertTrue(page1.has_more)
        page2 = self._search(
            since=SINCE, until=until, limit=2, cursor=page1.next_cursor
        )

        all_seen = [s.trace_id for s in page1.summaries + page2.summaries]
        self.assertEqual(sorted(all_seen), sorted(self.in_ids[:3]))
        self.assertFalse(any(t in self.pre_ids for t in all_seen))

    def test_list_continuation_pages_keep_since(self):
        """The list() surface shares the helper and gets the same fix."""
        page1 = self.resource.list(
            since=SINCE,
            limit=3,
            trace_filter=self.trace_filter,
        )
        self.assertTrue(page1.has_more)

        page2 = self.resource.list(
            since=SINCE,
            limit=3,
            cursor=page1.next_cursor,
            trace_filter=self.trace_filter,
        )
        self.assertEqual(
            [s.trace_id for s in page2.summaries],
            [self.in_ids[0]],
        )
        for summary in page2.summaries:
            self.assertGreaterEqual(summary.started_at, SINCE)
