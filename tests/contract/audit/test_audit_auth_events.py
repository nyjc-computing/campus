"""HTTP contract tests for campus.audit authentication audit events.

These tests verify that authentication operations emit proper audit events
to the traces table for security monitoring and compliance.

Audit Events Tested:
- campus.apikeys.auth.success - Valid API key authentication
- campus.apikeys.auth.failed - Invalid/missing API key

File: tests/contract/audit/test_audit_auth_events.py
Issue: #567
"""

import unittest

from campus.common.utils import secret, uid
from tests.fixtures import services
from tests.fixtures.audit_events import get_audit_spans, parse_audit_span_data


class TestAuditAuthSuccessEvent(unittest.TestCase):
    """Contract tests for campus.apikeys.auth.success audit event."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager(shared=False)
        cls.manager.initialize()
        cls.app = cls.manager.audit_app

        # Initialize API keys and traces storage
        from campus.audit.resources.apikeys import APIKeysResource
        from campus.audit.resources.traces import TracesResource
        APIKeysResource.init_storage()
        TracesResource.init_storage()

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        self.manager.clear_test_data()
        assert self.app
        self.client = self.app.test_client()

        # Create a test audit API key for authentication
        from campus.audit.resources.apikeys import APIKeysResource
        apikey_resource = APIKeysResource()
        api_key_model, api_key_value = apikey_resource.new(
            name="Test Auth Key",
            owner_id="test-user",
            scopes="admin",
        )
        self.api_key_id = api_key_model.id
        self.auth_headers = {"Authorization": f"Bearer {api_key_value}"}

        # Clear audit events generated during setup (API key creation)
        from tests.fixtures.audit_events import get_audit_spans
        import campus.storage
        from campus.audit.resources.traces import traces_storage

        # Get all audit events and delete them
        all_spans = traces_storage.get_matching({}, limit=1000)
        audit_spans = [s for s in all_spans if s.get("path", "").startswith("campus.")]
        for span in audit_spans:
            try:
                traces_storage.delete_by_id(span["id"])
            except campus.storage.errors.NotFoundError:
                pass

    def test_successful_authentication_emits_audit_event(self):
        """Successful API key authentication emits campus.apikeys.auth.success event."""
        # Make authenticated request to protected endpoint
        response = self.client.get(
            "/audit/v1/traces/",
            headers=self.auth_headers
        )
        self.assertEqual(response.status_code, 200)

        # Verify audit event was emitted
        events = get_audit_spans("campus.apikeys.auth.success")
        self.assertGreater(len(events), 0, "No auth.success events found")

        # Get the most recent event
        event = events[0]

        # Verify event structure (TraceSpan with audit event data)
        self.assertEqual(event["path"], "campus.apikeys.auth.success")
        self.assertIn("id", event)
        self.assertIn("started_at", event)
        self.assertIn("tags", event)

        # Parse and verify event data from tags
        data = parse_audit_span_data(event)
        self.assertIn("api_key_id", data)
        self.assertEqual(data["api_key_id"], self.api_key_id)
        self.assertIn("client_ip", data)

    def test_successful_authentication_includes_api_key_id(self):
        """Auth success event includes the authenticated API key ID."""
        # Make authenticated request to protected endpoint
        response = self.client.get(
            "/audit/v1/traces/",
            headers=self.auth_headers
        )
        self.assertEqual(response.status_code, 200)

        # Verify event includes api_key_id
        events = get_audit_spans("campus.apikeys.auth.success")
        self.assertGreater(len(events), 0, "No auth.success events found")

        # Get the most recent event
        event = events[0]
        data = parse_audit_span_data(event)
        self.assertEqual(data["api_key_id"], self.api_key_id)

    def test_successful_authentication_includes_client_ip(self):
        """Auth success event includes client IP address."""
        # Make authenticated request to protected endpoint
        response = self.client.get(
            "/audit/v1/traces/",
            headers=self.auth_headers
        )
        self.assertEqual(response.status_code, 200)

        # Verify event includes client_ip
        events = get_audit_spans("campus.apikeys.auth.success")
        self.assertGreater(len(events), 0)

        data = parse_audit_span_data(events[0])
        self.assertIn("client_ip", data)
        # Test client uses localhost/127.0.0.1
        self.assertIsNotNone(data["client_ip"])


class TestAuditAuthFailedEvent(unittest.TestCase):
    """Contract tests for campus.apikeys.auth.failed audit event."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager(shared=False)
        cls.manager.initialize()
        cls.app = cls.manager.audit_app

        # Initialize API keys and traces storage
        from campus.audit.resources.apikeys import APIKeysResource
        from campus.audit.resources.traces import TracesResource
        APIKeysResource.init_storage()
        TracesResource.init_storage()

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        self.manager.clear_test_data()
        assert self.app
        self.client = self.app.test_client()

    def test_missing_api_key_emits_audit_event(self):
        """Missing API key emits campus.apikeys.auth.failed event."""
        # Make request without authentication
        response = self.client.get("/audit/v1/traces/")
        self.assertEqual(response.status_code, 401)

        # Verify audit event was emitted
        events = get_audit_spans("campus.apikeys.auth.failed")
        self.assertGreater(len(events), 0, "No auth.failed events found")

        # Verify event structure
        event = events[0]
        self.assertEqual(event["path"], "campus.apikeys.auth.failed")

        # Parse and verify event data from tags
        data = parse_audit_span_data(event)
        self.assertIn("reason", data)
        self.assertIn("Missing API key", data["reason"])
        self.assertIn("client_ip", data)

    def test_invalid_api_key_format_emits_audit_event(self):
        """Invalid API key format emits campus.apikeys.auth.failed event."""
        # Make request with malformed API key
        response = self.client.get(
            "/audit/v1/traces/",
            headers={"Authorization": "Bearer invalid_format_key"}
        )
        self.assertEqual(response.status_code, 401)

        # Verify audit event was emitted
        events = get_audit_spans("campus.apikeys.auth.failed")
        self.assertGreater(len(events), 0)

        # Parse and verify event data from tags
        data = parse_audit_span_data(events[0])
        self.assertIn("reason", data)
        self.assertIn("Invalid API key format", data["reason"])

    def test_unknown_api_key_emits_audit_event(self):
        """Unknown API key (valid format, not in database) emits auth.failed event."""
        # Generate valid format key that doesn't exist
        fake_key = secret.generate_audit_api_key()

        response = self.client.get(
            "/audit/v1/traces/",
            headers={"Authorization": f"Bearer {fake_key}"}
        )
        self.assertEqual(response.status_code, 401)

        # Verify audit event was emitted
        events = get_audit_spans("campus.apikeys.auth.failed")
        self.assertGreater(len(events), 0)

        # Parse and verify event data from tags
        data = parse_audit_span_data(events[0])
        self.assertIn("reason", data)
        self.assertIn("Invalid API key", data["reason"])

    def test_failed_authentication_includes_client_ip(self):
        """Failed auth event includes client IP address."""
        # Make request without authentication
        response = self.client.get("/audit/v1/traces/")
        self.assertEqual(response.status_code, 401)

        # Verify event includes client_ip
        events = get_audit_spans("campus.apikeys.auth.failed")
        self.assertGreater(len(events), 0)

        data = parse_audit_span_data(events[0])
        self.assertIn("client_ip", data)
        self.assertIsNotNone(data["client_ip"])

    def test_failed_authentication_includes_reason(self):
        """Failed auth event includes reason for failure."""
        # Make request without authentication
        response = self.client.get("/audit/v1/traces/")
        self.assertEqual(response.status_code, 401)

        # Verify event includes reason
        events = get_audit_spans("campus.apikeys.auth.failed")
        self.assertGreater(len(events), 0)

        data = parse_audit_span_data(events[0])
        self.assertIn("reason", data)
        self.assertIsInstance(data["reason"], str)
        self.assertGreater(len(data["reason"]), 0)


if __name__ == "__main__":
    unittest.main()
