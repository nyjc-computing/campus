"""Unit tests for the trace tree/detail tags passthrough (campus#1175).

The tree/detail path must carry the span's full stored tags dict —
request_kind (flask-campus#26 static capture), journey_name (#828),
warnings, event_type (#941) — with parity with the flat spans list on
the same spans. The passthrough itself ships in campus-model
(TraceTreeNode.tags, v0.2.5); these tests pin the audit service's tree
view on top of it, since this is the surface the audit UI and the
CLI's traces get render.
"""

import unittest

from campus.common import env

# Configure test storage before importing storage-backed modules
env.set('STORAGE_MODE', "1")

TRACE_ID = "a" * 32

ROOT_TAGS = {
    "request_kind": "static",
    "journey_name": "fetch-asset",
    "device_id": "uid-device-9f3c",
    "warnings": ["slow-response"],
}


def _root_span() -> dict:
    from campus.model.audit import TraceSpan
    span = TraceSpan(
        trace_id=TRACE_ID,
        span_id=TRACE_ID[:16],
        parent_span_id=None,
        method="GET",
        path="/static/app.js",
        query_params={},
        status_code=200,
        started_at="2026-11-20T10:00:00Z",
        duration_ms=5.0,
        client_id=None,
        user_id=None,
        client_ip="127.0.0.1",
        user_agent="test",
        error_message=None,
        tags=dict(ROOT_TAGS),
    )
    return span.to_storage()


class TestTraceTreeTags(unittest.TestCase):
    """get_tree exposes the stored tags dict on the root node."""

    def setUp(self):
        from campus.audit.resources.traces import traces_storage
        from campus.model import audit as audit_model

        traces_storage.init_from_model("spans", audit_model.TraceSpan)
        traces_storage.delete_matching({})
        traces_storage.insert_one(_root_span())

    def tearDown(self):
        from campus.audit.resources.traces import traces_storage
        traces_storage.delete_matching({})

    def test_tree_root_carries_full_tags_dict(self):
        from campus.audit.resources.traces import TraceFilter, TraceResource

        tree = TraceResource(TRACE_ID).get_tree(trace_filter=TraceFilter())
        self.assertIsNotNone(tree)
        assert tree is not None and tree.root is not None
        self.assertEqual(tree.root.tags, ROOT_TAGS)
        # The #825 device_id lift still works alongside the full dict.
        self.assertEqual(tree.root.device_id, "uid-device-9f3c")
        # Parity with the flat spans list: the resource payload the UI
        # renders must include the tags the list view returns.
        payload = tree.to_resource()
        self.assertEqual(payload["tags"], ROOT_TAGS)


if __name__ == "__main__":
    unittest.main()
