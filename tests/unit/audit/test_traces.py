"""Unit tests for campus.audit.client.v1.traces module.

These tests verify that the Traces resource properly constructs API requests
and follows Campus API schema conventions.

Test Principles:
- Test resource chaining and path construction
- Test bracket access for IDs
- Test property access for named sub-resources
- Test HTTP method calls (mocked)
"""

import unittest
from unittest.mock import Mock, MagicMock, call

from campus.audit.client.v1.traces import Traces
from campus.audit.client.v1.root import AuditRoot
from campus.common.http.interface import JsonClient


class TestTracesResource(unittest.TestCase):
    """Test Traces resource collection."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=JsonClient)
        self.mock_client.base_url = "https://audit.test"
        self.root = AuditRoot(json_client=self.mock_client)

    def test_traces_path_has_trailing_slash(self):
        """Test that Traces.path has trailing slash (ResourceCollection requirement)."""
        self.assertTrue(Traces.path.endswith("/"))
        self.assertEqual(Traces.path, "traces/")

    def test_traces_make_path(self):
        """Test that make_path constructs correct paths."""
        traces = Traces(client=self.mock_client, root=self.root)

        # Base path
        self.assertEqual(traces.make_path(), "/audit/v1/traces/")

        # With sub-path
        self.assertEqual(traces.make_path("search"), "/audit/v1/traces/search")

    def test_traces_make_url(self):
        """Test that make_url constructs full URLs."""
        traces = Traces(client=self.mock_client, root=self.root)

        self.assertEqual(traces.make_url(), "https://audit.test/audit/v1/traces/")
        self.assertEqual(traces.make_url("search"), "https://audit.test/audit/v1/traces/search")

    def test_traces_getitem_returns_trace_resource(self):
        """Test that bracket access creates Trace resource."""
        traces = Traces(client=self.mock_client, root=self.root)

        trace = traces["abc123"]

        # Verify it's a Trace resource
        self.assertIsInstance(trace, Traces.Trace)
        self.assertEqual(trace.trace_id, "abc123")
        self.assertEqual(trace.parent, traces)

    def test_traces_new_single_span(self):
        """Test that new(span) calls POST with correct payload."""
        traces = Traces(client=self.mock_client, root=self.root)

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        self.mock_client.post.return_value = mock_response

        span = {"trace_id": "abc123", "span_id": "def456"}
        result = traces.new(span)

        # Verify POST was called correctly
        self.mock_client.post.assert_called_once_with(
            "/audit/v1/traces/",
            json={"spans": [span]}
        )
        self.assertEqual(result, mock_response)

    def test_traces_new_batch_spans(self):
        """Test that new(s1, s2, s3) calls POST with all spans."""
        traces = Traces(client=self.mock_client, root=self.root)

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        self.mock_client.post.return_value = mock_response

        span1 = {"trace_id": "abc123", "span_id": "def456"}
        span2 = {"trace_id": "abc123", "span_id": "ghi789"}
        span3 = {"trace_id": "abc123", "span_id": "jkl012"}

        result = traces.new(span1, span2, span3)

        # Verify POST was called with all spans
        self.mock_client.post.assert_called_once_with(
            "/audit/v1/traces/",
            json={"spans": [span1, span2, span3]}
        )
        self.assertEqual(result, mock_response)

    def test_traces_list_with_defaults(self):
        """Test that list() uses default parameters."""
        traces = Traces(client=self.mock_client, root=self.root)

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        self.mock_client.get.return_value = mock_response

        result = traces.list()

        # Verify GET was called with default limit
        self.mock_client.get.assert_called_once_with(
            "/audit/v1/traces/",
            params={"limit": 50}
        )
        self.assertEqual(result, mock_response)

    def test_traces_list_with_params(self):
        """Test that list(limit=10, since=...) includes parameters."""
        traces = Traces(client=self.mock_client, root=self.root)

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        self.mock_client.get.return_value = mock_response

        result = traces.list(limit=10, since="2025-01-01T00:00:00Z")

        # Verify GET was called with parameters
        self.mock_client.get.assert_called_once_with(
            "/audit/v1/traces/",
            params={"limit": 10, "since": "2025-01-01T00:00:00Z"}
        )
        self.assertEqual(result, mock_response)

    def test_traces_search_with_filters(self):
        """Test that search includes query parameters."""
        traces = Traces(client=self.mock_client, root=self.root)

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        self.mock_client.get.return_value = mock_response

        result = traces.search(path="/api/v1/users", status=200)

        # Verify GET was called with search filters
        self.mock_client.get.assert_called_once()
        args, kwargs = self.mock_client.get.call_args
        self.assertEqual(args[0], "/audit/v1/traces/search")
        self.assertIn("path", kwargs["params"])
        self.assertIn("status", kwargs["params"])
        self.assertEqual(result, mock_response)


class TestTraceResource(unittest.TestCase):
    """Test Trace resource (individual trace by ID)."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=JsonClient)
        self.mock_client.base_url = "https://audit.test"
        self.root = AuditRoot(json_client=self.mock_client)
        self.traces = Traces(client=self.mock_client, root=self.root)

    def test_trace_path_construction(self):
        """Test that Trace path includes trace_id."""
        trace = self.traces["abc123"]

        self.assertEqual(trace.path, "/audit/v1/traces/abc123")
        self.assertEqual(trace.make_path(end_slash=True), "/audit/v1/traces/abc123/")

    def test_trace_get_tree(self):
        """Test that get_tree() calls GET to correct endpoint."""
        trace = self.traces["abc123"]

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        self.mock_client.get.return_value = mock_response

        result = trace.get_tree()

        # Verify GET was called
        self.mock_client.get.assert_called_once_with("/audit/v1/traces/abc123/")
        self.assertEqual(result, mock_response)

    def test_trace_spans_property_returns_spans_resource(self):
        """Test that .spans property returns Spans resource."""
        trace = self.traces["abc123"]

        spans = trace.spans

        # Verify it's a Spans resource
        self.assertIsInstance(spans, Traces.Spans)
        self.assertEqual(spans.trace_id, "abc123")
        self.assertEqual(spans.parent, trace)


class TestSpansResource(unittest.TestCase):
    """Test Spans resource (nested within Trace)."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=JsonClient)
        self.mock_client.base_url = "https://audit.test"
        self.root = AuditRoot(json_client=self.mock_client)
        self.traces = Traces(client=self.mock_client, root=self.root)
        self.trace = self.traces["abc123"]

    def test_spans_path_construction(self):
        """Test that Spans path includes 'spans/'."""
        spans = self.trace.spans

        self.assertEqual(spans.path, "spans/")
        self.assertEqual(spans.make_path(), "/audit/v1/traces/abc123/spans/")

    def test_spans_list(self):
        """Test that list() calls GET to list spans."""
        spans = self.trace.spans

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        self.mock_client.get.return_value = mock_response

        result = spans.list()

        # Verify GET was called
        self.mock_client.get.assert_called_once_with("/audit/v1/traces/abc123/spans/")
        self.assertEqual(result, mock_response)

    def test_spans_getitem_returns_span_resource(self):
        """Test that bracket access creates Span resource."""
        spans = self.trace.spans

        span = spans["def456"]

        # Verify it's a Span resource
        self.assertIsInstance(span, Traces.Spans.Span)
        self.assertEqual(span.span_id, "def456")
        self.assertEqual(span.parent, spans)


class TestSpanResource(unittest.TestCase):
    """Test Span resource (individual span within Spans)."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=JsonClient)
        self.mock_client.base_url = "https://audit.test"
        self.root = AuditRoot(json_client=self.mock_client)
        self.traces = Traces(client=self.mock_client, root=self.root)
        self.trace = self.traces["abc123"]
        self.spans = self.trace.spans

    def test_span_path_construction(self):
        """Test that Span path includes span_id."""
        span = self.spans["def456"]

        self.assertEqual(span.path, "/audit/v1/traces/abc123/spans/def456")
        self.assertEqual(span.make_path(end_slash=True), "/audit/v1/traces/abc123/spans/def456/")

    def test_span_get(self):
        """Test that get() calls GET to correct endpoint."""
        span = self.spans["def456"]

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        self.mock_client.get.return_value = mock_response

        result = span.get()

        # Verify GET was called
        self.mock_client.get.assert_called_once_with("/audit/v1/traces/abc123/spans/def456/")
        self.assertEqual(result, mock_response)


if __name__ == "__main__":
    unittest.main()
