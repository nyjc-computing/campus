"""Unit tests for the traces search/list filters (campus#1164).

The search filters had no unit coverage at all — any backend
divergence in the query language landed silently (the path filter
returned zero for every path on dev, 2026-11-18, and neither the
resource layer nor the storage seam had a test to catch it). These
tests pin each filter at the resource level against the test storage
backend: path, status, user, journey tag, the since/until both-bounds
time range (the campus-core#3 `between` seam), and audit-event
inclusion (#941).
"""

import unittest

from campus.common import env

# Configure test storage before importing storage-backed modules
env.set('STORAGE_MODE', "1")

T1 = "c" * 32
T2 = "d" * 32
T3 = "e" * 32  # audit-event trace (#941)


def _span(trace_id: str, *, path: str, status: int, user_id: str | None,
          started_at: str, tags: dict | None = None) -> dict:
    from campus.model.audit import TraceSpan
    span = TraceSpan(
        trace_id=trace_id,
        span_id=trace_id[:16],
        parent_span_id=None,
        method="GET",
        path=path,
        query_params={},
        status_code=status,
        started_at=started_at,
        duration_ms=10.0,
        client_id=None,
        user_id=user_id,
        client_ip="127.0.0.1",
        user_agent="test",
        error_message=None,
        tags=tags or {},
    )
    return span.to_storage()


class TestTraceSearchFilters(unittest.TestCase):
    """Every search filter must actually filter — never silently pass."""

    def setUp(self):
        from campus.audit.resources.traces import traces_storage

        traces_storage.init_from_model("spans", _trace_span_model())
        traces_storage.delete_matching({})
        traces_storage.insert_one(_span(
            T1, path="/assignments/new", status=200,
            user_id="alice@nyjc.edu.sg", started_at="2026-11-20T10:00:00Z",
            tags={"journey_id": "journey-1"},
        ))
        traces_storage.insert_one(_span(
            T2, path="/api/v1/apps", status=201,
            user_id="bob@nyjc.edu.sg", started_at="2026-11-20T11:00:00Z",
        ))
        # Audit event: one-span trace, event_type tag, no request
        # identity (#941 discriminator).
        traces_storage.insert_one(_span(
            T3, path="/audit/v1/traces/", status=200,
            user_id=None, started_at="2026-11-20T12:00:00Z",
            tags={"event_type": "audit.apikeys.auth.success"},
        ))

    def tearDown(self):
        from campus.audit.resources.traces import traces_storage
        traces_storage.delete_matching({})

    def _search(self, **kwargs):
        from campus.audit.resources.traces import TraceFilter, TracesResource
        return TracesResource().search(
            trace_filter=TraceFilter(), **kwargs
        )

    @staticmethod
    def _trace_ids(page) -> set:
        return {s.trace_id for s in page.summaries}

    def test_path_filter_matches_exact_path(self):
        """search?path=X returns traces whose root span path is X (#1164)."""
        page = self._search(path="/assignments/new")
        self.assertEqual(self._trace_ids(page), {T1})
        page = self._search(path="/api/v1/apps")
        self.assertEqual(self._trace_ids(page), {T2})

    def test_path_filter_no_match_yields_empty_page(self):
        """A path that exists in list but is searched wrongly yields no
        trace — and a genuinely absent path yields an empty page
        (not an error, not every trace)."""
        page = self._search(path="/assignments/new/")
        self.assertEqual(self._trace_ids(page), set())

    def test_status_filter(self):
        page = self._search(status=201)
        self.assertEqual(self._trace_ids(page), {T2})

    def test_user_filter(self):
        page = self._search(user_id="alice@nyjc.edu.sg")
        self.assertEqual(self._trace_ids(page), {T1})

    def test_journey_filter_matches_span_tags_in_python(self):
        """journey_id matches spans.tags in Python (#803), not storage."""
        page = self._search(journey_id="journey-1")
        self.assertEqual(self._trace_ids(page), {T1})

    def test_time_range_both_bounds(self):
        """since AND until hit the storage between seam (campus-core#3)."""
        page = self._search(
            since="2026-11-20T09:00:00Z", until="2026-11-20T10:30:00Z"
        )
        self.assertEqual(self._trace_ids(page), {T1})

    def test_time_range_single_bounds(self):
        page = self._search(since="2026-11-20T10:30:00Z")
        self.assertEqual(self._trace_ids(page), {T2, T3})
        page = self._search(until="2026-11-20T10:30:00Z")
        self.assertEqual(self._trace_ids(page), {T1})

    def test_events_included_by_default_and_excludable(self):
        """Audit-event traces are included by default (#941); events=
        false drops them from list and search."""
        self.assertIn(T3, self._trace_ids(self._search()))
        self.assertIn(T3, self._trace_ids(self._search(path="/audit/v1/traces/")))
        page = self._search(include_events=False)
        self.assertNotIn(T3, self._trace_ids(page))
        self.assertEqual(self._trace_ids(page), {T1, T2})

    def test_list_endpoint_shares_the_filters(self):
        """list() applies the same time/event filters as search()."""
        from campus.audit.resources.traces import TraceFilter, TracesResource
        page = TracesResource().list(trace_filter=TraceFilter())
        self.assertEqual(self._trace_ids(page), {T1, T2, T3})


def _trace_span_model():
    from campus.model import audit as audit_model
    return audit_model.TraceSpan


if __name__ == "__main__":
    unittest.main()
