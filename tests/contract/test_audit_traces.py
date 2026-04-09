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

import unittest

from campus.common import env, schema
from campus.model import TraceSpan
from tests.fixtures import services
from tests.fixtures.tokens import get_basic_auth_headers


class TestAuditHealthContract(unittest.TestCase):
    """HTTP contract tests for /audit/v1/health endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.setup()
        # Note: audit_app is created as part of the ServiceManager setup
        cls.app = cls.manager.audit_app

    @classmethod
    def tearDownClass(cls):
        cls.manager.close()
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

    def setUp(self):
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
        cls.manager = services.create_service_manager()
        cls.manager.setup()
        cls.app = cls.manager.audit_app

        # Initialize traces storage
        from campus.audit.resources.traces import TracesResource
        TracesResource.init_storage()

    @classmethod
    def tearDownClass(cls):
        cls.manager.close()
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

    def setUp(self):
        self.client = self.app.test_client()
        self.auth_headers = get_basic_auth_headers(env.CLIENT_ID, env.CLIENT_SECRET)

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
        """POST /audit/v1/traces requires authentication."""
        response = self.client.post(
            "/audit/v1/traces",
            json={"spans": [self._make_test_span()]}
        )

        self.assertEqual(response.status_code, 401)

    def test_ingest_single_span_success(self):
        """POST /audit/v1/traces with single span returns 201."""
        response = self.client.post(
            "/audit/v1/traces",
            json={"spans": [self._make_test_span()]},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertIn("created", data)
        self.assertEqual(len(data["created"]), 1)
        self.assertNotIn("failed", data)

    def test_ingest_batch_spans_success(self):
        """POST /audit/v1/traces with multiple spans returns 201."""
        spans = [
            self._make_test_span(span_id=f"span{i}", trace_id=f"trace{i}")
            for i in range(3)
        ]

        response = self.client.post(
            "/audit/v1/traces",
            json={"spans": spans},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(len(data["created"]), 3)

    def test_ingest_missing_spans_field_returns_error(self):
        """POST /audit/v1/traces without 'spans' field returns 400."""
        response = self.client.post(
            "/audit/v1/traces",
            json={},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 400)

    def test_ingest_invalid_span_returns_error(self):
        """POST /audit/v1/traces with invalid span data returns 400."""
        response = self.client.post(
            "/audit/v1/traces",
            json={"spans": [{"invalid": "data"}]},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 400)


class TestAuditTracesListContract(unittest.TestCase):
    """HTTP contract tests for GET /audit/v1/traces endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.setup()
        cls.app = cls.manager.audit_app

        # Initialize traces storage
        from campus.audit.resources.traces import TracesResource
        TracesResource.init_storage()

    @classmethod
    def tearDownClass(cls):
        cls.manager.close()
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

    def setUp(self):
        self.client = self.app.test_client()
        self.auth_headers = get_basic_auth_headers(env.CLIENT_ID, env.CLIENT_SECRET)

    def test_list_traces_requires_authentication(self):
        """GET /audit/v1/traces requires authentication."""
        response = self.client.get("/audit/v1/traces")

        self.assertEqual(response.status_code, 401)

    def test_list_traces_empty_returns_empty_list(self):
        """GET /audit/v1/traces with no traces returns empty list."""
        response = self.client.get(
            "/audit/v1/traces",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["traces"], [])
        self.assertIn("cursor", data)

    def test_list_traces_returns_trace_summaries(self):
        """GET /audit/v1/traces returns trace summaries with cursor."""
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

        # Then list traces
        response = self.client.get(
            "/audit/v1/traces",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data["traces"]), 1)
        self.assertEqual(data["traces"][0]["trace_id"], "a" * 32)
        self.assertIn("cursor", data)

    def test_list_traces_with_limit(self):
        """GET /audit/v1/traces?limit=5 respects limit parameter."""
        response = self.client.get(
            "/audit/v1/traces?limit=5",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertLessEqual(len(data["traces"]), 5)


class TestAuditTracesGetTreeContract(unittest.TestCase):
    """HTTP contract tests for GET /audit/v1/traces/<trace_id>/ endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.setup()
        cls.app = cls.manager.audit_app

        # Initialize traces storage
        from campus.audit.resources.traces import TracesResource
        TracesResource.init_storage()

    @classmethod
    def tearDownClass(cls):
        cls.manager.close()
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

    def setUp(self):
        self.client = self.app.test_client()
        self.auth_headers = get_basic_auth_headers(env.CLIENT_ID, env.CLIENT_SECRET)

    def test_get_trace_requires_authentication(self):
        """GET /audit/v1/traces/<id> requires authentication."""
        response = self.client.get("/audit/v1/traces/abc123")

        self.assertEqual(response.status_code, 401)

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
        cls.manager = services.create_service_manager()
        cls.manager.setup()
        cls.app = cls.manager.audit_app

        # Initialize traces storage
        from campus.audit.resources.traces import TracesResource
        TracesResource.init_storage()

    @classmethod
    def tearDownClass(cls):
        cls.manager.close()
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

    def setUp(self):
        self.client = self.app.test_client()
        self.auth_headers = get_basic_auth_headers(env.CLIENT_ID, env.CLIENT_SECRET)

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
        cls.manager = services.create_service_manager()
        cls.manager.setup()
        cls.app = cls.manager.audit_app

        # Initialize traces storage
        from campus.audit.resources.traces import TracesResource
        TracesResource.init_storage()

    @classmethod
    def tearDownClass(cls):
        cls.manager.close()
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

    def setUp(self):
        self.client = self.app.test_client()
        self.auth_headers = get_basic_auth_headers(env.CLIENT_ID, env.CLIENT_SECRET)

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
        cls.manager = services.create_service_manager()
        cls.manager.setup()
        cls.app = cls.manager.audit_app

        # Initialize traces storage
        from campus.audit.resources.traces import TracesResource
        TracesResource.init_storage()

    @classmethod
    def tearDownClass(cls):
        cls.manager.close()
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

    def setUp(self):
        self.client = self.app.test_client()
        self.auth_headers = get_basic_auth_headers(env.CLIENT_ID, env.CLIENT_SECRET)

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

        response = self.client.get(
            "/audit/v1/traces/search",
            headers=self.auth_headers
        )

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
