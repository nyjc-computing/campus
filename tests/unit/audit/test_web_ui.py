"""Unit tests for the Audit Web UI routes.

These tests verify that the audit UI blueprint serves its pages, static
assets, and unauthenticated data endpoints. Page routes render templates
only; data endpoint tests seed spans through the resources layer.

File: tests/unit/audit/test_web_ui.py
Issue: #429
"""

import contextlib
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

    def test_index_serves_landing_page(self):
        """/audit/ is the public landing page (docs/web-ui-requirements.md §2)."""
        response = self.client.get("/audit/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Browse traces", response.data)
        self.assertIn(b"/audit/traces", response.data)
        # The landing page carries no trace list scaffolding
        self.assertNotIn(b"trace-filters", response.data)

    def test_traces_serves_trace_list(self):
        """/audit/traces is the trace list page (docs/web-ui-requirements.md §2)."""
        response = self.client.get("/audit/traces")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"trace-filters", response.data)
        self.assertIn(b"trace-table-body", response.data)
        self.assertIn(b"traces.js", response.data)
        # Journey filter (#803) rides the standard filter form
        self.assertIn(b'name="journey_id"', response.data)
        # One merged template serves both views (#803): the group-by-
        # journey header card lives here, filled in by traces.js when
        # the journey_id URL param selects a journey
        self.assertIn(b"journey-header", response.data)
        self.assertIn(b"journey-card", response.data)
        # PATH keeps its space via fixed column shares
        self.assertIn(b"col-path", response.data)

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
            ("/audit/static/css/main.css", b"journey-card"),
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
        """traces.js must fetch the UI data endpoints, not the auth'd API.

        The browser cannot call the versioned audit API (API-key auth),
        so the list page must target /audit/api/traces for the flat list
        and /audit/api/journeys for the group-by-journey view (#803).
        """
        response = self.client.get("/audit/static/js/traces.js")
        self.assertIn(b"/audit/api/traces", response.data)
        self.assertIn(b"/audit/api/journeys", response.data)
        self.assertNotIn(b"/audit/v1/traces", response.data)

    def test_traces_js_drives_filters_from_url_params(self):
        """Filters live in the URL (#803): the form syncs from params on
        load and back/forward, and Apply pushes form state into the URL.
        """
        traces_js = self.client.get("/audit/static/js/traces.js").data
        self.assertIn(b"URLSearchParams(window.location.search)", traces_js)
        self.assertIn(b"history.pushState", traces_js)
        self.assertIn(b"popstate", traces_js)

    def test_traces_js_formats_ids_and_timestamps(self):
        """The list renders the full trace ID on one line and local datetimes.

        docs/web-ui-requirements.md §3.3/§7.1/§7.4: trace IDs render in
        full, unwrapped (td.trace-id keeps them on one line), timestamps
        render as local YYYY-MM-DD HH:MM:SS. The row renderer lives in
        main.js (shared with the journey view, #803); traces.js just
        calls it per row.
        """
        main_js = self.client.get("/audit/static/js/main.js").data
        traces_js = self.client.get("/audit/static/js/traces.js").data
        css = self.client.get("/audit/static/css/main.css").data
        # Shared timestamp helper exists and is used by the row renderer
        self.assertIn(b"function formatTimestamp", main_js)
        self.assertIn(b"formatTimestamp(summary.started_at)", main_js)
        # The trace ID cell renders the full id with the no-wrap class;
        # the truncation helper is gone (dead code).
        self.assertIn(b'<td class="trace-id">', main_js)
        self.assertNotIn(b"formatTraceId", main_js)
        self.assertIn(b".trace-table td.trace-id", css)
        # Detail links keep pointing at the detail route; the list page
        # renders rows through the shared renderer
        self.assertIn(b"/audit/traces/${encodeURIComponent(summary.trace_id)}", main_js)
        self.assertIn(b"traces.map(renderTraceRow)", traces_js)

    def test_trace_js_targets_ui_data_endpoint(self):
        """trace.js must fetch the UI data endpoints, not the auth'd API."""
        response = self.client.get("/audit/static/js/trace.js")
        self.assertIn(b"/audit/api/traces", response.data)
        self.assertNotIn(b"/audit/v1", response.data)

    def test_journey_id_renders_as_meta_line_above_trace_id(self):
        """The journey id sits in small text above the trace id (#803).

        Card-style meta line instead of a dedicated column: it links to
        the group-by-journey view and is dropped in journey view itself
        (the group header already names the journey).
        """
        main_js = self.client.get("/audit/static/js/main.js").data
        self.assertIn(b'class="cell-journey"', main_js)
        self.assertIn(b"/audit/traces?journey_id=${encodeURIComponent(journeyId)}", main_js)
        self.assertIn(b"options.journeyView ? '' : renderJourneyLine(journeyId)", main_js)
        # The old inline chip is gone
        self.assertNotIn(b"journey-chip", main_js)
        self.assertIn(b".cell-journey", self.client.get("/audit/static/css/main.css").data)

    def test_journey_url_redirects_to_merged_traces_view(self):
        """/audit/journeys/<id> redirects to /audit/traces?journey_id=<id> (#803)."""
        journey_id = "journey_abc123"
        response = self.client.get(f"/audit/journeys/{journey_id}")
        self.assertEqual(response.status_code, 302)
        location = response.headers.get("Location", "")
        self.assertTrue(
            location.endswith(f"/audit/traces?journey_id={journey_id}"),
            f"unexpected redirect target: {location}",
        )


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

    def test_get_journey_returns_member_traces_oldest_first(self):
        """GET /audit/api/journeys/<id> lists tagged traces, oldest first (#803)."""
        from campus.common import schema
        from campus.model import audit as audit_model

        seeded: list[str] = []

        def _seed(trace_id: str, span_id: str, started_at: str, journey_id: str | None):
            span = audit_model.TraceSpan(
                trace_id=trace_id,
                span_id=span_id,
                method="GET",
                path="/auth/v1/authorize",
                status_code=302,
                started_at=schema.DateTime(started_at),
                duration_ms=5.0,
                client_ip="127.0.0.1",
                tags={"journey_id": journey_id} if journey_id else {},
            )
            result = TracesResource().ingest([span])
            self.assertEqual(result["created"], [span.span_id])
            seeded.append(span.span_id)

        # Local import after storage init (see setUpClass)
        from campus.audit.resources.traces import TracesResource, traces_storage

        try:
            _seed("a" * 32, "b" * 16, "2026-10-04T10:00:00+00:00", "journey_u1")
            _seed("c" * 32, "d" * 16, "2026-10-04T10:01:00+00:00", "journey_u1")
            _seed("e" * 32, "f" * 16, "2026-10-04T10:02:00+00:00", None)

            response = self.client.get("/audit/api/journeys/journey_u1")
            self.assertEqual(response.status_code, 200)
            body = response.get_json()
            self.assertEqual(body["journey_id"], "journey_u1")
            self.assertEqual(body["trace_count"], 2)
            self.assertEqual(
                [t["trace_id"] for t in body["traces"]],
                ["a" * 32, "c" * 32],
            )
            # Rows carry the journey chip data: root span tags surface the id
            self.assertEqual(
                body["traces"][0]["root_span"]["tags"]["journey_id"],
                "journey_u1",
            )

            unknown = self.client.get("/audit/api/journeys/journey_missing")
            self.assertEqual(unknown.status_code, 200)
            self.assertEqual(unknown.get_json()["trace_count"], 0)
        finally:
            # This class has no per-test storage cleanup; remove the
            # seeds so later tests (and the unfiltered list shape test)
            # see an unchanged table.
            for span_id in seeded:
                with contextlib.suppress(Exception):
                    traces_storage.delete_by_id(span_id)

    def test_list_traces_filters_by_journey_id(self):
        """GET /audit/api/traces?journey_id=... narrows to journey traces (#803)."""
        from campus.audit.resources.traces import TracesResource, traces_storage
        from campus.model import audit as audit_model

        tagged = audit_model.TraceSpan(
            trace_id="9" * 32,
            span_id="8" * 16,
            method="GET",
            path="/auth/v1/verify_login",
            status_code=302,
            duration_ms=5.0,
            client_ip="127.0.0.1",
            tags={"journey_id": "journey_u2"},
        )
        untagged = audit_model.TraceSpan(
            trace_id="7" * 32,
            span_id="6" * 16,
            method="GET",
            path="/api/v1/circles/",
            status_code=200,
            duration_ms=5.0,
            client_ip="127.0.0.1",
        )
        result = TracesResource().ingest([tagged, untagged])
        self.assertEqual(sorted(result["created"]), sorted([tagged.span_id, untagged.span_id]))

        try:
            response = self.client.get("/audit/api/traces?journey_id=journey_u2")
            self.assertEqual(response.status_code, 200)
            body = response.get_json()
            self.assertEqual(
                [t["trace_id"] for t in body["traces"]],
                ["9" * 32],
            )
        finally:
            for span in (tagged, untagged):
                with contextlib.suppress(Exception):
                    traces_storage.delete_by_id(span.span_id)


if __name__ == "__main__":
    unittest.main()
