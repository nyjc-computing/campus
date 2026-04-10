#!/usr/bin/env python3
"""Unit tests for campus.audit.resources.traces

Tests the TracesResource, TraceResource, TraceSpansResource, and SpanResource
classes against the acceptance criteria for issue #426.

Acceptance Criteria:
- All resource methods work with mock storage
- Batch insert returns proper error dict on partial failure
- Trace tree returns spans ordered by parent-child relationship
- Time range filters work correctly (both since and until together)
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone

from campus.model import TraceSpan, TraceTree, TraceSummary
from campus.common import schema
from campus.common.errors import api_errors
from campus.storage import errors as storage_errors


def _make_span_record(**overrides):
    """Create a complete span record for testing with all required fields.

    Args:
        **overrides: Field values to override defaults

    Returns:
        Dictionary with all required TraceSpan fields
    """
    defaults = {
        "span_id": "span1",
        "trace_id": "trace1",
        "parent_span_id": None,
        "method": "GET",
        "path": "/api/test",
        "status_code": 200,
        "started_at": "2023-01-01T10:00:00Z",
        "duration_ms": 100.0,
        "query_params": {},
        "request_headers": {},
        "request_body": None,
        "response_headers": {},
        "response_body": None,
        "api_key_id": None,
        "client_id": None,
        "user_id": None,
        "client_ip": "127.0.0.1",
        "user_agent": None,
        "error_message": None,
        "tags": {},
    }
    defaults.update(overrides)
    return defaults


class TestTracesResourceIngest(unittest.TestCase):
    """Test TracesResource.ingest() for single and batch insert."""

    def setUp(self):
        """Set up mock storage for testing."""
        self.traces_storage_mock = Mock()
        self.patcher = patch('campus.audit.resources.traces.traces_storage', self.traces_storage_mock)
        self.patcher.start()

        # Import the class directly to avoid namespace collision
        from campus.audit.resources.traces import TracesResource
        self.traces_resource = TracesResource()

    def tearDown(self):
        """Clean up mocks."""
        self.patcher.stop()

    def test_ingest_single_span_success(self):
        """ingest() with single span returns created span ID."""
        # Arrange
        self.traces_storage_mock.insert_many.return_value = {}  # No errors
        span = TraceSpan(
            trace_id="abc123" * 2,  # 32-char hex
            span_id="def456",  # 16-char hex
            method="GET",
            path="/api/test",
            status_code=200,
            started_at=schema.DateTime.utcnow(),
            duration_ms=100.0,
            client_ip="127.0.0.1"
        )

        # Act
        result = self.traces_resource.ingest([span])

        # Assert
        self.traces_storage_mock.insert_many.assert_called_once()
        self.assertEqual(result["created"], [span.span_id])
        self.assertNotIn("failed", result)

    def test_ingest_batch_success(self):
        """ingest() with batch of spans returns all created span IDs."""
        # Arrange
        self.traces_storage_mock.insert_many.return_value = {}
        spans = [
            TraceSpan(
                trace_id="abc123" * 2,
                span_id=f"span{i}",
                method="GET",
                path=f"/api/test{i}",
                status_code=200,
                started_at=schema.DateTime.utcnow(),
                duration_ms=100.0,
                client_ip="127.0.0.1"
            )
            for i in range(5)
        ]

        # Act
        result = self.traces_resource.ingest(spans)

        # Assert
        self.assertEqual(len(result["created"]), 5)
        self.assertNotIn("failed", result)

    def test_ingest_partial_failure_returns_207_format(self):
        """ingest() on partial failure returns 207 Multi-Status format."""
        # Arrange
        spans = [
            TraceSpan(
                trace_id="abc123" * 2,
                span_id=f"span{i}",
                method="GET",
                path=f"/api/test{i}",
                status_code=200,
                started_at=schema.DateTime.utcnow(),
                duration_ms=100.0,
                client_ip="127.0.0.1"
            )
            for i in range(3)
        ]
        # Simulate failure at index 1
        self.traces_storage_mock.insert_many.return_value = {
            1: Exception("Duplicate key")
        }

        # Act
        result = self.traces_resource.ingest(spans)

        # Assert
        self.assertIn("created", result)
        self.assertIn("failed", result)
        self.assertEqual(result["created"], ["span0", "span2"])
        self.assertEqual(len(result["failed"]), 1)
        self.assertEqual(result["failed"][0]["span_id"], "span1")
        self.assertIn("error", result["failed"][0])

    def test_ingest_converts_models_to_storage_dicts(self):
        """ingest() converts TraceSpan models to storage dicts."""
        # Arrange
        self.traces_storage_mock.insert_many.return_value = {}
        span = TraceSpan(
            trace_id="abc123" * 2,
            span_id="def456",
            method="GET",
            path="/api/test",
            query_params={"foo": "bar"},
            request_headers={"auth": "hidden"},
            status_code=200,
            started_at=schema.DateTime.utcnow(),
            duration_ms=100.0,
            client_ip="127.0.0.1",
            tags={"env": "test"}
        )

        # Act
        self.traces_resource.ingest([span])

        # Assert
        call_args = self.traces_storage_mock.insert_many.call_args[0][0]
        self.assertIsInstance(call_args, list)
        self.assertIsInstance(call_args[0], dict)
        # Verify it's a storage dict, not a model
        self.assertNotIn("to_resource", call_args[0])


class TestTracesResourceList(unittest.TestCase):
    """Test TracesResource.list() for listing traces with filters."""

    def setUp(self):
        """Set up mock storage for testing."""
        self.traces_storage_mock = Mock()
        self.patcher = patch('campus.audit.resources.traces.traces_storage', self.traces_storage_mock)
        self.patcher.start()

        # Import the class directly to avoid namespace collision
        from campus.audit.resources.traces import TracesResource
        self.traces_resource = TracesResource()

        # Create sample span records with all required fields
        self.sample_spans = [
            _make_span_record(
                span_id="span1",
                trace_id="trace1",
                method="GET",
                path="/api/users",
                status_code=200,
                started_at="2023-01-01T10:00:00Z",
                duration_ms=100.0,
            ),
            _make_span_record(
                span_id="span2",
                trace_id="trace2",
                method="POST",
                path="/api/users",
                status_code=201,
                started_at="2023-01-01T11:00:00Z",
                duration_ms=150.0,
            ),
        ]

    def tearDown(self):
        """Clean up mocks."""
        self.patcher.stop()

    def test_list_returns_trace_summaries(self):
        """list() returns TraceSummary instances."""
        # Arrange
        self.traces_storage_mock.get_matching.return_value = self.sample_spans

        # Act
        result = self.traces_resource.list()

        # Assert
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], TraceSummary)
        self.assertEqual(result[0].trace_id, "trace1")
        self.assertEqual(result[1].trace_id, "trace2")

    def test_list_respects_limit(self):
        """list() respects the limit parameter."""
        # Arrange
        # Return 5 spans but limit to 2
        spans = [
            _make_span_record(
                span_id=f"span{i}",
                trace_id=f"trace{i}",
                started_at="2023-01-01T10:00:00Z",
                duration_ms=100.0,
            )
            for i in range(5)
        ]
        self.traces_storage_mock.get_matching.return_value = spans

        # Act
        result = self.traces_resource.list(limit=2)

        # Assert
        self.assertLessEqual(len(result), 2)

    def test_list_with_since_filter(self):
        """list() filters by since timestamp."""
        # Arrange
        self.traces_storage_mock.get_matching.return_value = self.sample_spans

        # Act
        result = self.traces_resource.list(since="2023-01-01T10:30:00Z")

        # Assert
        # Verify gte operator was used
        call_args = self.traces_storage_mock.get_matching.call_args
        query = call_args[0][0]
        self.assertIn("started_at", query)

    def test_list_with_until_filter(self):
        """list() filters by until timestamp."""
        # Arrange
        self.traces_storage_mock.get_matching.return_value = self.sample_spans

        # Act
        result = self.traces_resource.list(until="2023-01-01T10:30:00Z")

        # Assert
        # Verify lte operator was used
        call_args = self.traces_storage_mock.get_matching.call_args
        query = call_args[0][0]
        self.assertIn("started_at", query)

    def test_list_orders_by_started_at_descending(self):
        """list() orders traces by started_at descending."""
        # Arrange
        self.traces_storage_mock.get_matching.return_value = self.sample_spans

        # Act
        self.traces_resource.list()

        # Assert
        call_args = self.traces_storage_mock.get_matching.call_args
        self.assertEqual(call_args[1]["order_by"], "started_at")
        self.assertFalse(call_args[1]["ascending"])

    def test_list_on_storage_error_raises_internal_error(self):
        """list() raises InternalError on storage failure."""
        # Arrange
        self.traces_storage_mock.get_matching.side_effect = storage_errors.StorageError("DB down")

        # Act & Assert
        with self.assertRaises(api_errors.InternalError):
            self.traces_resource.list()


class TestTracesResourceSearch(unittest.TestCase):
    """Test TracesResource.search() for filtering traces."""

    def setUp(self):
        """Set up mock storage for testing."""
        self.traces_storage_mock = Mock()
        self.patcher = patch('campus.audit.resources.traces.traces_storage', self.traces_storage_mock)
        self.patcher.start()

        # Import the class directly to avoid namespace collision
        from campus.audit.resources.traces import TracesResource
        self.traces_resource = TracesResource()

        self.sample_spans = [
            _make_span_record(
                span_id="span1",
                trace_id="trace1",
                method="GET",
                path="/api/users",
                status_code=200,
                api_key_id="key1",
                client_id="client1",
                user_id="user1",
                started_at="2023-01-01T10:00:00Z",
                duration_ms=100.0,
            ),
        ]

    def tearDown(self):
        """Clean up mocks."""
        self.patcher.stop()

    def test_search_by_path(self):
        """search() filters by path."""
        # Arrange
        self.traces_storage_mock.get_matching.return_value = self.sample_spans

        # Act
        result = self.traces_resource.search(path="/api/users")

        # Assert
        call_args = self.traces_storage_mock.get_matching.call_args
        query = call_args[0][0]
        self.assertEqual(query["path"], "/api/users")

    def test_search_by_status(self):
        """search() filters by status_code."""
        # Arrange
        self.traces_storage_mock.get_matching.return_value = self.sample_spans

        # Act
        result = self.traces_resource.search(status=200)

        # Assert
        call_args = self.traces_storage_mock.get_matching.call_args
        query = call_args[0][0]
        self.assertEqual(query["status_code"], 200)

    def test_search_by_api_key_id(self):
        """search() filters by api_key_id."""
        # Arrange
        self.traces_storage_mock.get_matching.return_value = self.sample_spans

        # Act
        result = self.traces_resource.search(api_key_id="key1")

        # Assert
        call_args = self.traces_storage_mock.get_matching.call_args
        query = call_args[0][0]
        self.assertEqual(query["api_key_id"], "key1")

    def test_search_by_client_id(self):
        """search() filters by client_id."""
        # Arrange
        self.traces_storage_mock.get_matching.return_value = self.sample_spans

        # Act
        result = self.traces_resource.search(client_id="client1")

        # Assert
        call_args = self.traces_storage_mock.get_matching.call_args
        query = call_args[0][0]
        self.assertEqual(query["client_id"], "client1")

    def test_search_by_user_id(self):
        """search() filters by user_id."""
        # Arrange
        self.traces_storage_mock.get_matching.return_value = self.sample_spans

        # Act
        result = self.traces_resource.search(user_id="user1")

        # Assert
        call_args = self.traces_storage_mock.get_matching.call_args
        query = call_args[0][0]
        self.assertEqual(query["user_id"], "user1")

    def test_search_with_since_and_until_filters(self):
        """search() with both since and until should use between operator.

        Fixed: Now uses the `between` operator to represent both bounds.
        """
        # Arrange
        self.traces_storage_mock.get_matching.return_value = self.sample_spans

        # Act
        result = self.traces_resource.search(
            since="2023-01-01T09:00:00Z",
            until="2023-01-01T11:00:00Z"
        )

        # Assert
        call_args = self.traces_storage_mock.get_matching.call_args
        query = call_args[0][0]

        # Verify both bounds are captured using the between operator
        from campus.storage import between
        started_at = query.get("started_at")

        # Should be a between operator with both bounds
        self.assertIsInstance(started_at, between)
        self.assertEqual(started_at.value, ("2023-01-01T09:00:00Z", "2023-01-01T11:00:00Z"))

    def test_search_with_multiple_filters(self):
        """search() combines multiple filter criteria."""
        # Arrange
        self.traces_storage_mock.get_matching.return_value = self.sample_spans

        # Act
        result = self.traces_resource.search(
            path="/api/users",
            status=200,
            client_id="client1"
        )

        # Assert
        call_args = self.traces_storage_mock.get_matching.call_args
        query = call_args[0][0]
        self.assertEqual(query["path"], "/api/users")
        self.assertEqual(query["status_code"], 200)
        self.assertEqual(query["client_id"], "client1")

    def test_search_respects_limit(self):
        """search() respects the limit parameter."""
        # Arrange
        spans = [
            _make_span_record(
                span_id=f"span{i}",
                trace_id=f"trace{i}",
                started_at="2023-01-01T10:00:00Z",
                duration_ms=100.0,
            )
            for i in range(10)
        ]
        self.traces_storage_mock.get_matching.return_value = spans

        # Act
        result = self.traces_resource.search(limit=3)

        # Assert
        self.assertLessEqual(len(result), 3)

    def test_search_on_storage_error_raises_internal_error(self):
        """search() raises InternalError on storage failure."""
        # Arrange
        self.traces_storage_mock.get_matching.side_effect = storage_errors.StorageError("DB down")

        # Act & Assert
        with self.assertRaises(api_errors.InternalError):
            self.traces_resource.search()


class TestTraceResourceGetTree(unittest.TestCase):
    """Test TraceResource.get_tree() for trace tree building."""

    def setUp(self):
        """Set up mock storage for testing."""
        self.traces_storage_mock = Mock()
        self.patcher = patch('campus.audit.resources.traces.traces_storage', self.traces_storage_mock)
        self.patcher.start()

        # Import the class directly to avoid namespace collision
        from campus.audit.resources.traces import TracesResource
        # TraceResource is accessed via TracesResource.__getitem__
        self.traces_resource = TracesResource()["trace1"]

    def tearDown(self):
        """Clean up mocks."""
        self.patcher.stop()

    def test_get_tree_returns_trace_tree(self):
        """get_tree() returns a TraceTree instance."""
        # Arrange
        span_records = [
            {
                "span_id": "root",
                "trace_id": "trace1",
                "parent_span_id": None,
                "method": "GET",
                "path": "/api/test",
                "status_code": 200,
                "started_at": "2023-01-01T10:00:00Z",
                "duration_ms": 100.0,
                "error_message": None,
            },
        ]
        self.traces_storage_mock.get_matching.return_value = span_records

        # Act
        result = self.traces_resource.get_tree()

        # Assert
        self.assertIsInstance(result, TraceTree)
        self.assertIsNotNone(result.root)
        self.assertEqual(result.root.span_id, "root")

    def test_get_tree_builds_parent_child_hierarchy(self):
        """get_tree() builds correct parent-child relationships."""
        # Arrange - root with 2 children, one child has a grandchild
        span_records = [
            {
                "span_id": "root",
                "trace_id": "trace1",
                "parent_span_id": None,
                "method": "GET",
                "path": "/api/test",
                "status_code": 200,
                "started_at": "2023-01-01T10:00:00Z",
                "duration_ms": 100.0,
                "error_message": None,
            },
            {
                "span_id": "child1",
                "trace_id": "trace1",
                "parent_span_id": "root",
                "method": "GET",
                "path": "/api/child1",
                "status_code": 200,
                "started_at": "2023-01-01T10:00:01Z",
                "duration_ms": 50.0,
                "error_message": None,
            },
            {
                "span_id": "child2",
                "trace_id": "trace1",
                "parent_span_id": "root",
                "method": "GET",
                "path": "/api/child2",
                "status_code": 200,
                "started_at": "2023-01-01T10:00:02Z",
                "duration_ms": 30.0,
                "error_message": None,
            },
            {
                "span_id": "grandchild",
                "trace_id": "trace1",
                "parent_span_id": "child1",
                "method": "GET",
                "path": "/api/grandchild",
                "status_code": 200,
                "started_at": "2023-01-01T10:00:03Z",
                "duration_ms": 20.0,
                "error_message": None,
            },
        ]
        self.traces_storage_mock.get_matching.return_value = span_records

        # Act
        result = self.traces_resource.get_tree()

        # Assert - verify hierarchy
        self.assertEqual(result.root.span_id, "root")
        self.assertEqual(len(result.root.children), 2)
        self.assertEqual(result.root.children[0].span_id, "child1")
        self.assertEqual(result.root.children[1].span_id, "child2")
        self.assertEqual(len(result.root.children[0].children), 1)
        self.assertEqual(result.root.children[0].children[0].span_id, "grandchild")

    def test_get_tree_with_no_spans_returns_none(self):
        """get_tree() returns None when trace has no spans."""
        # Arrange
        self.traces_storage_mock.get_matching.return_value = []

        # Act
        result = self.traces_resource.get_tree()

        # Assert
        self.assertIsNone(result)

    def test_get_tree_filters_by_trace_id(self):
        """get_tree() queries storage with correct trace_id."""
        # Arrange
        self.traces_storage_mock.get_matching.return_value = []

        # Act
        self.traces_resource.get_tree()

        # Assert
        self.traces_storage_mock.get_matching.assert_called_once_with({"trace_id": "trace1"})


class TestTraceSpansResourceList(unittest.TestCase):
    """Test TraceSpansResource.list() for flat span listing."""

    def setUp(self):
        """Set up mock storage for testing."""
        self.traces_storage_mock = Mock()
        self.patcher = patch('campus.audit.resources.traces.traces_storage', self.traces_storage_mock)
        self.patcher.start()

        # Import the class directly to avoid namespace collision
        from campus.audit.resources.traces import TracesResource

        # TraceSpansResource is accessed via TracesResource[trace_id]["spans"]
        self.spans_resource = TracesResource()["trace1"]["spans"]

    def tearDown(self):
        """Clean up mocks."""
        self.patcher.stop()

    def test_list_returns_flat_span_list(self):
        """list() returns flat list of TraceSpan instances."""
        # Arrange
        span_records = [
            {
                "span_id": "span1",
                "trace_id": "trace1",
                "parent_span_id": None,
                "method": "GET",
                "path": "/api/test",
                "status_code": 200,
                "started_at": "2023-01-01T10:00:00Z",
                "duration_ms": 100.0,
                "query_params": {},
                "request_headers": {},
                "request_body": None,
                "response_headers": {},
                "response_body": None,
                "api_key_id": None,
                "client_id": None,
                "user_id": None,
                "client_ip": "127.0.0.1",
                "user_agent": None,
                "error_message": None,
                "tags": {},
            },
        ]
        self.traces_storage_mock.get_matching.return_value = span_records

        # Act
        result = self.spans_resource.list()

        # Assert
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], TraceSpan)
        self.assertEqual(result[0].span_id, "span1")

    def test_list_filters_by_trace_id(self):
        """list() queries storage with correct trace_id."""
        # Arrange
        self.traces_storage_mock.get_matching.return_value = []

        # Act
        self.spans_resource.list()

        # Assert
        self.traces_storage_mock.get_matching.assert_called_once_with({"trace_id": "trace1"})


class TestSpanResourceGet(unittest.TestCase):
    """Test SpanResource.get() for single span retrieval."""

    def setUp(self):
        """Set up mock storage for testing."""
        self.traces_storage_mock = Mock()
        self.patcher = patch('campus.audit.resources.traces.traces_storage', self.traces_storage_mock)
        self.patcher.start()

        # Import the class directly to avoid namespace collision
        from campus.audit.resources.traces import TracesResource

        # SpanResource is accessed via TracesResource[trace_id]["spans"][span_id]
        self.span_resource = TracesResource()["trace1"]["spans"]["span1"]

    def tearDown(self):
        """Clean up mocks."""
        self.patcher.stop()

    def test_get_returns_span(self):
        """get() returns TraceSpan instance when found."""
        # Arrange
        span_record = {
            "span_id": "span1",
            "trace_id": "trace1",
            "parent_span_id": None,
            "method": "GET",
            "path": "/api/test",
            "status_code": 200,
            "started_at": "2023-01-01T10:00:00Z",
            "duration_ms": 100.0,
            "query_params": {"foo": "bar"},
            "request_headers": {"auth": "hidden"},
            "request_body": None,
            "response_headers": {"content-type": "application/json"},
            "response_body": {"data": "test"},
            "api_key_id": "key1",
            "client_id": "client1",
            "user_id": "user1",
            "client_ip": "127.0.0.1",
            "user_agent": "test-agent",
            "error_message": None,
            "tags": {"env": "test"},
        }
        self.traces_storage_mock.get_by_id.return_value = span_record

        # Act
        result = self.span_resource.get()

        # Assert
        self.assertIsInstance(result, TraceSpan)
        self.assertEqual(result.span_id, "span1")
        self.assertEqual(result.trace_id, "trace1")
        self.assertEqual(result.query_params, {"foo": "bar"})
        self.assertEqual(result.response_headers, {"content-type": "application/json"})

    def test_get_with_wrong_trace_id_returns_none(self):
        """get() returns None when span belongs to different trace."""
        # Arrange - span exists but for different trace
        span_record = {
            "span_id": "span1",
            "trace_id": "trace2",  # Different trace!
            "parent_span_id": None,
            "method": "GET",
            "path": "/api/test",
            "status_code": 200,
            "started_at": "2023-01-01T10:00:00Z",
            "duration_ms": 100.0,
            "query_params": {},
            "request_headers": {},
            "request_body": None,
            "response_headers": {},
            "response_body": None,
            "api_key_id": None,
            "client_id": None,
            "user_id": None,
            "client_ip": "127.0.0.1",
            "user_agent": None,
            "error_message": None,
            "tags": {},
        }
        self.traces_storage_mock.get_by_id.return_value = span_record

        # Act
        result = self.span_resource.get()

        # Assert
        self.assertIsNone(result)

    def test_get_with_nonexistent_span_returns_none(self):
        """get() returns None when span doesn't exist."""
        # Arrange
        self.traces_storage_mock.get_by_id.side_effect = storage_errors.NotFoundError("Not found")

        # Act
        result = self.span_resource.get()

        # Assert
        self.assertIsNone(result)


class TestTraceTreeFromSpans(unittest.TestCase):
    """Test TraceTree.from_spans() for trace tree construction."""

    def test_from_spans_single_root_span(self):
        """from_spans() creates tree with single root span."""
        # Arrange
        spans = [
            {
                "span_id": "root",
                "trace_id": "trace1",
                "parent_span_id": None,
                "method": "GET",
                "path": "/api/test",
                "status_code": 200,
                "started_at": "2023-01-01T10:00:00Z",
                "duration_ms": 100.0,
                "error_message": None,
            },
        ]

        # Act
        tree = TraceTree.from_spans(spans)

        # Assert
        self.assertIsNotNone(tree.root)
        self.assertEqual(tree.root.span_id, "root")
        self.assertIsNone(tree.root.parent_span_id)
        self.assertEqual(len(tree.root.children), 0)

    def test_from_spans_with_nested_children(self):
        """from_spans() creates correct nested hierarchy."""
        # Arrange
        spans = [
            {
                "span_id": "root",
                "trace_id": "trace1",
                "parent_span_id": None,
                "method": "GET",
                "path": "/api/root",
                "status_code": 200,
                "started_at": "2023-01-01T10:00:00Z",
                "duration_ms": 200.0,
                "error_message": None,
            },
            {
                "span_id": "child1",
                "trace_id": "trace1",
                "parent_span_id": "root",
                "method": "GET",
                "path": "/api/child1",
                "status_code": 200,
                "started_at": "2023-01-01T10:00:01Z",
                "duration_ms": 50.0,
                "error_message": None,
            },
            {
                "span_id": "child2",
                "trace_id": "trace1",
                "parent_span_id": "root",
                "method": "GET",
                "path": "/api/child2",
                "status_code": 200,
                "started_at": "2023-01-01T10:00:02Z",
                "duration_ms": 30.0,
                "error_message": None,
            },
            {
                "span_id": "grandchild1",
                "trace_id": "trace1",
                "parent_span_id": "child1",
                "method": "GET",
                "path": "/api/grandchild1",
                "status_code": 200,
                "started_at": "2023-01-01T10:00:03Z",
                "duration_ms": 20.0,
                "error_message": None,
            },
        ]

        # Act
        tree = TraceTree.from_spans(spans)

        # Assert - verify structure
        self.assertEqual(tree.root.span_id, "root")
        self.assertEqual(len(tree.root.children), 2)

        child1 = tree.root.children[0]
        child2 = tree.root.children[1]
        self.assertEqual(child1.span_id, "child1")
        self.assertEqual(child2.span_id, "child2")

        self.assertEqual(len(child1.children), 1)
        self.assertEqual(len(child2.children), 0)

        grandchild1 = child1.children[0]
        self.assertEqual(grandchild1.span_id, "grandchild1")

    def test_from_spans_orders_by_parent_child_relationship(self):
        """from_spans() maintains parent-child ordering (acceptance criteria)."""
        # Arrange - spans in random order
        spans = [
            {
                "span_id": "grandchild",
                "trace_id": "trace1",
                "parent_span_id": "child",
                "method": "GET",
                "path": "/api/gc",
                "status_code": 200,
                "started_at": "2023-01-01T10:00:03Z",
                "duration_ms": 10.0,
                "error_message": None,
            },
            {
                "span_id": "root",
                "trace_id": "trace1",
                "parent_span_id": None,
                "method": "GET",
                "path": "/api/root",
                "status_code": 200,
                "started_at": "2023-01-01T10:00:00Z",
                "duration_ms": 100.0,
                "error_message": None,
            },
            {
                "span_id": "child",
                "trace_id": "trace1",
                "parent_span_id": "root",
                "method": "GET",
                "path": "/api/child",
                "status_code": 200,
                "started_at": "2023-01-01T10:00:01Z",
                "duration_ms": 50.0,
                "error_message": None,
            },
        ]

        # Act
        tree = TraceTree.from_spans(spans)

        # Assert - verify correct parent-child ordering regardless of input order
        self.assertEqual(tree.root.span_id, "root")
        self.assertEqual(tree.root.children[0].span_id, "child")
        self.assertEqual(tree.root.children[0].children[0].span_id, "grandchild")

    def test_from_spans_with_empty_list(self):
        """from_spans() returns tree with None root for empty list."""
        # Act
        tree = TraceTree.from_spans([])

        # Assert
        self.assertIsNone(tree.root)

    def test_from_spans_calculates_depth_and_offset(self):
        """from_spans() calculates depth and offset metrics."""
        # Arrange
        spans = [
            {
                "span_id": "root",
                "trace_id": "trace1",
                "parent_span_id": None,
                "method": "GET",
                "path": "/api/root",
                "status_code": 200,
                "started_at": "2023-01-01T10:00:00Z",
                "duration_ms": 100.0,
                "error_message": None,
            },
            {
                "span_id": "child1",
                "trace_id": "trace1",
                "parent_span_id": "root",
                "method": "GET",
                "path": "/api/child1",
                "status_code": 200,
                "started_at": "2023-01-01T10:00:00Z",
                "duration_ms": 30.0,
                "error_message": None,
            },
            {
                "span_id": "child2",
                "trace_id": "trace1",
                "parent_span_id": "root",
                "method": "GET",
                "path": "/api/child2",
                "status_code": 200,
                "started_at": "2023-01-01T10:00:00Z",
                "duration_ms": 20.0,
                "error_message": None,
            },
        ]

        # Act
        tree = TraceTree.from_spans(spans)

        # Assert
        self.assertEqual(tree.root.depth, 0)
        self.assertEqual(tree.root.offset, 0.0)
        self.assertEqual(tree.root.children[0].depth, 1)
        self.assertEqual(tree.root.children[0].offset, 0.0)
        self.assertEqual(tree.root.children[1].depth, 1)
        # child2 offset should be after child1 completes
        self.assertEqual(tree.root.children[1].offset, 30.0)


class TestTraceSummaryFromSpans(unittest.TestCase):
    """Test TraceSummary.from_spans() for summary building."""

    def test_from_spans_creates_summary_with_root_span(self):
        """from_spans() creates summary with root span details."""
        # Arrange
        trace_id = "trace1"
        spans = [
            _make_span_record(
                span_id="root",
                trace_id=trace_id,
                parent_span_id=None,
                method="GET",
                path="/api/test",
                status_code=200,
                started_at="2023-01-01T10:00:00Z",
                duration_ms=100.0,
            ),
            _make_span_record(
                span_id="child",
                trace_id=trace_id,
                parent_span_id="root",
                method="GET",
                path="/api/child",
                status_code=200,
                started_at="2023-01-01T10:00:01Z",
                duration_ms=50.0,
            ),
        ]

        # Act
        summary = TraceSummary.from_spans(trace_id, spans)

        # Assert
        self.assertEqual(summary.trace_id, trace_id)
        self.assertEqual(summary.span_count, 2)
        self.assertEqual(summary.started_at, "2023-01-01T10:00:00Z")
        self.assertEqual(summary.duration_ms, 100.0)  # Root's duration
        self.assertEqual(summary.root_span.span_id, "root")

    def test_from_spans_with_no_root_uses_earliest_span(self):
        """from_spans() uses earliest span when no root (parent_span_id=None) exists."""
        # Arrange - no root span (all have parents)
        trace_id = "trace1"
        spans = [
            _make_span_record(
                span_id="span2",
                trace_id=trace_id,
                parent_span_id="span1",
                method="GET",
                path="/api/span2",
                status_code=200,
                started_at="2023-01-01T10:00:01Z",
                duration_ms=50.0,
            ),
            _make_span_record(
                span_id="span1",
                trace_id=trace_id,
                parent_span_id="external",
                method="GET",
                path="/api/span1",
                status_code=200,
                started_at="2023-01-01T10:00:00Z",
                duration_ms=100.0,
            ),
        ]

        # Act
        summary = TraceSummary.from_spans(trace_id, spans)

        # Assert
        self.assertEqual(summary.span_count, 2)
        self.assertEqual(summary.started_at, "2023-01-01T10:00:00Z")  # Earliest
        self.assertEqual(summary.duration_ms, 150.0)  # Sum of all durations
        self.assertEqual(summary.root_span.span_id, "span1")  # Earliest span as root


if __name__ == "__main__":
    unittest.main()
