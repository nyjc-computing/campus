"""Unit tests for the Audit Web UI routes.

These tests verify that the audit UI blueprint serves its pages and
static assets. The UI routes render templates only (no storage access),
so a bare Flask app with just the UI blueprint is sufficient.

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

    def test_index_renders_base_layout(self):
        """/audit/ renders the base layout with navigation."""
        response = self.client.get("/audit/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Audit Traces", response.data)
        self.assertIn(b"/audit/traces", response.data)

    def test_traces_page_renders_list_scaffold(self):
        """/audit/traces renders the filter form and trace table."""
        response = self.client.get("/audit/traces")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"trace-filters", response.data)
        self.assertIn(b"trace-table-body", response.data)
        self.assertIn(b"traces.js", response.data)

    def test_static_assets_are_served(self):
        """Static assets referenced by base.html resolve instead of 404."""
        expected_tokens = [
            ("/audit/static/css/main.css", b"status-badge"),
            ("/audit/static/js/main.js", b"escapeHtml"),
            ("/audit/static/js/traces.js", b"loadTraces"),
        ]
        for path, token in expected_tokens:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(token, response.data)


if __name__ == "__main__":
    unittest.main()
