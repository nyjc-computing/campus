"""Tests for what the audit service records about its own API (#1243).

campus.audit's events are its record of who used which key to read or
change the audit trail. Three things are pinned here because each one
cost or hid something before:

- Failures are recorded. ``emit_from_flask`` used to drop every 4XX/5XX
  response, although the decorator's docstring promised the opposite, so
  a 429 or a 403 left no event at all.
- A successful read keeps no copy of what it returned. The response is a
  page of traces that are already stored; one search event measured
  173 KB on development for that reason.
- A rejected ingest keeps the batch it refused, but only its first 64 KB.

These tests capture the ingested span by monkeypatching the lazy
traces-resource import seam, as test_event_emission_redaction does.
No storage or network.
"""

import json
import unittest

import flask

from campus.audit.helpers import audit_events
from campus.common import env, schema

ALL_STATUSES = (200, 201, 207, 302, 400, 401, 403, 404, 409, 422, 429, 500, 503)
FAILURE_STATUSES = (400, 401, 403, 404, 409, 422, 429, 500, 503)
ERROR_ENVELOPE = {"error": {"code": "NOT_FOUND", "message": "no such trace"}}


def _capture_ingested_spans():
    """Patch traces.ingest to capture spans; return (spans, restore)."""
    from campus.audit.resources import traces

    captured: list = []
    original = traces.ingest
    traces.ingest = lambda spans: captured.extend(spans)
    return captured, lambda: setattr(traces, "ingest", original)


def _response(status: int, payload) -> flask.Response:
    return flask.Response(
        json.dumps(payload), status=status, mimetype="application/json",
    )


class _EventPolicyTestCase(unittest.TestCase):
    def setUp(self):
        self._original_flag = env.get("AUDIT_EVENTS_ENABLED")
        env.set("AUDIT_EVENTS_ENABLED", "1")
        self.app = flask.Flask(__name__)

    def tearDown(self):
        if self._original_flag is not None:
            env.set("AUDIT_EVENTS_ENABLED", self._original_flag)


class TestEmitFromFlaskPolicy(_EventPolicyTestCase):
    """emit_from_flask records failures and can drop bodies on success."""

    def _emit(self, status, *, request_body=None, response_payload=None,
              event_type="audit.traces.search", **policy):
        spans, restore = _capture_ingested_spans()
        try:
            path = "/audit/v1/traces/search"
            with self.app.test_request_context(path, method="POST",
                                               json=request_body):
                audit_events.emit_from_flask(
                    None,
                    _response(status, response_payload or {}),
                    event_type=event_type,
                    data={"status_code": status},
                    api_key_id="key-1",
                    started_at=schema.DateTime.utcnow(),
                    duration_ms=1.0,
                    **policy,
                )
        finally:
            restore()
        return spans

    def test_every_status_is_recorded_by_default(self):
        for status in ALL_STATUSES:
            with self.subTest(status=status):
                spans = self._emit(status)
                self.assertEqual(len(spans), 1)
                self.assertEqual(spans[0].status_code, status)

    def test_on_success_false_keeps_only_failures(self):
        for status in (200, 201, 207, 302):
            with self.subTest(status=status):
                self.assertEqual(
                    self._emit(status, on_success=False), [],
                )
        for status in FAILURE_STATUSES:
            with self.subTest(status=status):
                self.assertEqual(len(self._emit(status, on_success=False)), 1)

    def test_bodies_on_success_false_drops_bodies_on_success_only(self):
        request_body = {"filter": "today"}
        response_payload = {"traces": [{"trace_id": "a" * 32}]}
        policy = {"bodies_on_success": False}

        success = self._emit(
            200, request_body=request_body, response_payload=response_payload,
            **policy,
        )[0]
        self.assertEqual(success.request_body, {})
        self.assertEqual(success.response_body, {})

        failure = self._emit(
            404, request_body=request_body, response_payload=ERROR_ENVELOPE,
            **policy,
        )[0]
        self.assertEqual(failure.request_body, request_body)
        self.assertEqual(failure.response_body, ERROR_ENVELOPE)

    def test_bodies_are_kept_by_default(self):
        response_payload = {"traces": [{"trace_id": "a" * 32}]}
        span = self._emit(200, response_payload=response_payload)[0]
        self.assertEqual(span.response_body, response_payload)

    def test_event_type_rides_in_the_tags(self):
        span = self._emit(429, response_payload=ERROR_ENVELOPE)[0]
        self.assertEqual(span.tags["event_type"], "audit.traces.search")
        self.assertEqual(span.tags["status_code"], 429)
        self.assertEqual(span.api_key_id, "key-1")


class TestRejectedIngestBody(_EventPolicyTestCase):
    """A rejected ingest keeps a bounded prefix of the batch it refused."""

    def _batch(self, count, *, padding=1024):
        return {
            "spans": [
                {"span_id": f"{i:016x}", "path": "/x", "pad": "p" * padding}
                for i in range(count)
            ]
        }

    def test_a_small_batch_is_kept_whole(self):
        body = self._batch(3)
        self.assertIs(audit_events._truncate_span_batch(body), body)

    def test_a_large_batch_keeps_its_leading_spans_and_says_so(self):
        body = self._batch(200)
        kept = audit_events._truncate_span_batch(body)
        self.assertLess(len(kept["spans"]), 200)
        self.assertGreater(len(kept["spans"]), 1)
        self.assertEqual(kept["_truncated"], f"{len(kept['spans'])} of 200 spans kept")
        self.assertEqual(kept["spans"][0]["span_id"], f"{0:016x}")

    def test_one_oversized_span_is_still_kept(self):
        """The evidence survives even when a single span caused the reject."""
        body = {"spans": [{"span_id": "a" * 16, "pad": "p" * 200_000}]}
        kept = audit_events._truncate_span_batch(body)
        self.assertEqual(len(kept["spans"]), 1)

    def test_anything_that_is_not_a_span_batch_passes_through(self):
        for body in ({"note": "x"}, {"spans": "not a list"}, ["a"], "text", None):
            with self.subTest(body=body):
                self.assertIs(audit_events._truncate_span_batch(body), body)

    def test_the_truncation_reaches_the_stored_event(self):
        spans, restore = _capture_ingested_spans()
        try:
            path = "/audit/v1/traces/"
            with self.app.test_request_context(path, method="POST",
                                               json=self._batch(200)):
                audit_events.emit_from_flask(
                    None,
                    _response(400, ERROR_ENVELOPE),
                    event_type="audit.traces.ingest",
                    data={"status_code": 400},
                    api_key_id="key-1",
                    started_at=schema.DateTime.utcnow(),
                    duration_ms=1.0,
                    on_success=False,
                )
        finally:
            restore()
        self.assertEqual(len(spans), 1)
        stored = spans[0].request_body
        self.assertIn("_truncated", stored)
        self.assertLess(len(stored["spans"]), 200)


class TestAuditEventDecoratorPolicy(_EventPolicyTestCase):
    """The decorator passes its policy through on a real request."""

    def _register(self, status, **policy):
        @audit_events.audit_event("audit.traces.search", **policy)
        def view(**_):
            return {"rows": [1, 2, 3]}, status

        rule = f"/probe/{status}"
        self.app.add_url_rule(rule, f"probe{status}", view)
        return rule

    def _get(self, rule):
        spans, restore = _capture_ingested_spans()
        try:
            response = self.app.test_client().get(rule)
        finally:
            restore()
        return response, spans

    def test_default_records_success_with_its_response(self):
        response, spans = self._get(self._register(200))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].response_body, {"rows": [1, 2, 3]})

    def test_on_success_false_skips_success(self):
        _, spans = self._get(self._register(201, on_success=False))
        self.assertEqual(spans, [])

    def test_on_success_false_still_records_failure(self):
        response, spans = self._get(self._register(429, on_success=False))
        self.assertEqual(response.status_code, 429)
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].status_code, 429)

    def test_bodies_on_success_false_drops_the_response_on_success(self):
        _, spans = self._get(self._register(200, bodies_on_success=False))
        self.assertEqual(spans[0].response_body, {})

    def test_bodies_on_success_false_keeps_the_error_on_failure(self):
        _, spans = self._get(self._register(404, bodies_on_success=False))
        self.assertEqual(spans[0].response_body, {"rows": [1, 2, 3]})


if __name__ == "__main__":
    unittest.main()
