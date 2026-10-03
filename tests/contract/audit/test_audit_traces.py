"""HTTP contract tests for campus.audit endpoints.

These tests verify the HTTP interface contract for the audit/traces service.
They test status codes, response formats, and authentication behavior.

Audit Endpoints Reference:
- POST   /audit/v1/traces                    - Ingest spans (requires auth)
- GET    /audit/v1/traces                    - List recent traces (requires auth)
- GET    /audit/v1/traces/<trace_id>/        - Get trace tree (requires auth)
- GET    /audit/v1/traces/<trace_id>/spans/   - List trace spans (requires auth)
- GET    /audit/v1/traces/<trace_id>/spans/<span_id>/ - Get span (requires auth)
- GET    /audit/v1/traces/search             - Filter traces (requires auth)
- GET    /audit/v1/health                     - Health check (NO auth required)
"""

import base64
import unittest
from urllib.parse import urlencode

import campus.storage
from campus.common import schema
from campus.model import TraceSpan
from tests.fixtures import services

apikeys_storage = campus.storage.tables.get_db("apikeys")


class TestAuditHealthContract(unittest.TestCase):
    """HTTP contract tests for /audit/v1/health endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager(shared=False)
        cls.manager.initialize()
        # Note: audit_app is created as part of the ServiceManager setup
        cls.app = cls.manager.audit_app

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        assert self.app
        self.client = self.app.test_client()

    def test_health_check_no_auth_required(self):
        """GET /audit/v1/health returns 200 without authentication."""
        response = self.client.get("/audit/v1/health")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "ok")

    def test_health_check_returns_json(self):
        """GET /audit/v1/health returns JSON response."""
        response = self.client.get("/audit/v1/health")

        self.assertEqual(response.content_type, "application/json")
        data = response.get_json()
        self.assertIsInstance(data, dict)


class TestAuditTracesIngestContract(unittest.TestCase):
    """HTTP contract tests for POST /audit/v1/traces endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager(shared=False)
        cls.manager.initialize()
        cls.app = cls.manager.audit_app

        # Initialize API keys storage
        from campus.audit.resources.apikeys import APIKeysResource
        APIKeysResource.init_storage()

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        # Clear test data - no manual resource initialization needed
        self.manager.clear_test_data()
        assert self.app
        self.client = self.app.test_client()

        # Create a test audit API key for authentication
        from campus.audit.resources.apikeys import APIKeysResource
        _, api_key_value = APIKeysResource().new(
            name="Test Auth Key",
            owner_id="test-user",
            scopes="traces:*",
        )

        # Use the audit API key for authentication
        self.auth_headers = {"Authorization": f"Bearer {api_key_value}"}

        # Clear traces that were emitted during API key creation
        # This ensures tests start with a clean trace state
        traces_storage = campus.storage.tables.get_db("spans")
        traces_storage.delete_matching({})  # Empty query deletes all rows

    def _make_test_span(self, **overrides):
        """Helper to create a test span dict."""
        span = {
            "trace_id": "a" * 32,  # 32-char hex
            "span_id": "b" * 16,  # 16-char hex
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
            "user_agent": "test-agent",
            "error_message": None,
            "tags": {},
        }
        span.update(overrides)
        return span

    def test_ingest_spans_requires_authentication(self):
        """POST /audit/v1/traces/ requires authentication."""
        response = self.client.post(
            "/audit/v1/traces/",
            json={"spans": [self._make_test_span()]}
        )

        self.assertEqual(response.status_code, 401)

    def test_ingest_rejects_basic_auth_scheme(self):
        """Basic auth is rejected with 401; audit API is Bearer-only (#699).

        Producers authenticate with an audit_v1_ API key via Bearer auth;
        OAuth client credentials (Basic) are not a valid scheme here and
        must fail with a clear Unauthorized, not a scheme-mismatch 400.
        """
        credentials = base64.b64encode(b"uid-client-x:secret").decode()
        response = self.client.post(
            "/audit/v1/traces/",
            json={"spans": [self._make_test_span()]},
            headers={"Authorization": f"Basic {credentials}"},
        )

        self.assertEqual(response.status_code, 401)

    def test_ingest_single_span_success(self):
        """POST /audit/v1/traces/ with single span returns 201."""
        response = self.client.post(
            "/audit/v1/traces/",
            json={"spans": [self._make_test_span()]},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertIn("created", data)
        self.assertEqual(len(data["created"]), 1)
        self.assertNotIn("failed", data)

    def test_ingest_batch_spans_success(self):
        """POST /audit/v1/traces/ with multiple spans returns 201."""
        spans = [
            self._make_test_span(span_id=f"span{i}", trace_id=f"trace{i}")
            for i in range(3)
        ]

        response = self.client.post(
            "/audit/v1/traces/",
            json={"spans": spans},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(len(data["created"]), 3)

    def test_ingest_missing_spans_field_returns_error(self):
        """POST /audit/v1/traces/ without 'spans' field returns 400."""
        response = self.client.post(
            "/audit/v1/traces/",
            json={},
            headers=self.auth_headers
        )

        # Accept both 400 (Bad Request) and 422 (Unprocessable Entity) as valid error responses
        self.assertIn(response.status_code, [400, 422])

    def test_ingest_invalid_span_returns_error(self):
        """POST /audit/v1/traces/ with invalid span data returns 400."""
        response = self.client.post(
            "/audit/v1/traces/",
            json={"spans": [{"invalid": "data"}]},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 400)


class TestAuditTracesListContract(unittest.TestCase):
    """HTTP contract tests for GET /audit/v1/traces endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager(shared=False)
        cls.manager.initialize()
        cls.app = cls.manager.audit_app

        # Initialize API keys storage
        from campus.audit.resources.apikeys import APIKeysResource
        APIKeysResource.init_storage()

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        # Clear test data - no manual resource initialization needed
        self.manager.clear_test_data()
        assert self.app
        self.client = self.app.test_client()

        # Create a test audit API key for authentication
        from campus.audit.resources.apikeys import APIKeysResource
        _, api_key_value = APIKeysResource().new(
            name="Test Auth Key",
            owner_id="test-user",
            scopes="traces:*",
        )

        # Use the audit API key for authentication
        self.auth_headers = {"Authorization": f"Bearer {api_key_value}"}

        # Clear traces that were emitted during API key creation
        # This ensures tests start with a clean trace state
        traces_storage = campus.storage.tables.get_db("spans")
        traces_storage.delete_matching({})  # Empty query deletes all rows

    def test_list_traces_requires_authentication(self):
        """GET /audit/v1/traces/ requires authentication."""
        response = self.client.get("/audit/v1/traces/")

        self.assertEqual(response.status_code, 401)

    def test_list_traces_empty_returns_empty_list(self):
        """GET /audit/v1/traces/ with no traces returns empty list."""
        # Disable audit events to avoid authentication side effects
        from campus.common import env
        env.set('AUDIT_EVENTS_ENABLED', '0')

        response = self.client.get(
            "/audit/v1/traces/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["traces"], [])

        # Re-enable audit events for other tests
        env.set('AUDIT_EVENTS_ENABLED', '1')
        self.assertIn("cursor", data)

    def test_list_traces_returns_trace_summaries(self):
        """GET /audit/v1/traces/ returns trace summaries with cursor."""
        # First, ingest a span
        from campus.audit.resources.traces import TracesResource
        traces_resource = TracesResource()
        span = TraceSpan(
            trace_id="a" * 32,
            span_id="b" * 16,
            method="GET",
            path="/api/test",
            status_code=200,
            started_at=schema.DateTime.utcnow(),
            duration_ms=100.0,
            client_ip="127.0.0.1"
        )
        traces_resource.ingest([span])

        # Disable audit events to avoid authentication side effects when listing
        from campus.common import env
        env.set('AUDIT_EVENTS_ENABLED', '0')

        # Then list traces
        response = self.client.get(
            "/audit/v1/traces/",
            headers=self.auth_headers
        )

        # Re-enable audit events
        env.set('AUDIT_EVENTS_ENABLED', '1')

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data["traces"]), 1)
        self.assertEqual(data["traces"][0]["trace_id"], "a" * 32)
        self.assertIn("cursor", data)

    def test_list_traces_with_limit(self):
        """GET /audit/v1/traces/?limit=5 respects limit parameter."""
        response = self.client.get(
            "/audit/v1/traces/?limit=5",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertLessEqual(len(data["traces"]), 5)


class TestAuditTracesGetTreeContract(unittest.TestCase):
    """HTTP contract tests for GET /audit/v1/traces/<trace_id>/ endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager(shared=False)
        cls.manager.initialize()
        cls.app = cls.manager.audit_app

        # Initialize API keys storage
        from campus.audit.resources.apikeys import APIKeysResource
        APIKeysResource.init_storage()

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        # Clear test data - no manual resource initialization needed
        self.manager.clear_test_data()
        assert self.app
        self.client = self.app.test_client()

        # Create a test audit API key for authentication
        from campus.audit.resources.apikeys import APIKeysResource
        _, api_key_value = APIKeysResource().new(
            name="Test Auth Key",
            owner_id="test-user",
            scopes="traces:*",
        )

        # Use the audit API key for authentication
        self.auth_headers = {"Authorization": f"Bearer {api_key_value}"}

        # Clear traces that were emitted during API key creation
        # This ensures tests start with a clean trace state
        traces_storage = campus.storage.tables.get_db("spans")
        traces_storage.delete_matching({})  # Empty query deletes all rows

    @unittest.skip("API BUG #407: request without trailing slash is 308-redirected, never reaches auth")
    def test_get_trace_requires_authentication(self):
        """GET /audit/v1/traces/<id> requires authentication."""
        response = self.client.get("/audit/v1/traces/abc123")

        self.assertEqual(response.status_code, 401)

    @unittest.skip("API BUG #407: request without trailing slash is 308-redirected, never reaches the route")
    def test_get_trace_not_found_returns_404(self):
        """GET /audit/v1/traces/<id> with non-existent trace returns 404."""
        response = self.client.get(
            "/audit/v1/traces/doesnotexist",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 404)

    def test_get_trace_returns_tree_structure(self):
        """GET /audit/v1/traces/<id> returns nested tree structure."""
        # Ingest a trace with multiple spans
        from campus.audit.resources.traces import TracesResource
        traces_resource = TracesResource()
        trace_id = "a" * 32

        # Create root span
        root = TraceSpan(
            trace_id=trace_id,
            span_id="root",
            parent_span_id=None,
            method="GET",
            path="/api/test",
            status_code=200,
            started_at=schema.DateTime.utcnow(),
            duration_ms=100.0,
            client_ip="127.0.0.1"
        )

        # Create child span
        child = TraceSpan(
            trace_id=trace_id,
            span_id="child",
            parent_span_id="root",
            method="POST",
            path="/api/child",
            status_code=200,
            started_at=schema.DateTime.utcnow(),
            duration_ms=50.0,
            client_ip="127.0.0.1"
        )

        traces_resource.ingest([root, child])

        # Get the trace tree
        response = self.client.get(
            f"/audit/v1/traces/{trace_id}/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["trace_id"], trace_id)
        self.assertIn("root_span", data)
        self.assertIn("children", data["root_span"])


class TestAuditSpansListContract(unittest.TestCase):
    """HTTP contract tests for GET /audit/v1/traces/<trace_id>/spans/ endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager(shared=False)
        cls.manager.initialize()
        cls.app = cls.manager.audit_app

        # Initialize API keys storage
        from campus.audit.resources.apikeys import APIKeysResource
        APIKeysResource.init_storage()

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        # Clear test data - no manual resource initialization needed
        self.manager.clear_test_data()
        assert self.app
        self.client = self.app.test_client()

        # Create a test audit API key for authentication
        from campus.audit.resources.apikeys import APIKeysResource
        _, api_key_value = APIKeysResource().new(
            name="Test Auth Key",
            owner_id="test-user",
            scopes="traces:*",
        )

        # Use the audit API key for authentication
        self.auth_headers = {"Authorization": f"Bearer {api_key_value}"}

        # Clear traces that were emitted during API key creation
        # This ensures tests start with a clean trace state
        traces_storage = campus.storage.tables.get_db("spans")
        traces_storage.delete_matching({})  # Empty query deletes all rows

    def test_list_spans_requires_authentication(self):
        """GET /audit/v1/traces/<id>/spans requires authentication."""
        response = self.client.get("/audit/v1/traces/abc123/spans/")

        self.assertEqual(response.status_code, 401)

    def test_list_spans_nonexistent_trace_returns_empty(self):
        """GET /audit/v1/traces/<id>/spans with non-existent trace returns empty list."""
        response = self.client.get(
            "/audit/v1/traces/doesnotexist/spans/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["spans"], [])

    def test_list_spans_returns_flat_list(self):
        """GET /audit/v1/traces/<id>/spans returns flat list of spans."""
        from campus.audit.resources.traces import TracesResource
        traces_resource = TracesResource()
        trace_id = "a" * 32

        spans = [
            TraceSpan(
                trace_id=trace_id,
                span_id=f"span{i}",
                parent_span_id="span0" if i > 0 else None,
                method="GET",
                path=f"/api/test{i}",
                status_code=200,
                started_at=schema.DateTime.utcnow(),
                duration_ms=100.0,
                client_ip="127.0.0.1"
            )
            for i in range(3)
        ]

        traces_resource.ingest(spans)

        response = self.client.get(
            f"/audit/v1/traces/{trace_id}/spans/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data["spans"]), 3)


class TestAuditSpanGetContract(unittest.TestCase):
    """HTTP contract tests for GET /audit/v1/traces/<id>/spans/<span_id>/ endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager(shared=False)
        cls.manager.initialize()
        cls.app = cls.manager.audit_app

        # Initialize API keys storage
        from campus.audit.resources.apikeys import APIKeysResource
        APIKeysResource.init_storage()

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        # Clear test data - no manual resource initialization needed
        self.manager.clear_test_data()
        assert self.app
        self.client = self.app.test_client()

        # Create a test audit API key for authentication
        from campus.audit.resources.apikeys import APIKeysResource
        _, api_key_value = APIKeysResource().new(
            name="Test Auth Key",
            owner_id="test-user",
            scopes="traces:*",
        )

        # Use the audit API key for authentication
        self.auth_headers = {"Authorization": f"Bearer {api_key_value}"}

        # Clear traces that were emitted during API key creation
        # This ensures tests start with a clean trace state
        traces_storage = campus.storage.tables.get_db("spans")
        traces_storage.delete_matching({})  # Empty query deletes all rows

    def test_get_span_requires_authentication(self):
        """GET /audit/v1/traces/<id>/spans/<span_id> requires authentication."""
        response = self.client.get("/audit/v1/traces/abc123/spans/def456/")

        self.assertEqual(response.status_code, 401)

    def test_get_span_not_found_returns_404(self):
        """GET /audit/v1/traces/<id>/spans/<span_id> with non-existent span returns 404."""
        response = self.client.get(
            "/audit/v1/traces/doesnotexist/spans/notfound/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 404)

    def test_get_span_wrong_trace_returns_404(self):
        """GET /audit/v1/traces/<id>/spans/<span_id> span from different trace returns 404."""
        from campus.audit.resources.traces import TracesResource
        traces_resource = TracesResource()

        # Ingest a span in trace1
        span = TraceSpan(
            trace_id="a" * 32,
            span_id="span1",
            method="GET",
            path="/api/test",
            status_code=200,
            started_at=schema.DateTime.utcnow(),
            duration_ms=100.0,
            client_ip="127.0.0.1"
        )
        traces_resource.ingest([span])

        # Try to get it via a different trace_id
        response = self.client.get(
            f"/audit/v1/traces/{'b' * 32}/spans/span1/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 404)

    def test_get_span_returns_full_span_data(self):
        """GET /audit/v1/traces/<id>/spans/<span_id> returns complete span with headers/bodies."""
        from campus.audit.resources.traces import TracesResource
        traces_resource = TracesResource()
        trace_id = "a" * 32

        span = TraceSpan(
            trace_id=trace_id,
            span_id="span1",
            method="POST",
            path="/api/test",
            query_params={"foo": "bar"},
            request_headers={"auth": "secret"},
            status_code=201,
            started_at=schema.DateTime.utcnow(),
            duration_ms=100.0,
            response_headers={"content-type": "application/json"},
            response_body={"success": True},
            client_ip="127.0.0.1",
            tags={"env": "test"}
        )

        traces_resource.ingest([span])

        response = self.client.get(
            f"/audit/v1/traces/{trace_id}/spans/span1/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["span_id"], "span1")
        self.assertEqual(data["query_params"], {"foo": "bar"})
        self.assertEqual(data["tags"], {"env": "test"})


class TestAuditTracesSearchContract(unittest.TestCase):
    """HTTP contract tests for GET /audit/v1/traces/search endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager(shared=False)
        cls.manager.initialize()
        cls.app = cls.manager.audit_app

        # Initialize API keys storage
        from campus.audit.resources.apikeys import APIKeysResource
        APIKeysResource.init_storage()

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        # Clear test data - no manual resource initialization needed
        self.manager.clear_test_data()
        assert self.app
        self.client = self.app.test_client()

        # Create a test audit API key for authentication
        from campus.audit.resources.apikeys import APIKeysResource
        _, api_key_value = APIKeysResource().new(
            name="Test Auth Key",
            owner_id="test-user",
            scopes="traces:*",
        )

        # Use the audit API key for authentication
        self.auth_headers = {"Authorization": f"Bearer {api_key_value}"}

        # Clear traces that were emitted during API key creation
        # This ensures tests start with a clean trace state
        traces_storage = campus.storage.tables.get_db("spans")
        traces_storage.delete_matching({})  # Empty query deletes all rows

    def test_search_requires_authentication(self):
        """GET /audit/v1/traces/search requires authentication."""
        response = self.client.get("/audit/v1/traces/search")

        self.assertEqual(response.status_code, 401)

    def test_search_with_no_filters_returns_all_traces(self):
        """GET /audit/v1/traces/search with no filters returns all traces."""
        from campus.audit.resources.traces import TracesResource
        traces_resource = TracesResource()

        spans = [
            TraceSpan(
                trace_id=f"trace{i}" + "a" * 26,
                span_id=f"span{i}",
                method="GET",
                path=f"/api/test{i}",
                status_code=200 if i < 2 else 500,
                started_at=schema.DateTime.utcnow(),
                duration_ms=100.0,
                client_ip="127.0.0.1",
                client_id=f"client{i}" if i < 2 else None,
            )
            for i in range(3)
        ]

        traces_resource.ingest(spans)

        # Disable audit events to avoid authentication side effects when searching
        from campus.common import env
        env.set('AUDIT_EVENTS_ENABLED', '0')

        response = self.client.get(
            "/audit/v1/traces/search",
            headers=self.auth_headers
        )

        # Re-enable audit events
        env.set('AUDIT_EVENTS_ENABLED', '1')

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data["traces"]), 3)

    def test_search_by_path(self):
        """GET /audit/v1/traces/search?path=/api/test1 filters by path."""
        from campus.audit.resources.traces import TracesResource
        traces_resource = TracesResource()

        spans = [
            TraceSpan(
                trace_id=f"trace{i}" + "a" * 26,
                span_id=f"span{i}",
                method="GET",
                path=f"/api/test{i}",
                status_code=200,
                started_at=schema.DateTime.utcnow(),
                duration_ms=100.0,
                client_ip="127.0.0.1",
            )
            for i in range(3)
        ]

        traces_resource.ingest(spans)

        response = self.client.get(
            "/audit/v1/traces/search?path=/api/test1",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data["traces"]), 1)
        self.assertEqual(data["traces"][0]["root_span"]["path"], "/api/test1")

    def test_search_by_status(self):
        """GET /audit/v1/traces/search?status=500 filters by status code."""
        from campus.audit.resources.traces import TracesResource
        traces_resource = TracesResource()

        spans = [
            TraceSpan(
                trace_id=f"trace{i}" + "a" * 26,
                span_id=f"span{i}",
                method="GET",
                path="/api/test",
                status_code=200 if i < 2 else 500,
                started_at=schema.DateTime.utcnow(),
                duration_ms=100.0,
                client_ip="127.0.0.1",
            )
            for i in range(3)
        ]

        traces_resource.ingest(spans)

        response = self.client.get(
            "/audit/v1/traces/search?status=500",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data["traces"]), 1)

    def test_search_by_client_id(self):
        """GET /audit/v1/traces/search?client_id=client0 filters by client."""
        from campus.audit.resources.traces import TracesResource
        traces_resource = TracesResource()

        spans = [
            TraceSpan(
                trace_id=f"trace{i}" + "a" * 26,
                span_id=f"span{i}",
                method="GET",
                path="/api/test",
                status_code=200,
                started_at=schema.DateTime.utcnow(),
                duration_ms=100.0,
                client_ip="127.0.0.1",
                client_id=f"client{i}",
            )
            for i in range(3)
        ]

        traces_resource.ingest(spans)

        response = self.client.get(
            "/audit/v1/traces/search?client_id=client1",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data["traces"]), 1)

    def test_search_with_limit(self):
        """GET /audit/v1/traces/search?limit=2 respects limit."""
        from campus.audit.resources.traces import TracesResource
        traces_resource = TracesResource()

        spans = [
            TraceSpan(
                trace_id=f"trace{i}" + "a" * 26,
                span_id=f"span{i}",
                method="GET",
                path="/api/test",
                status_code=200,
                started_at=schema.DateTime.utcnow(),
                duration_ms=100.0,
                client_ip="127.0.0.1",
            )
            for i in range(5)
        ]

        traces_resource.ingest(spans)

        response = self.client.get(
            "/audit/v1/traces/search?limit=2",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertLessEqual(len(data["traces"]), 2)


class TestAuditTracesCursorPaginationContract(unittest.TestCase):
    """HTTP contract tests for cursor pagination (issue #698).

    Invariants: stable (started_at, trace_id) descending order across
    pages, no duplicates across pages, has_more/next termination, and
    400 responses for malformed cursor/limit input.
    """

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager(shared=False)
        cls.manager.initialize()
        cls.app = cls.manager.audit_app

        # Initialize API keys storage
        from campus.audit.resources.apikeys import APIKeysResource
        APIKeysResource.init_storage()

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        # Clear test data - no manual resource initialization needed
        self.manager.clear_test_data()
        assert self.app
        self.client = self.app.test_client()

        # Disable request tracing for this class: the middleware ingests a
        # span for every test HTTP request (asynchronously), which would
        # pollute exact-content assertions over the spans table.
        from campus.common import env
        env.set('AUDIT_TRACING_ENABLED', '0')

        # Create a test audit API key for authentication
        from campus.audit.resources.apikeys import APIKeysResource
        _, api_key_value = APIKeysResource().new(
            name="Test Auth Key",
            owner_id="test-user",
            scopes="traces:*",
        )

        # Use the audit API key for authentication
        self.auth_headers = {"Authorization": f"Bearer {api_key_value}"}

        # Clear traces that were emitted during API key creation
        traces_storage = campus.storage.tables.get_db("spans")
        traces_storage.delete_matching({})

    def tearDown(self):
        # Restore fixture defaults for other test classes
        from campus.common import env
        env.set('AUDIT_TRACING_ENABLED', '1')

    def _ingest_traces(self, count: int, started_at: str) -> list[str]:
        """Ingest `count` single-span traces sharing a started_at value.

        Trace IDs sort as trace00... < trace01... < ... so the keyset
        walk order is deterministic in tests.
        """
        from campus.audit.resources.traces import TracesResource
        traces_resource = TracesResource()
        spans = [
            TraceSpan(
                trace_id=f"trace{i:02d}" + "a" * 26,
                span_id=f"span{i:02d}" + "b" * 10,
                method="GET",
                path="/api/test",
                status_code=200,
                started_at=schema.DateTime(started_at),
                duration_ms=100.0,
                client_ip="127.0.0.1",
            )
            for i in range(count)
        ]
        traces_resource.ingest(spans)
        return [s.trace_id for s in spans]

    def _walk_pages(self, endpoint: str, page_size: int) -> list[dict]:
        """Follow cursor.next from `endpoint` until has_more is False.

        Disables audit event emission while walking: each authenticated
        request would otherwise ingest new spans and shift the dataset
        mid-walk. Returns the raw page responses in walk order.
        """
        from campus.common import env
        env.set('AUDIT_EVENTS_ENABLED', '0')
        try:
            pages: list[dict] = []
            cursor = None
            while True:
                params = {"limit": str(page_size)}
                if cursor:
                    params["cursor"] = cursor
                response = self.client.get(
                    f"{endpoint}?{urlencode(params)}",
                    headers=self.auth_headers,
                )
                self.assertEqual(response.status_code, 200)
                data = response.get_json()
                # Every page respects the requested page size
                self.assertLessEqual(len(data["traces"]), page_size)
                pages.append(data)
                cursor = data["cursor"]["next"]
                if not data["cursor"]["has_more"]:
                    self.assertIsNone(cursor)
                    break
                # Guard against an infinite walk if the contract regresses
                self.assertLess(len(pages), 100)
                self.assertIsNotNone(cursor)
            return pages
        finally:
            env.set('AUDIT_EVENTS_ENABLED', '1')

    def _assert_cursor_walk_invariants(
            self,
            pages: list[dict],
            expected: set[str],
    ) -> None:
        """Assert cursor invariants over a full page walk.

        Stray traces (e.g. async-ingested spans from earlier requests)
        may appear, so page contents are not asserted exactly. Instead:
        - every page except the last has has_more + next; the last
          terminates with has_more=False, next=None
        - no trace_id appears twice across the whole walk (no dupes)
        - every seeded trace appears exactly once
        - the concatenated order is strictly descending by
          (started_at, trace_id), across page boundaries
        """
        self.assertGreater(len(pages), 0)
        for page in pages[:-1]:
            self.assertTrue(page["cursor"]["has_more"])
            self.assertIsNotNone(page["cursor"]["next"])
        self.assertFalse(pages[-1]["cursor"]["has_more"])
        self.assertIsNone(pages[-1]["cursor"]["next"])

        seen = [t["trace_id"] for p in pages for t in p["traces"]]
        self.assertEqual(len(seen), len(set(seen)), f"duplicate traces: {seen}")
        for trace_id in expected:
            self.assertEqual(seen.count(trace_id), 1, f"{trace_id} not exactly once")

        keys = [
            (t["started_at"], t["trace_id"])
            for p in pages for t in p["traces"]
        ]
        self.assertEqual(keys, sorted(keys, reverse=True), "order not descending")

    def test_search_pages_cover_all_traces_without_duplicates(self):
        """Walking /search cursor pages yields every trace exactly once."""
        expected = set(self._ingest_traces(5, "2023-01-01T10:00:00Z"))

        pages = self._walk_pages("/audit/v1/traces/search", page_size=2)

        self._assert_cursor_walk_invariants(pages, expected)

    def test_list_pages_cover_all_traces_without_duplicates(self):
        """Walking /traces cursor pages yields every trace exactly once."""
        expected = set(self._ingest_traces(5, "2023-01-01T10:00:00Z"))

        pages = self._walk_pages("/audit/v1/traces/", page_size=2)

        self._assert_cursor_walk_invariants(pages, expected)

    def test_same_started_at_traces_do_not_duplicate_across_pages(self):
        """Traces sharing a started_at are tie-broken by trace_id.

        The storage query can only filter started_at (lte); traces at or
        after the cursor key at the same timestamp must be dropped
        in the resource layer, or ties would repeat on every page.
        """
        expected = set(self._ingest_traces(5, "2023-06-01T08:30:00Z"))

        pages = self._walk_pages("/audit/v1/traces/search", page_size=2)

        self._assert_cursor_walk_invariants(pages, expected)

    def test_invalid_cursor_returns_400(self):
        """A malformed cursor token is a 400, not a 500."""
        from campus.common import env
        self._ingest_traces(1, "2023-01-01T10:00:00Z")
        env.set('AUDIT_EVENTS_ENABLED', '0')
        try:
            for cursor in ("garbage", base64.urlsafe_b64encode(b"nojson").decode()):
                with self.subTest(cursor=cursor):
                    response = self.client.get(
                        f"/audit/v1/traces/?{urlencode({'cursor': cursor})}",
                        headers=self.auth_headers,
                    )
                    self.assertEqual(response.status_code, 400)
        finally:
            env.set('AUDIT_EVENTS_ENABLED', '1')

    def test_non_integer_limit_returns_400(self):
        """A non-integer limit is a 400, not a 500."""
        from campus.common import env
        env.set('AUDIT_EVENTS_ENABLED', '0')
        try:
            for endpoint in ("/audit/v1/traces/", "/audit/v1/traces/search"):
                with self.subTest(endpoint=endpoint):
                    response = self.client.get(
                        f"{endpoint}?{urlencode({'limit': 'abc'})}",
                        headers=self.auth_headers,
                    )
                    self.assertEqual(response.status_code, 400)
        finally:
            env.set('AUDIT_EVENTS_ENABLED', '1')

    def test_out_of_range_limits_are_clamped(self):
        """Out-of-range limits clamp to [1, 1000] instead of erroring."""
        from campus.audit.resources.traces import MAX_PAGE_SIZE
        expected = set(self._ingest_traces(3, "2023-01-01T10:00:00Z"))

        from campus.common import env
        env.set('AUDIT_EVENTS_ENABLED', '0')
        try:
            for limit in ("999999", "0", "-5"):
                with self.subTest(limit=limit):
                    response = self.client.get(
                        "/audit/v1/traces/?"
                        + urlencode({"limit": limit}),
                        headers=self.auth_headers,
                    )
                    self.assertEqual(response.status_code, 200)
                    traces = response.get_json()["traces"]
                    self.assertGreaterEqual(
                        len(traces), 1, f"limit={limit} returned no traces"
                    )
                    seen = {t["trace_id"] for t in traces}
                    self.assertLessEqual(len(traces), MAX_PAGE_SIZE)
                    if limit == "999999":
                        # Clamped to MAX_PAGE_SIZE: nothing may be cut
                        self.assertTrue(
                            expected.issubset(seen),
                            f"oversized limit cut traces: {expected - seen}",
                        )
        finally:
            env.set('AUDIT_EVENTS_ENABLED', '1')



class TestAuditTracesScopeEnforcement(unittest.TestCase):
    """Scope enforcement on trace endpoints (#575).

    API keys authenticate with scopes; trace endpoints require
    traces:read for queries and traces:write for ingestion. Wildcard
    key scopes (traces:*, *) satisfy both.
    """

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager(shared=False)
        cls.manager.initialize()
        cls.app = cls.manager.audit_app

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        self.manager.clear_test_data()
        assert self.app
        self.client = self.app.test_client()

    def _make_span(self):
        """Minimal valid span payload for ingestion."""
        return {
            "trace_id": "a" * 32,
            "span_id": "b" * 16,
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
            "user_agent": "test-agent",
            "error_message": None,
            "tags": {},
        }

    def _make_key(self, scopes: str) -> dict:
        """Create an audit API key with the given scopes; return headers."""
        from campus.audit.resources.apikeys import APIKeysResource
        _, api_key_value = APIKeysResource().new(
            name=f"Scope Test Key ({scopes})",
            owner_id="test-user",
            scopes=scopes,
        )
        return {"Authorization": f"Bearer {api_key_value}"}

    def test_read_only_key_can_list_but_not_ingest(self):
        """A traces:read key gets 200 on GET and 403 on POST."""
        headers = self._make_key("traces:read")

        response = self.client.get(
            "/audit/v1/traces/",
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            "/audit/v1/traces/",
            json={"spans": [self._make_span()]},
            headers=headers,
        )
        self.assertEqual(response.status_code, 403)

    def test_write_only_key_can_ingest_but_not_list(self):
        """A traces:write key gets 201 on POST and 403 on GET."""
        headers = self._make_key("traces:write")

        response = self.client.post(
            "/audit/v1/traces/",
            json={"spans": [self._make_span()]},
            headers=headers,
        )
        self.assertEqual(response.status_code, 201)

        response = self.client.get(
            "/audit/v1/traces/",
            headers=headers,
        )
        self.assertEqual(response.status_code, 403)

    def test_unscoped_key_is_denied(self):
        """A key with an unrelated scope is denied on trace endpoints."""
        headers = self._make_key("metrics:read")

        response = self.client.get(
            "/audit/v1/traces/",
            headers=headers,
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_wildcard_scope_gets_full_access(self):
        """A "*" key scope satisfies both read and write requirements."""
        headers = self._make_key("*")

        response = self.client.post(
            "/audit/v1/traces/",
            json={"spans": [self._make_span()]},
            headers=headers,
        )
        self.assertEqual(response.status_code, 201)

        response = self.client.get(
            "/audit/v1/traces/",
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
