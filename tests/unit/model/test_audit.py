"""Pure unit tests for campus.model.audit module.

These tests verify the business logic in audit models without any mocks or
external dependencies. All tests use pure functions and stateless computations.

Test coverage:
- TraceSpan: dataclass initialization, __post_init__, serialization
- TraceTreeNode: tree structure, to_resource(), depth/offset metrics
- TraceTree: from_spans() tree building algorithm, _build_node() recursion
- TraceSummary: from_spans() summary computation, root span logic
- APIKey: serialization, field filtering (key_hash excluded),
  lifecycle helpers (is_active/is_expired/is_revoked), has_scope(),
  validate_update()
"""

import unittest

from campus.common import schema
from campus.model.audit import (
    APIKey,
    TraceSpan,
    TraceSummary,
    TraceTree,
    TraceTreeNode,
)


class TestTraceSpan(unittest.TestCase):
    """Test TraceSpan model pure methods."""

    def test_tracespan_initialization_with_all_fields(self):
        """TraceSpan initializes with all required fields."""
        span = TraceSpan(
            trace_id="a" * 32,
            span_id="b" * 16,
            parent_span_id=None,
            method="GET",
            path="/api/test",
            status_code=200,
            started_at=schema.DateTime.utcnow(),
            duration_ms=100.0,
            client_ip="127.0.0.1",
        )

        self.assertEqual(span.trace_id, "a" * 32)
        self.assertEqual(span.span_id, "b" * 16)
        self.assertIsNone(span.parent_span_id)
        self.assertEqual(span.method, "GET")
        self.assertEqual(span.path, "/api/test")
        self.assertEqual(span.status_code, 200)
        self.assertEqual(span.duration_ms, 100.0)
        self.assertEqual(span.client_ip, "127.0.0.1")

    def test_tracespan_post_init_aliases_id_to_span_id(self):
        """__post_init__() sets id field equal to span_id."""
        span = TraceSpan(
            trace_id="a" * 32,
            span_id="myspan123",
            method="GET",
            path="/api/test",
            status_code=200,
            started_at=schema.DateTime.utcnow(),
            duration_ms=100.0,
            client_ip="127.0.0.1",
        )

        self.assertEqual(span.id, "myspan123")
        self.assertEqual(span.span_id, "myspan123")

    def test_tracespan_defaults_to_empty_dicts(self):
        """TraceSpan uses empty dict defaults for query_params, headers, tags."""
        span = TraceSpan(
            trace_id="a" * 32,
            span_id="b" * 16,
            method="GET",
            path="/api/test",
            status_code=200,
            started_at=schema.DateTime.utcnow(),
            duration_ms=100.0,
            client_ip="127.0.0.1",
        )

        self.assertEqual(span.query_params, {})
        self.assertEqual(span.request_headers, {})
        self.assertEqual(span.response_headers, {})
        self.assertEqual(span.tags, {})

    def test_tracespan_to_resource_serialization(self):
        """to_resource() converts TraceSpan to resource dict."""
        span = TraceSpan(
            trace_id="trace123",
            span_id="span456",
            parent_span_id="parent789",
            method="POST",
            path="/api/users",
            query_params={"page": "1"},
            request_headers={"auth": "bearer"},
            request_body={"name": "test"},
            status_code=201,
            started_at="2023-01-01T10:00:00Z",
            duration_ms=150.5,
            response_headers={"content-type": "application/json"},
            response_body={"id": 123},
            client_ip="10.0.0.1",
            user_agent="test-agent",
            error_message=None,
            tags={"env": "test"},
        )

        resource = span.to_resource()

        self.assertEqual(resource["trace_id"], "trace123")
        self.assertEqual(resource["span_id"], "span456")
        self.assertEqual(resource["parent_span_id"], "parent789")
        self.assertEqual(resource["method"], "POST")
        self.assertEqual(resource["path"], "/api/users")
        self.assertEqual(resource["status_code"], 201)
        self.assertEqual(resource["duration_ms"], 150.5)

    def test_tracespan_from_storage_deserialization(self):
        """from_storage() creates TraceSpan from storage dict."""
        record = {
            "id": "span123",
            "trace_id": "trace456",
            "span_id": "span123",
            "parent_span_id": None,
            "method": "GET",
            "path": "/api/test",
            "query_params": {},
            "request_headers": {},
            "request_body": None,
            "status_code": 200,
            "response_headers": {},
            "response_body": None,
            "started_at": "2023-01-01T10:00:00Z",
            "duration_ms": 100.0,
            "api_key_id": None,
            "client_id": None,
            "user_id": None,
            "client_ip": "127.0.0.1",
            "user_agent": None,
            "error_message": None,
            "tags": {},
        }

        span = TraceSpan.from_storage(record)

        self.assertEqual(span.span_id, "span123")
        self.assertEqual(span.trace_id, "trace456")
        self.assertEqual(span.method, "GET")
        self.assertEqual(span.path, "/api/test")

    def test_tracespan_to_storage_serialization(self):
        """to_storage() converts TraceSpan to storage dict."""
        span = TraceSpan(
            trace_id="trace123",
            span_id="span456",
            method="GET",
            path="/api/test",
            status_code=200,
            started_at="2023-01-01T10:00:00Z",
            duration_ms=100.0,
            client_ip="127.0.0.1",
        )

        storage = span.to_storage()

        self.assertEqual(storage["trace_id"], "trace123")
        self.assertEqual(storage["span_id"], "span456")
        self.assertEqual(storage["method"], "GET")
        self.assertEqual(storage["path"], "/api/test")


class TestTraceTreeNode(unittest.TestCase):
    """Test TraceTreeNode model pure methods."""

    def _make_node(self, **kwargs):
        """Helper to create a TraceTreeNode with default values."""
        defaults = {
            "span_id": "span1",
            "trace_id": "trace1",
            "parent_span_id": None,
            "method": "GET",
            "path": "/api/test",
            "status_code": 200,
            "started_at": "2023-01-01T10:00:00Z",
            "duration_ms": 100.0,
            "error_message": None,
            "children": [],
            "depth": 0,
            "offset": 0.0,
        }
        defaults.update(kwargs)
        return TraceTreeNode(**defaults)

    def test_treenode_initialization(self):
        """TraceTreeNode initializes with all fields."""
        node = self._make_node(
            span_id="span123",
            depth=2,
            offset=50.0,
        )

        self.assertEqual(node.span_id, "span123")
        self.assertEqual(node.depth, 2)
        self.assertEqual(node.offset, 50.0)

    def test_treenode_to_resource_serializes_fields(self):
        """to_resource() converts node to resource dict."""
        node = self._make_node(
            span_id="root",
            trace_id="trace1",
            method="GET",
            path="/api/test",
            status_code=200,
            started_at="2023-01-01T10:00:00Z",
            duration_ms=100.0,
            error_message=None,
            depth=1,
            offset=25.5,
        )

        resource = node.to_resource()

        self.assertEqual(resource["span_id"], "root")
        self.assertEqual(resource["trace_id"], "trace1")
        self.assertEqual(resource["method"], "GET")
        self.assertEqual(resource["depth"], 1)
        self.assertEqual(resource["offset"], 25.5)

    def test_treenode_to_resource_nests_children(self):
        """to_resource() recursively serializes children."""
        child = self._make_node(span_id="child1")
        parent = self._make_node(span_id="root", children=[child])

        resource = parent.to_resource()

        self.assertEqual(resource["span_id"], "root")
        self.assertEqual(len(resource["children"]), 1)
        self.assertEqual(resource["children"][0]["span_id"], "child1")

    def test_treenode_to_resource_with_multiple_children(self):
        """to_resource() handles multiple children."""
        child1 = self._make_node(span_id="child1")
        child2 = self._make_node(span_id="child2")
        parent = self._make_node(span_id="root", children=[child1, child2])

        resource = parent.to_resource()

        self.assertEqual(len(resource["children"]), 2)
        self.assertEqual(resource["children"][0]["span_id"], "child1")
        self.assertEqual(resource["children"][1]["span_id"], "child2")

    def test_treenode_to_resource_deep_nesting(self):
        """to_resource() handles deeply nested children."""
        grandchild = self._make_node(span_id="grandchild")
        child = self._make_node(span_id="child", children=[grandchild])
        parent = self._make_node(span_id="root", children=[child])

        resource = parent.to_resource()

        self.assertEqual(resource["children"][0]["span_id"], "child")
        self.assertEqual(resource["children"][0]["children"][0]["span_id"], "grandchild")


class TestTraceTree(unittest.TestCase):
    """Test TraceTree model pure methods."""

    def _make_span_dict(self, **kwargs):
        """Helper to create a span dict for testing."""
        defaults = {
            "span_id": "span1",
            "trace_id": "trace1",
            "parent_span_id": None,
            "method": "GET",
            "path": "/api/test",
            "status_code": 200,
            "started_at": "2023-01-01T10:00:00Z",
            "duration_ms": 100.0,
            "error_message": None,
        }
        defaults.update(kwargs)
        return defaults

    def test_treetree_from_spans_empty_returns_none_root(self):
        """from_spans() with empty list returns tree with None root."""
        tree = TraceTree.from_spans([])

        self.assertIsNone(tree.root)

    def test_treetree_from_spans_single_span_becomes_root(self):
        """from_spans() with single span creates root with no children."""
        spans = [self._make_span_dict(span_id="root", parent_span_id=None)]

        tree = TraceTree.from_spans(spans)

        self.assertIsNotNone(tree.root)
        self.assertEqual(tree.root.span_id, "root")
        self.assertIsNone(tree.root.parent_span_id)
        self.assertEqual(len(tree.root.children), 0)

    def test_treetree_from_spans_builds_parent_child_hierarchy(self):
        """from_spans() builds correct parent-child relationships."""
        spans = [
            self._make_span_dict(span_id="root", parent_span_id=None),
            self._make_span_dict(span_id="child1", parent_span_id="root"),
            self._make_span_dict(span_id="child2", parent_span_id="root"),
        ]

        tree = TraceTree.from_spans(spans)

        self.assertEqual(tree.root.span_id, "root")
        self.assertEqual(len(tree.root.children), 2)
        self.assertEqual(tree.root.children[0].span_id, "child1")
        self.assertEqual(tree.root.children[1].span_id, "child2")

    def test_treetree_from_spans_builds_grandchild_hierarchy(self):
        """from_spans() builds multi-level hierarchy."""
        spans = [
            self._make_span_dict(span_id="root", parent_span_id=None, duration_ms=100),
            self._make_span_dict(span_id="child1", parent_span_id="root", duration_ms=50),
            self._make_span_dict(span_id="child2", parent_span_id="root", duration_ms=30),
            self._make_span_dict(span_id="grandchild", parent_span_id="child1", duration_ms=20),
        ]

        tree = TraceTree.from_spans(spans)

        self.assertEqual(tree.root.span_id, "root")
        self.assertEqual(len(tree.root.children), 2)

        child1 = tree.root.children[0]
        child2 = tree.root.children[1]
        self.assertEqual(child1.span_id, "child1")
        self.assertEqual(child2.span_id, "child2")

        self.assertEqual(len(child1.children), 1)
        self.assertEqual(child1.children[0].span_id, "grandchild")
        self.assertEqual(len(child2.children), 0)

    def test_treetree_from_spans_orphaned_spans_adopted_under_root(self):
        """from_spans() adopts spans with non-existent parents under the root.

        Orphaned spans (parent not ingested) must stay visible in the
        waterfall rather than being dropped (#794).
        """
        spans = [
            self._make_span_dict(span_id="root", parent_span_id=None),
            self._make_span_dict(
                span_id="child", parent_span_id="root",
                started_at="2023-01-01T10:00:00.050Z",
            ),
            self._make_span_dict(
                span_id="orphan", parent_span_id="nonexistent",
                started_at="2023-01-01T10:00:00.100Z",
            ),
        ]

        tree = TraceTree.from_spans(spans)

        # Orphan is adopted under the root, after the real child
        self.assertEqual(len(tree.root.children), 2)
        self.assertEqual(tree.root.children[0].span_id, "child")
        self.assertEqual(tree.root.children[1].span_id, "orphan")
        # The adopted span's parent link is normalized to the root
        self.assertIsNone(tree.root.children[1].parent_span_id)

    def test_treetree_from_spans_multiple_roots_earliest_becomes_root(self):
        """from_spans() picks the earliest root; other roots hang under it."""
        spans = [
            self._make_span_dict(
                span_id="root-later", parent_span_id=None,
                started_at="2023-01-01T10:00:01.000Z",
            ),
            self._make_span_dict(
                span_id="root-earliest", parent_span_id=None,
                started_at="2023-01-01T10:00:00.000Z",
            ),
        ]

        tree = TraceTree.from_spans(spans)

        self.assertEqual(tree.root.span_id, "root-earliest")
        self.assertEqual(len(tree.root.children), 1)
        self.assertEqual(tree.root.children[0].span_id, "root-later")

    def test_treetree_from_spans_children_sorted_by_start_time(self):
        """Children are ordered by started_at regardless of input order."""
        spans = [
            self._make_span_dict(span_id="root", parent_span_id=None),
            self._make_span_dict(
                span_id="late", parent_span_id="root",
                started_at="2023-01-01T10:00:00.200Z",
            ),
            self._make_span_dict(
                span_id="early", parent_span_id="root",
                started_at="2023-01-01T10:00:00.050Z",
            ),
        ]

        tree = TraceTree.from_spans(spans)

        self.assertEqual(
            [c.span_id for c in tree.root.children], ["early", "late"]
        )

    def test_treetree_from_spans_unordered_input(self):
        """from_spans() works regardless of input order."""
        spans = [
            self._make_span_dict(span_id="grandchild", parent_span_id="child"),
            self._make_span_dict(span_id="child", parent_span_id="root"),
            self._make_span_dict(span_id="root", parent_span_id=None),
        ]

        tree = TraceTree.from_spans(spans)

        self.assertEqual(tree.root.span_id, "root")
        self.assertEqual(tree.root.children[0].span_id, "child")
        self.assertEqual(tree.root.children[0].children[0].span_id, "grandchild")

    def test_treetree_build_node_calculates_depth_recursively(self):
        """_build_node() correctly calculates depth for nested nodes."""
        spans = [
            self._make_span_dict(span_id="root", parent_span_id=None),
            self._make_span_dict(span_id="child", parent_span_id="root"),
            self._make_span_dict(span_id="grandchild", parent_span_id="child"),
        ]

        tree = TraceTree.from_spans(spans)

        self.assertEqual(tree.root.depth, 0)
        self.assertEqual(tree.root.children[0].depth, 1)
        self.assertEqual(tree.root.children[0].children[0].depth, 2)

    def test_treetree_build_node_calculates_offset_from_timestamps(self):
        """_build_node() derives each child's offset from started_at (#794)."""
        spans = [
            self._make_span_dict(
                span_id="root", parent_span_id=None,
                started_at="2023-01-01T10:00:00.000Z",
            ),
            self._make_span_dict(
                span_id="child1", parent_span_id="root",
                started_at="2023-01-01T10:00:00.030Z",
            ),
            self._make_span_dict(
                span_id="child2", parent_span_id="root",
                started_at="2023-01-01T10:00:00.050Z",
            ),
        ]

        tree = TraceTree.from_spans(spans)

        # Offsets are real start deltas from the parent, not cumulative
        # sibling durations
        self.assertEqual(tree.root.offset, 0.0)
        self.assertEqual(tree.root.children[0].offset, 30.0)
        self.assertEqual(tree.root.children[1].offset, 50.0)

    def test_treetree_build_node_offset_nested_child_relative_to_parent(self):
        """A grandchild's offset is relative to its own parent's start."""
        spans = [
            self._make_span_dict(
                span_id="root", parent_span_id=None,
                started_at="2023-01-01T10:00:00.000Z",
            ),
            self._make_span_dict(
                span_id="child", parent_span_id="root",
                started_at="2023-01-01T10:00:00.020Z",
            ),
            self._make_span_dict(
                span_id="grandchild", parent_span_id="child",
                started_at="2023-01-01T10:00:00.045Z",
            ),
        ]

        tree = TraceTree.from_spans(spans)

        self.assertEqual(tree.root.children[0].offset, 20.0)
        self.assertEqual(
            tree.root.children[0].children[0].offset, 25.0
        )

    def test_treetree_build_node_clamps_negative_offsets(self):
        """A child with a skewed clock (start before parent) gets offset 0."""
        spans = [
            self._make_span_dict(
                span_id="root", parent_span_id=None,
                started_at="2023-01-01T10:00:00.100Z",
            ),
            self._make_span_dict(
                span_id="child", parent_span_id="root",
                started_at="2023-01-01T10:00:00.050Z",
            ),
        ]

        tree = TraceTree.from_spans(spans)

        self.assertEqual(tree.root.children[0].offset, 0.0)

    def test_treetree_to_resource_with_root(self):
        """to_resource() returns root's resource dict."""
        spans = [self._make_span_dict(span_id="root", parent_span_id=None)]
        tree = TraceTree.from_spans(spans)

        resource = tree.to_resource()

        self.assertEqual(resource["span_id"], "root")
        self.assertIn("children", resource)

    def test_treetree_to_resource_without_root(self):
        """to_resource() returns empty dict when root is None."""
        tree = TraceTree.from_spans([])

        resource = tree.to_resource()

        self.assertEqual(resource, {})

    def test_treetree_from_storage_raises_not_implemented(self):
        """from_storage() raises NotImplementedError."""
        with self.assertRaises(NotImplementedError) as cm:
            TraceTree.from_storage({})

        self.assertIn("computed from spans", str(cm.exception))

    def test_treetree_to_storage_raises_not_implemented(self):
        """to_storage() raises NotImplementedError."""
        tree = TraceTree(root=None)

        with self.assertRaises(NotImplementedError) as cm:
            tree.to_storage()

        self.assertIn("cannot be stored", str(cm.exception))

    def test_treetree_from_resource_raises_not_implemented(self):
        """from_resource() raises NotImplementedError."""
        with self.assertRaises(NotImplementedError) as cm:
            TraceTree.from_resource({})

        self.assertIn("computed from spans", str(cm.exception))


class TestTraceSummary(unittest.TestCase):
    """Test TraceSummary model pure methods."""

    def _make_span_dict(self, **kwargs):
        """Helper to create a span dict for testing."""
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
        defaults.update(kwargs)
        return defaults

    def test_tracesummary_from_spans_finds_root_span(self):
        """from_spans() identifies root span (parent_span_id is None)."""
        trace_id = "trace1"
        spans = [
            self._make_span_dict(
                span_id="root",
                parent_span_id=None,
                duration_ms=100.0,
            ),
            self._make_span_dict(
                span_id="child",
                parent_span_id="root",
                duration_ms=50.0,
            ),
        ]

        summary = TraceSummary.from_spans(trace_id, spans)

        self.assertEqual(summary.trace_id, trace_id)
        self.assertEqual(summary.span_count, 2)
        self.assertEqual(summary.root_span.span_id, "root")
        self.assertEqual(summary.duration_ms, 100.0)  # Root's duration

    def test_tracesummary_from_spans_no_root_uses_earliest_span(self):
        """from_spans() uses earliest span when no root exists."""
        trace_id = "trace1"
        spans = [
            self._make_span_dict(
                span_id="span2",
                parent_span_id="external",
                started_at="2023-01-01T10:00:01Z",
                duration_ms=50.0,
            ),
            self._make_span_dict(
                span_id="span1",
                parent_span_id="external",
                started_at="2023-01-01T10:00:00Z",
                duration_ms=100.0,
            ),
        ]

        summary = TraceSummary.from_spans(trace_id, spans)

        # Should use earliest span (span1)
        self.assertEqual(summary.root_span.span_id, "span1")
        self.assertEqual(summary.started_at, "2023-01-01T10:00:00Z")
        # Should sum all durations when no root
        self.assertEqual(summary.duration_ms, 150.0)

    def test_tracesummary_from_spans_counts_spans(self):
        """from_spans() correctly counts total spans."""
        trace_id = "trace1"
        spans = [
            self._make_span_dict(span_id=f"span{i}")
            for i in range(5)
        ]

        summary = TraceSummary.from_spans(trace_id, spans)

        self.assertEqual(summary.span_count, 5)

    def test_tracesummary_from_spans_uses_root_duration(self):
        """from_spans() uses root span's duration, not sum."""
        trace_id = "trace1"
        spans = [
            self._make_span_dict(
                span_id="root",
                parent_span_id=None,
                duration_ms=200.0,
            ),
            self._make_span_dict(
                span_id="child1",
                parent_span_id="root",
                duration_ms=50.0,
            ),
            self._make_span_dict(
                span_id="child2",
                parent_span_id="root",
                duration_ms=75.0,
            ),
        ]

        summary = TraceSummary.from_spans(trace_id, spans)

        # Should use root's duration (200), not sum (325)
        self.assertEqual(summary.duration_ms, 200.0)

    def test_tracesummary_from_spans_sums_duration_when_no_root(self):
        """from_spans() sums all durations when no root span exists."""
        trace_id = "trace1"
        spans = [
            self._make_span_dict(span_id="span1", parent_span_id="external", duration_ms=100),
            self._make_span_dict(span_id="span2", parent_span_id="external", duration_ms=50),
            self._make_span_dict(span_id="span3", parent_span_id="external", duration_ms=25),
        ]

        summary = TraceSummary.from_spans(trace_id, spans)

        # Should sum all durations
        self.assertEqual(summary.duration_ms, 175.0)

    def test_tracesummary_to_resource_serialization(self):
        """to_resource() converts summary to resource dict."""
        from campus.model.audit import TraceSpan

        trace_id = "trace1"
        root_span = TraceSpan(
            trace_id=trace_id,
            span_id="root",
            method="GET",
            path="/api/test",
            status_code=200,
            started_at="2023-01-01T10:00:00Z",
            duration_ms=100.0,
            client_ip="127.0.0.1",
        )

        summary = TraceSummary(
            trace_id=trace_id,
            span_count=1,
            started_at="2023-01-01T10:00:00Z",
            duration_ms=100.0,
            root_span=root_span,
        )

        resource = summary.to_resource()

        self.assertEqual(resource["trace_id"], trace_id)
        self.assertEqual(resource["span_count"], 1)
        self.assertEqual(resource["duration_ms"], 100.0)
        self.assertIn("root_span", resource)
        self.assertEqual(resource["root_span"]["span_id"], "root")

    def test_tracesummary_from_storage_raises_not_implemented(self):
        """from_storage() raises NotImplementedError."""
        with self.assertRaises(NotImplementedError) as cm:
            TraceSummary.from_storage({})

        self.assertIn("computed from spans", str(cm.exception))

    def test_tracesummary_to_storage_raises_not_implemented(self):
        """to_storage() raises NotImplementedError."""
        summary = TraceSummary(
            trace_id="trace1",
            span_count=1,
            started_at="2023-01-01T10:00:00Z",
            duration_ms=100.0,
            root_span=None,
        )

        with self.assertRaises(NotImplementedError) as cm:
            summary.to_storage()

        self.assertIn("cannot be stored", str(cm.exception))

    def test_tracesummary_from_resource_raises_not_implemented(self):
        """from_resource() raises NotImplementedError."""
        with self.assertRaises(NotImplementedError) as cm:
            TraceSummary.from_resource({})

        self.assertIn("computed from spans", str(cm.exception))


class TestAPIKey(unittest.TestCase):
    """Test APIKey model pure methods."""

    def test_apikey_initialization_with_required_fields(self):
        """APIKey initializes with required fields."""
        key = APIKey(
            id="key123",
            key_hash="hash123",
            name="Test Key",
            owner_id="user456",
        )

        self.assertEqual(key.id, "key123")
        self.assertEqual(key.key_hash, "hash123")
        self.assertEqual(key.name, "Test Key")
        self.assertEqual(key.owner_id, "user456")

    def test_apikey_initialization_with_optional_fields(self):
        """APIKey initializes with optional fields."""
        key = APIKey(
            id="key123",
            key_hash="hash123",
            name="Test Key",
            owner_id="user456",
            scopes=["read", "write"],
            rate_limit=100,
            expires_at="2025-01-01T00:00:00Z",
        )

        self.assertEqual(key.scopes, ["read", "write"])
        self.assertEqual(key.rate_limit, 100)
        self.assertEqual(key.expires_at, "2025-01-01T00:00:00Z")

    def test_apikey_defaults_to_empty_scopes(self):
        """APIKey defaults scopes to empty list."""
        key = APIKey(
            id="key123",
            key_hash="hash123",
            name="Test Key",
            owner_id="user456",
        )

        self.assertEqual(key.scopes, [])

    def test_apikey_to_resource_excludes_key_hash(self):
        """to_resource() excludes key_hash from resource dict."""
        key = APIKey(
            id="key123",
            key_hash="secret_hash",
            name="Test Key",
            owner_id="user456",
            rate_limit=100,
        )

        resource = key.to_resource()

        # key_hash should not be in resource
        self.assertNotIn("key_hash", resource)
        # Other fields should be present
        self.assertEqual(resource["id"], "key123")
        self.assertEqual(resource["name"], "Test Key")
        self.assertEqual(resource["rate_limit"], 100)

    def test_apikey_from_storage_deserialization(self):
        """from_storage() creates APIKey from storage dict."""
        record = {
            "id": "key123",
            "created_at": "2023-01-01T00:00:00Z",
            "key_hash": "hash123",
            "name": "Test Key",
            "owner_id": "user456",
            "scopes": ["read"],
            "rate_limit": 50,
            "expires_at": None,
            "revoked_at": None,
            "last_used": None,
        }

        key = APIKey.from_storage(record)

        self.assertEqual(key.id, "key123")
        self.assertEqual(key.key_hash, "hash123")
        self.assertEqual(key.name, "Test Key")
        self.assertEqual(key.owner_id, "user456")

    def test_apikey_to_storage_serialization(self):
        """to_storage() converts APIKey to storage dict."""
        key = APIKey(
            id="key123",
            key_hash="hash123",
            name="Test Key",
            owner_id="user456",
        )

        storage = key.to_storage()

        self.assertEqual(storage["id"], "key123")
        self.assertEqual(storage["key_hash"], "hash123")
        self.assertEqual(storage["name"], "Test Key")
        self.assertEqual(storage["owner_id"], "user456")

    def test_apikey_is_active_returns_true_for_active_key(self):
        """is_active() returns True when key is neither expired nor revoked."""
        key = APIKey(
            id="key123",
            key_hash="hash123",
            name="Test Key",
            owner_id="user456",
            expires_at=schema.DateTime.utcafter(days=1),
        )

        self.assertTrue(key.is_active())

    def test_apikey_is_active_returns_false_for_expired_key(self):
        """is_active() returns False when key is expired."""
        key = APIKey(
            id="key123",
            key_hash="hash123",
            name="Test Key",
            owner_id="user456",
            expires_at=schema.DateTime.utcafter(days=-1),
        )

        self.assertFalse(key.is_active())

    def test_apikey_is_active_returns_false_for_revoked_key(self):
        """is_active() returns False when key is revoked."""
        key = APIKey(
            id="key123",
            key_hash="hash123",
            name="Test Key",
            owner_id="user456",
            revoked_at=schema.DateTime.utcnow(),
        )

        self.assertFalse(key.is_active())

    def test_apikey_is_expired_returns_false_without_expiry(self):
        """is_expired() returns False when expires_at is None."""
        key = APIKey(
            id="key123",
            key_hash="hash123",
            name="Test Key",
            owner_id="user456",
        )

        self.assertFalse(key.is_expired())

    def test_apikey_is_expired_returns_false_for_future_expiry(self):
        """is_expired() returns False when expires_at is in the future."""
        key = APIKey(
            id="key123",
            key_hash="hash123",
            name="Test Key",
            owner_id="user456",
            expires_at=schema.DateTime.utcafter(days=1),
        )

        self.assertFalse(key.is_expired())

    def test_apikey_is_expired_returns_true_for_past_expiry(self):
        """is_expired() returns True when expires_at is in the past."""
        key = APIKey(
            id="key123",
            key_hash="hash123",
            name="Test Key",
            owner_id="user456",
            expires_at=schema.DateTime.utcafter(days=-1),
        )

        self.assertTrue(key.is_expired())

    def test_apikey_is_revoked_returns_false_without_revocation(self):
        """is_revoked() returns False when revoked_at is None."""
        key = APIKey(
            id="key123",
            key_hash="hash123",
            name="Test Key",
            owner_id="user456",
        )

        self.assertFalse(key.is_revoked())

    def test_apikey_is_revoked_returns_true_when_revoked(self):
        """is_revoked() returns True when revoked_at is set."""
        key = APIKey(
            id="key123",
            key_hash="hash123",
            name="Test Key",
            owner_id="user456",
            revoked_at=schema.DateTime.utcnow(),
        )

        self.assertTrue(key.is_revoked())

    def test_apikey_has_scope_returns_true_for_granted_scope(self):
        """has_scope() returns True for a scope in the key's scopes."""
        key = APIKey(
            id="key123",
            key_hash="hash123",
            name="Test Key",
            owner_id="user456",
            scopes=["traces:read", "traces:write"],
        )

        self.assertTrue(key.has_scope("traces:read"))

    def test_apikey_has_scope_returns_false_for_missing_scope(self):
        """has_scope() returns False for a scope not in the key's scopes."""
        key = APIKey(
            id="key123",
            key_hash="hash123",
            name="Test Key",
            owner_id="user456",
            scopes=["traces:read"],
        )

        self.assertFalse(key.has_scope("traces:write"))

    def test_apikey_has_scope_matches_wildcards_exactly(self):
        """has_scope() matches wildcard scopes only exactly.

        Wildcard expansion (e.g. "traces:*" satisfying "traces:read")
        is the authorization layer's responsibility (#575).
        """
        key = APIKey(
            id="key123",
            key_hash="hash123",
            name="Test Key",
            owner_id="user456",
            scopes=["traces:*"],
        )

        self.assertTrue(key.has_scope("traces:*"))
        self.assertFalse(key.has_scope("traces:read"))

    def test_apikey_has_scope_raises_typeerror_for_non_string(self):
        """has_scope() raises TypeError for a non-string scope."""
        key = APIKey(
            id="key123",
            key_hash="hash123",
            name="Test Key",
            owner_id="user456",
            scopes=["read"],
        )

        with self.assertRaises(TypeError):
            key.has_scope(["read"])  # pyright: ignore[reportArgumentType]

    def test_apikey_validate_update_accepts_mutable_fields(self):
        """validate_update() accepts valid updates to mutable fields."""
        APIKey.validate_update({"name": "New Name"})

        APIKey.validate_update({
            "name": "New Name",
            "scopes": ["traces:read", "traces:write"],
            "rate_limit": 100,
        })

    def test_apikey_validate_update_accepts_null_rate_limit(self):
        """validate_update() accepts rate_limit=None (unlimited)."""
        APIKey.validate_update({"rate_limit": None})

    def test_apikey_validate_update_rejects_immutable_fields(self):
        """validate_update() rejects updates to immutable fields."""
        with self.assertRaises(ValueError):
            APIKey.validate_update({"revoked_at": schema.DateTime.utcnow()})

    def test_apikey_validate_update_rejects_unknown_fields(self):
        """validate_update() rejects fields that don't exist on the model."""
        with self.assertRaises(ValueError):
            APIKey.validate_update({"nonexistent": "value"})

    def test_apikey_validate_update_rejects_invalid_scopes_type(self):
        """validate_update() rejects non-list or non-string scopes."""
        with self.assertRaises(ValueError):
            APIKey.validate_update({"scopes": "traces:read"})

        with self.assertRaises(ValueError):
            APIKey.validate_update({"scopes": [1, 2, 3]})

    def test_apikey_validate_update_rejects_invalid_rate_limit_type(self):
        """validate_update() rejects non-integer rate_limit values."""
        with self.assertRaises(ValueError):
            APIKey.validate_update({"rate_limit": "unlimited"})

        with self.assertRaises(ValueError):
            APIKey.validate_update({"rate_limit": True})

    def test_apikey_validate_update_rejects_empty_update(self):
        """validate_update() rejects an empty update dict."""
        with self.assertRaises(ValueError):
            APIKey.validate_update({})


class TestTraceTreeIdentity(unittest.TestCase):
    """Tree nodes carry span identity (#823).

    The detail views serialize via TraceTreeNode; without identity
    fields there, the detail page and the versioned detail API show
    '—' client/user even when the spans have them — disagreeing with
    the list summaries built from the full TraceSpan.
    """

    def _span(self, span_id, parent_id=None, **extra):
        span = {
            "span_id": span_id,
            "trace_id": "t" * 32,
            "parent_span_id": parent_id,
            "method": "GET",
            "path": "/api/test",
            "status_code": 200,
            "started_at": "2026-10-05T10:00:00Z",
            "duration_ms": 10.0,
            "error_message": None,
            "client_id": "uid-client-abc",
            "user_id": "user@nyjc.edu.sg",
        }
        span.update(extra)
        return span

    def test_from_spans_maps_identity_onto_nodes(self):
        tree = TraceTree.from_spans([
            self._span("root"),
            self._span("child", parent_id="root"),
        ])

        self.assertEqual(tree.root.client_id, "uid-client-abc")
        self.assertEqual(tree.root.user_id, "user@nyjc.edu.sg")
        self.assertEqual(tree.root.children[0].client_id, "uid-client-abc")
        self.assertEqual(tree.root.children[0].user_id, "user@nyjc.edu.sg")

    def test_identity_absent_defaults_to_none(self):
        span = self._span("root")
        del span["client_id"]
        del span["user_id"]

        tree = TraceTree.from_spans([span])

        self.assertIsNone(tree.root.client_id)
        self.assertIsNone(tree.root.user_id)

    def test_to_resource_includes_identity(self):
        tree = TraceTree.from_spans([self._span("root")])

        resource = tree.to_resource()

        self.assertEqual(resource["client_id"], "uid-client-abc")
        self.assertEqual(resource["user_id"], "user@nyjc.edu.sg")


if __name__ == "__main__":
    unittest.main()
