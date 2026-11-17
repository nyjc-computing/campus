"""Unit tests for the trace-read scoping filter (#944).

Pure logic: TraceFilter matching semantics and _apply_bind query
intersection. No storage, no app — the E2E matrix lives in
tests/integration/test_audit_trace_scoping.py.
"""

import unittest

from campus.audit.resources.traces import TraceFilter, _apply_bind


class TestTraceFilterMatching(unittest.TestCase):
    """Span-level match semantics: a span must satisfy every set axis."""

    def test_unscoped_filter_matches_everything(self):
        f = TraceFilter()
        self.assertFalse(f.is_scoped())
        self.assertTrue(f.matches_span({"user_id": None, "client_id": None}))
        self.assertTrue(f.matches_span({"user_id": "a@x", "client_id": "c1"}))

    def test_user_bind_matches_only_that_user(self):
        f = TraceFilter(user_id="a@x")
        self.assertTrue(f.is_scoped())
        self.assertTrue(f.matches_span({"user_id": "a@x"}))
        self.assertFalse(f.matches_span({"user_id": "b@x"}))

    def test_null_identity_spans_match_no_bind(self):
        """Anonymous spans (null user/client) are invisible to scoped
        keys — the default-no ruling from the #944 design."""
        self.assertFalse(
            TraceFilter(user_id="a@x").matches_span({"user_id": None})
        )
        self.assertFalse(
            TraceFilter(client_id="c1").matches_span({"client_id": None})
        )

    def test_both_binds_require_both_axes(self):
        f = TraceFilter(user_id="a@x", client_id="c1")
        self.assertTrue(
            f.matches_span({"user_id": "a@x", "client_id": "c1"})
        )
        self.assertFalse(
            f.matches_span({"user_id": "a@x", "client_id": "c2"})
        )
        self.assertFalse(
            f.matches_span({"user_id": "b@x", "client_id": "c1"})
        )

    def test_missing_span_keys_are_not_matches(self):
        """A span record without the identity key at all behaves like
        null identity."""
        self.assertFalse(TraceFilter(user_id="a@x").matches_span({}))


class TestApplyBind(unittest.TestCase):
    """_apply_bind: merge the bind axes; conflicting caller filters
    signal a guaranteed-empty result (False), not an error."""

    def test_unscoped_bind_leaves_query_untouched(self):
        query = {"user_id": "b@x"}
        self.assertTrue(_apply_bind(query, TraceFilter()))
        self.assertEqual(query, {"user_id": "b@x"})

    def test_bind_overwrites_no_filter(self):
        query = {}
        self.assertTrue(_apply_bind(query, TraceFilter(user_id="a@x")))
        self.assertEqual(query, {"user_id": "a@x"})

    def test_matching_caller_filter_is_kept(self):
        query = {"user_id": "a@x"}
        self.assertTrue(_apply_bind(query, TraceFilter(user_id="a@x")))
        self.assertEqual(query, {"user_id": "a@x"})

    def test_conflicting_caller_filter_signals_empty(self):
        query = {"user_id": "b@x"}
        self.assertFalse(_apply_bind(query, TraceFilter(user_id="a@x")))

    def test_conflict_on_one_axis_only(self):
        query = {"client_id": "c9"}
        self.assertFalse(
            _apply_bind(query, TraceFilter(user_id="a@x", client_id="c1"))
        )


if __name__ == "__main__":
    unittest.main()
