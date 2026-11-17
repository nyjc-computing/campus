"""Tests for producer-side redaction of the audit service's own events
(#1124).

The audit-event producer previously stored request headers (every
caller's Authorization, signed cookies) and response bodies (the
plaintext newly-minted API keys) verbatim into the student-readable
trail. emit_audit_event now scrubs every context field through the
shared keyed redaction, drops Authorization outright, and drops the
response body for the apikeys event family (the minted key rides under
bare "key" on /regenerate, outside keyed redaction's deliberate #806
gap).

These tests capture the ingested span by monkeypatching the lazy
traces-resource import seam. No storage or network.
"""

import unittest

from campus.audit.helpers import audit_events
from campus.common import env


def _capture_ingested_spans():
    """Patch traces.ingest to capture spans; return (spans, restore)."""
    from campus.audit.resources import traces

    captured: list = []
    original = traces.ingest
    traces.ingest = lambda spans: captured.extend(spans)
    return captured, lambda: setattr(traces, "ingest", original)


class TestAuditEventRedaction(unittest.TestCase):
    """emit_audit_event stores no secrets (#1124)."""

    def setUp(self):
        self._original_flag = env.get("AUDIT_EVENTS_ENABLED")
        env.set("AUDIT_EVENTS_ENABLED", "1")

    def tearDown(self):
        if self._original_flag is not None:
            env.set("AUDIT_EVENTS_ENABLED", self._original_flag)

    def _emit(self, *, event_type, body, response_body, **kwargs):
        from campus.common import schema

        spans, restore = _capture_ingested_spans()
        try:
            audit_events.emit_audit_event(
                data={"event_type": event_type, "endpoint": "test"},
                api_key_id="key-1",
                started_at=schema.DateTime.utcnow(),
                duration_ms=1.0,
                request_context={
                    "method": "POST",
                    "path": "/audit/v1/test",
                    "urlparams": dict(kwargs.get("urlparams", {})),
                    "client_ip": "127.0.0.1",
                    "user_agent": "test",
                    "headers": kwargs.get("headers", {}),
                    "body": body,
                },
                response_context={
                    "status_code": 201,
                    "headers": {"Set-Cookie": "sid=xyz"},
                    "body": response_body,
                },
            )
        finally:
            restore()
        assert spans, "emit_audit_event ingested nothing"
        span = spans[0]
        return span.to_resource() if hasattr(span, "to_resource") else dict(span)

    def test_authorization_header_dropped(self):
        span = self._emit(
            event_type="audit.traces.ingest",
            body={},
            response_body={},
            headers={
                "Authorization": "Bearer audit_v1_supersecret",
                "Accept": "application/json",
            },
        )
        headers = span["request_headers"]
        self.assertNotIn("Authorization", headers)
        self.assertNotIn("audit_v1_supersecret", str(headers))
        self.assertEqual(headers.get("Accept"), "application/json")

    def test_cookie_and_api_key_headers_key_redacted(self):
        span = self._emit(
            event_type="audit.traces.ingest",
            body={},
            response_body={},
            headers={
                "Cookie": "session=signed-value",
                "X-Api-Key": "audit_v1_reader",
            },
        )
        headers = span["request_headers"]
        self.assertEqual(headers["Cookie"], "[REDACTED]")
        self.assertEqual(headers["X-Api-Key"], "[REDACTED]")

    def test_request_body_redacted(self):
        span = self._emit(
            event_type="audit.traces.ingest",
            body={"label": "ci", "otp": "123456",
                  "email": "personal@gmail.com"},
            response_body={},
            headers={},
        )
        body = span["request_body"]
        self.assertEqual(body["label"], "ci")
        self.assertEqual(body["otp"], "[REDACTED]")
        self.assertEqual(body["email"], "[REDACTED]")

    def test_create_response_body_dropped(self):
        """POST /apikeys/ returns record["api_key"]: never stored."""
        span = self._emit(
            event_type="audit.apikeys.new",
            body={"name": "portal-ui"},
            response_body={"id": "key-1", "api_key": "audit_v1_NEWPLAINTEXT"},
            headers={},
        )
        self.assertEqual(span["response_body"], {})
        self.assertNotIn("audit_v1_NEWPLAINTEXT", str(span))

    def test_regenerate_response_body_dropped(self):
        """/regenerate returns {"key": ...} — bare "key" is outside keyed
        redaction (#806), so the apikeys family drops the body outright."""
        span = self._emit(
            event_type="audit.apikeys.regenerate",
            body={},
            response_body={"key": "audit_v1_NEWPLAINTEXT"},
            headers={},
        )
        self.assertEqual(span["response_body"], {})
        self.assertNotIn("audit_v1_NEWPLAINTEXT", str(span))

    def test_non_apikeys_response_body_kept_but_redacted(self):
        """Other event types keep their (redacted) response bodies."""
        span = self._emit(
            event_type="audit.sessions.update",
            body={},
            response_body={"user_id": "student@nyjc.edu.sg",
                           "authorization_code": "4/0Ab_5qn"},
            headers={},
        )
        self.assertEqual(
            span["response_body"],
            {"user_id": "student@nyjc.edu.sg",
             "authorization_code": "[REDACTED]"},
        )

    def test_response_headers_redacted(self):
        span = self._emit(
            event_type="audit.traces.ingest",
            body={},
            response_body={},
            headers={},
        )
        self.assertEqual(span["response_headers"]["Set-Cookie"], "[REDACTED]")

    def test_tags_redacted(self):
        span = self._emit(
            event_type="audit.traces.ingest",
            body={},
            response_body={},
            headers={},
        )
        self.assertEqual(span["tags"]["event_type"], "audit.traces.ingest")

    def test_span_metadata_intact(self):
        span = self._emit(
            event_type="audit.traces.ingest",
            body={},
            response_body={},
            headers={},
        )
        self.assertEqual(span["method"], "POST")
        self.assertEqual(span["path"], "/audit/v1/test")
        self.assertEqual(span["status_code"], 201)
        self.assertEqual(span["api_key_id"], "key-1")


if __name__ == "__main__":
    unittest.main()
