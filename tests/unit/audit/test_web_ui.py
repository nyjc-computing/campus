"""Unit tests for the Audit Web UI routes.

These tests verify that the audit UI blueprint serves its pages, static
assets, and unauthenticated data endpoints. Page routes render templates
only; data endpoint tests seed spans through the resources layer.

File: tests/unit/audit/test_web_ui.py
Issue: #429
"""

import unittest

import flask


class TestAuditWebUI(unittest.TestCase):
    """Verify audit UI pages render and static assets resolve (no more 404s)."""

    @classmethod
    def setUpClass(cls):
        # Lazy import: campus.audit pulls in storage modules at import time.
        # See AGENTS.md - Storage Initialization Order.
        from campus.audit.web import ui

        app = flask.Flask(__name__)
        app.config["TESTING"] = True
        app.register_blueprint(ui.create_blueprint())
        cls.client = app.test_client()

    def test_index_serves_trace_list(self):
        """/audit/ is the trace list page (docs/web-ui-requirements.md §2)."""
        response = self.client.get("/audit/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"trace-filters", response.data)
        self.assertIn(b"trace-table-body", response.data)
        self.assertIn(b"traces.js", response.data)

    def test_former_list_url_redirects_to_index(self):
        """/audit/traces redirects to /audit/ so old links keep working."""
        response = self.client.get("/audit/traces")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/audit/"))

    def test_trace_detail_page_renders_scaffold(self):
        """/audit/traces/<trace_id> renders the waterfall/drawer scaffold."""
        trace_id = "a" * 32
        response = self.client.get(f"/audit/traces/{trace_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"waterfall-rows", response.data)
        self.assertIn(b"span-drawer", response.data)
        self.assertIn(b'data-trace-id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"', response.data)
        self.assertIn(b"trace.js", response.data)
        self.assertNotIn(b"traces.js", response.data)

    def test_static_assets_are_served(self):
        """Static assets referenced by the templates resolve instead of 404."""
        expected_tokens = [
            ("/audit/static/css/main.css", b"wf-bar"),
            ("/audit/static/css/main.css", b"span-drawer"),
            ("/audit/static/js/main.js", b"escapeHtml"),
            ("/audit/static/js/traces.js", b"loadTraces"),
            ("/audit/static/js/trace.js", b"renderWaterfall"),
        ]
        for path, token in expected_tokens:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(token, response.data)

    def test_traces_js_targets_ui_data_endpoint(self):
        """traces.js must fetch the UI data endpoint, not the auth'd API.

        The browser cannot call the versioned audit API (API-key auth), so
        the list page must target /audit/api/traces.
        """
        response = self.client.get("/audit/static/js/traces.js")
        self.assertIn(b"/audit/api/traces", response.data)
        self.assertNotIn(b"/audit/v1/traces", response.data)

    def test_traces_js_formats_ids_and_timestamps(self):
        """The list renders commit-hash trace IDs and local datetimes.

        docs/web-ui-requirements.md §3.3/§7.1/§7.4: trace IDs truncate to
        first 8 chars + ellipsis in tables (full ID in the hover tooltip),
        timestamps render as local YYYY-MM-DD HH:MM:SS.
        """
        main_js = self.client.get("/audit/static/js/main.js").data
        traces_js = self.client.get("/audit/static/js/traces.js").data
        # Shared helpers exist
        self.assertIn(b"function formatTraceId", main_js)
        self.assertIn(b"function formatTimestamp", main_js)
        # The list page uses them, keeping full values in tooltips
        self.assertIn(b"formatTraceId(summary.trace_id)", traces_js)
        self.assertIn(b"formatTimestamp(summary.started_at)", traces_js)
        self.assertIn(b'title="${escapeHtml(summary.trace_id)}"', traces_js)

    def test_trace_js_targets_ui_data_endpoint(self):
        """trace.js must fetch the UI data endpoints, not the auth'd API."""
        response = self.client.get("/audit/static/js/trace.js")
        self.assertIn(b"/audit/api/traces", response.data)
        self.assertNotIn(b"/audit/v1", response.data)


class TestAuditUIDataEndpoint(unittest.TestCase):
    """Verify the UI data endpoints serve trace data in the API's shape."""

    @classmethod
    def setUpClass(cls):
        # Lazy import: campus.audit pulls in storage modules at import time.
        # See AGENTS.md - Storage Initialization Order.
        from campus.audit.resources.traces import TracesResource
        from campus.audit.web import data

        TracesResource.init_storage()

        app = flask.Flask(__name__)
        app.config["TESTING"] = True
        app.register_blueprint(data.create_blueprint())
        cls.client = app.test_client()

    def test_list_traces_returns_api_shape(self):
        """GET /audit/api/traces returns the {traces, cursor} shape."""
        response = self.client.get("/audit/api/traces?limit=5&status=")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertIsInstance(body["traces"], list)
        self.assertLessEqual(len(body["traces"]), 5)
        self.assertEqual(body["cursor"], {"next": None, "has_more": False})

    def _seed_trace(self):
        """Ingest a two-span trace and return the root span model."""
        from campus.audit.resources.traces import TracesResource
        from campus.model import audit as audit_model

        root = audit_model.TraceSpan(
            method="GET",
            path="/audit/v1/traces/",
            status_code=200,
            duration_ms=12.5,
            client_ip="127.0.0.1",
            request_headers={"Accept": "application/json"},
            response_body={"ok": True},
        )
        child = audit_model.TraceSpan(
            trace_id=root.trace_id,
            parent_span_id=root.span_id,
            method="POST",
            path="/audit/v1/spans/",
            status_code=201,
            duration_ms=5.0,
            client_ip="127.0.0.1",
            request_headers={"Content-Type": "application/json"},
        )
        result = TracesResource().ingest([root, child])
        self.assertEqual(sorted(result["created"]), sorted([root.span_id, child.span_id]))
        return root, child

    def test_get_trace_returns_tree_shape(self):
        """GET /audit/api/traces/<id> mirrors the versioned trace response."""
        root, child = self._seed_trace()
        response = self.client.get(f"/audit/api/traces/{root.trace_id}")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["trace_id"], root.trace_id)
        root_span = body["root_span"]
        self.assertEqual(root_span["method"], "GET")
        self.assertEqual(root_span["path"], "/audit/v1/traces/")
        self.assertEqual(len(root_span["children"]), 1)
        self.assertEqual(root_span["children"][0]["span_id"], child.span_id)
        self.assertEqual(root_span["children"][0]["depth"], 1)

    def test_get_span_returns_full_span(self):
        """GET /audit/api/traces/<tid>/spans/<sid> returns headers/bodies."""
        root, child = self._seed_trace()
        response = self.client.get(
            f"/audit/api/traces/{root.trace_id}/spans/{child.span_id}"
        )
        self.assertEqual(response.status_code, 200)
        span = response.get_json()
        self.assertEqual(span["span_id"], child.span_id)
        self.assertEqual(span["trace_id"], root.trace_id)
        self.assertEqual(span["request_headers"], {"Content-Type": "application/json"})
        self.assertNotIn("id", span)

    def test_get_unknown_trace_returns_404(self):
        """GET /audit/api/traces/<unknown> returns a JSON 404."""
        response = self.client.get(f"/audit/api/traces/{'f' * 32}")
        self.assertEqual(response.status_code, 404)
        self.assertIn("error", response.get_json())

    def test_get_unknown_span_returns_404(self):
        """GET /audit/api/traces/<tid>/spans/<unknown> returns a JSON 404."""
        root, _ = self._seed_trace()
        response = self.client.get(
            f"/audit/api/traces/{root.trace_id}/spans/{'e' * 16}"
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("error", response.get_json())


if __name__ == "__main__":
    unittest.main()
