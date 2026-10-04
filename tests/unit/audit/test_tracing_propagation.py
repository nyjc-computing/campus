"""Pure unit tests for trace context propagation.

Covers the #794 propagation seam in campus.audit.middleware.tracing:
- start_span() intake of X-Request-ID / X-Parent-Span-ID headers
- propagation_headers() for outbound requests
- instrument_requests_session() wrapping of requests.Session

No storage, network, or audit-service involvement.
"""

import unittest

import flask
import requests

from campus.audit.middleware import tracing


class TestStartSpanContextIntake(unittest.TestCase):
    """start_span() reads trace context headers into flask.g."""

    def setUp(self):
        self.app = flask.Flask(__name__)

    def test_start_span_records_parent_from_header(self):
        """A request with context headers becomes a child span."""
        with self.app.test_request_context("/", headers={
            tracing.TRACE_ID_HEADER: "a" * 32,
            tracing.PARENT_SPAN_ID_HEADER: "c" * 16,
        }):
            tracing.start_span()

            self.assertEqual(flask.g.trace_id, "a" * 32)
            self.assertEqual(flask.g.parent_span_id, "c" * 16)
            self.assertIsNotNone(flask.g.trace_started_at)

    def test_start_span_without_headers_is_root(self):
        """A request without context headers starts a new root span."""
        with self.app.test_request_context("/"):
            tracing.start_span()

            self.assertEqual(len(flask.g.trace_id), 32)
            self.assertIsNone(flask.g.parent_span_id)

    def test_started_at_is_wall_clock_before_response(self):
        """trace_started_at is captured at request start, not ingestion."""
        with self.app.test_request_context("/"):
            tracing.start_span()
            started_at = flask.g.trace_started_at
            # str subclass carrying an ISO timestamp
            self.assertTrue(str(started_at))


class TestPropagationHeaders(unittest.TestCase):
    """propagation_headers() reflects the active traced request."""

    def setUp(self):
        self.app = flask.Flask(__name__)

    def test_empty_outside_request_context(self):
        """No headers when called outside a request context."""
        self.assertEqual(tracing.propagation_headers(), {})

    def test_empty_when_span_not_started(self):
        """No headers when the request has no active span."""
        with self.app.test_request_context("/"):
            self.assertEqual(tracing.propagation_headers(), {})

    def test_headers_inside_traced_request(self):
        """Trace and parent-span headers carry the current span context."""
        with self.app.test_request_context("/"):
            flask.g.trace_id = "a" * 32
            flask.g.span_id = "b" * 16

            self.assertEqual(tracing.propagation_headers(), {
                tracing.TRACE_ID_HEADER: "a" * 32,
                tracing.PARENT_SPAN_ID_HEADER: "b" * 16,
            })


class TestInstrumentRequestsSession(unittest.TestCase):
    """instrument_requests_session() wraps Session.request."""

    def setUp(self):
        self.app = flask.Flask(__name__)

    def _stub_session(self, captured: dict) -> requests.Session:
        """Session whose request method records kwargs instead of sending."""
        session = requests.Session()

        def original_request(method, url, **kwargs):
            captured["method"] = method
            captured["url"] = url
            captured.update(kwargs)
            return "response"

        session.request = original_request
        return session

    def test_injects_headers_within_traced_request(self):
        captured: dict = {}
        session = self._stub_session(captured)

        self.assertTrue(tracing.instrument_requests_session(session))

        with self.app.test_request_context("/"):
            flask.g.trace_id = "a" * 32
            flask.g.span_id = "b" * 16
            result = session.request("GET", "https://example.test/path")

        self.assertEqual(result, "response")
        self.assertEqual(captured["headers"], {
            tracing.TRACE_ID_HEADER: "a" * 32,
            tracing.PARENT_SPAN_ID_HEADER: "b" * 16,
        })

    def test_leaves_headers_untouched_outside_request(self):
        captured: dict = {}
        session = self._stub_session(captured)
        tracing.instrument_requests_session(session)

        session.request("GET", "https://example.test/path")

        self.assertNotIn("headers", captured)

    def test_preserves_caller_headers(self):
        """Caller-supplied headers win; context headers fill the gaps."""
        captured: dict = {}
        session = self._stub_session(captured)
        tracing.instrument_requests_session(session)

        with self.app.test_request_context("/"):
            flask.g.trace_id = "a" * 32
            flask.g.span_id = "b" * 16
            session.request(
                "GET",
                "https://example.test/path",
                headers={"X-Custom": "yes"},
            )

        self.assertEqual(captured["headers"], {
            "X-Custom": "yes",
            tracing.TRACE_ID_HEADER: "a" * 32,
            tracing.PARENT_SPAN_ID_HEADER: "b" * 16,
        })

    def test_does_not_clobber_caller_trace_id(self):
        """An explicitly set X-Request-ID is not overwritten."""
        captured: dict = {}
        session = self._stub_session(captured)
        tracing.instrument_requests_session(session)

        with self.app.test_request_context("/"):
            flask.g.trace_id = "a" * 32
            flask.g.span_id = "b" * 16
            session.request(
                "GET",
                "https://example.test/path",
                headers={tracing.TRACE_ID_HEADER: "f" * 32},
            )

        self.assertEqual(
            captured["headers"][tracing.TRACE_ID_HEADER], "f" * 32
        )

    def test_instrumentation_is_idempotent(self):
        session = requests.Session()

        self.assertTrue(tracing.instrument_requests_session(session))
        self.assertFalse(tracing.instrument_requests_session(session))


class TestSpanIdentityEnrichment(unittest.TestCase):
    """build_span_from_context() maps the authenticated caller onto the span.

    The shared Authenticator glue stashes full client/user objects under
    flask.g.current_client/current_user (#802): resource dicts via the
    SDK (campus.api), model objects in-process (campus.auth).
    """

    def setUp(self):
        self.app = flask.Flask(__name__)

    def _build_span(self) -> dict:
        with self.app.test_request_context("/"):
            tracing.start_span()
            span = tracing.build_span_from_context(
                flask.g.trace_id,
                flask.g.span_id,
                flask.Response(status=200),
                duration_ms=1.0,
            )
        return span

    def test_dict_identities_mapped(self):
        """Resource-dict identities (SDK path) land on the span by id."""
        with self.app.test_request_context("/"):
            tracing.start_span()
            flask.g.current_client = {"id": "client-x", "name": "X"}
            flask.g.current_user = {"id": "user-y"}
            span = tracing.build_span_from_context(
                flask.g.trace_id,
                flask.g.span_id,
                flask.Response(status=200),
                duration_ms=1.0,
            )

        self.assertEqual(span["client_id"], "client-x")
        self.assertEqual(span["user_id"], "user-y")

    def test_object_identities_mapped(self):
        """Model-object identities (auth in-process path) land by id."""
        from types import SimpleNamespace

        with self.app.test_request_context("/"):
            tracing.start_span()
            flask.g.current_client = SimpleNamespace(id="client-x")
            flask.g.current_user = SimpleNamespace(id="user-y")
            span = tracing.build_span_from_context(
                flask.g.trace_id,
                flask.g.span_id,
                flask.Response(status=200),
                duration_ms=1.0,
            )

        self.assertEqual(span["client_id"], "client-x")
        self.assertEqual(span["user_id"], "user-y")

    def test_unauthenticated_span_has_no_identity(self):
        """No Authenticator stash, no identity on the span."""
        span = self._build_span()

        self.assertIsNone(span["client_id"])
        self.assertIsNone(span["user_id"])

    def test_client_only_identity(self):
        """Basic-auth requests carry a client but no user."""
        with self.app.test_request_context("/"):
            tracing.start_span()
            flask.g.current_client = {"id": "client-x"}
            span = tracing.build_span_from_context(
                flask.g.trace_id,
                flask.g.span_id,
                flask.Response(status=200),
                duration_ms=1.0,
            )

        self.assertEqual(span["client_id"], "client-x")
        self.assertIsNone(span["user_id"])

    def test_direct_id_attributes_still_supported(self):
        """Deployment glue stashing plain ids under client_id/user_id works."""
        with self.app.test_request_context("/"):
            tracing.start_span()
            flask.g.client_id = "client-x"
            flask.g.user_id = "user-y"
            span = tracing.build_span_from_context(
                flask.g.trace_id,
                flask.g.span_id,
                flask.Response(status=200),
                duration_ms=1.0,
            )

        self.assertEqual(span["client_id"], "client-x")
        self.assertEqual(span["user_id"], "user-y")


if __name__ == "__main__":
    unittest.main()
