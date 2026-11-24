"""HTTP contract tests for what campus.audit stamps at ingest and for
what it records about its own API (#1243, #1244).

Two behaviors meet at POST /audit/v1/traces/:

- The stamps. Every stored span carries ``tags.producer_id``, the API
  key that delivered it — the attribution a producer cannot get wrong —
  and, when the request carried ``X-Request-Start``, ``tags.queue_ms``,
  the wait between the request's arrival and the span's start. Before
  this, a stored span did not say which service produced it.
- The self-events. campus.audit's own events are its record of who used
  which key. A successful ingest writes none (the spans are the record),
  a rejected one writes one carrying the batch it refused, a successful
  authentication writes no event of its own (the route event records the
  key), and a successful read keeps no copy of what it returned.
"""

import unittest
from contextlib import suppress

import campus.storage
from campus.common import env
from tests.fixtures import services
from tests.fixtures.audit_events import get_audit_spans

STARTED_AT = "2026-11-24T10:17:58.349921+00:00"
# The two stored forms of X-Request-Start, each paired with a hex span
# id: Railway's edge sends bare epoch milliseconds, the former gateway
# stamp sent t=<seconds.milliseconds>.
ARRIVAL_FORMS = (
    ("edge", "1795515478341", "e" * 16),
    ("gateway", "t=1795515478.341", "f" * 16),
)


class _AuditAppTestCase(unittest.TestCase):
    """A private audit app with one all-scopes key and an empty spans table."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager(shared=False)
        cls.manager.initialize()
        cls.app = cls.manager.audit_app

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

        from campus.audit.resources.apikeys import APIKeysResource
        api_key_model, api_key_value = APIKeysResource().new(
            name="Producer Key",
            owner_id="test-user",
            scopes="traces:*",
        )
        self.api_key_id = api_key_model.id
        self.auth_headers = {"Authorization": f"Bearer {api_key_value}"}

        # Drop the events the key creation wrote, so each test starts
        # with only the rows it creates itself.
        self.spans = campus.storage.tables.get_db("spans")
        with suppress(campus.storage.errors.StorageError):
            self.spans.delete_matching({})

    def _span(self, span_id="b" * 16, *, request_headers=None, tags=None,
              trace_id="a" * 32):
        return {
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": None,
            "method": "GET",
            "path": "/api/v1/test",
            "query_params": {},
            "request_headers": dict(request_headers or {}),
            "request_body": None,
            "status_code": 200,
            "response_headers": {},
            "response_body": None,
            "started_at": STARTED_AT,
            "duration_ms": 100.0,
            "api_key_id": None,
            "client_id": None,
            "user_id": None,
            "client_ip": "127.0.0.1",
            "user_agent": "test-agent",
            "error_message": None,
            "tags": dict(tags or {}),
        }

    def _ingest(self, *spans, headers=None):
        return self.client.post(
            "/audit/v1/traces/",
            json={"spans": list(spans)},
            headers=headers or self.auth_headers,
        )

    def _stored(self, span_id):
        return self.spans.get_matching({"span_id": span_id})[0]


class TestIngestStampsContract(_AuditAppTestCase):
    """POST /audit/v1/traces/ stamps every span it stores."""

    def test_ingested_span_carries_the_delivering_key(self):
        response = self._ingest(self._span())
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            self._stored("b" * 16)["tags"]["producer_id"], self.api_key_id,
        )

    def test_every_span_in_a_batch_is_stamped(self):
        response = self._ingest(
            self._span("b" * 16, trace_id="1" * 32),
            self._span("c" * 16, trace_id="2" * 32),
        )
        self.assertEqual(response.status_code, 201)
        for span_id in ("b" * 16, "c" * 16):
            with self.subTest(span_id=span_id):
                self.assertEqual(
                    self._stored(span_id)["tags"]["producer_id"],
                    self.api_key_id,
                )

    def test_queue_ms_from_either_form_of_request_start(self):
        for form, header_value, span_id in ARRIVAL_FORMS:
            with self.subTest(form=form):
                response = self._ingest(self._span(
                    span_id, request_headers={"X-Request-Start": header_value},
                ))
                self.assertEqual(response.status_code, 201)
                self.assertAlmostEqual(
                    self._stored(span_id)["tags"]["queue_ms"], 8.921, places=2,
                )

    def test_no_arrival_header_means_no_queue_stamp(self):
        self._ingest(self._span())
        self.assertNotIn("queue_ms", self._stored("b" * 16)["tags"])

    def test_producer_supplied_stamps_are_replaced(self):
        self._ingest(self._span(tags={
            "producer_id": "uid-spoofed",
            "queue_ms": -1.0,
            "journey_id": "journey-1",
        }))
        tags = self._stored("b" * 16)["tags"]
        self.assertEqual(tags["producer_id"], self.api_key_id)
        self.assertNotIn("queue_ms", tags)
        self.assertEqual(tags["journey_id"], "journey-1")

    def test_the_stamps_show_on_the_read_surface(self):
        self._ingest(self._span(
            request_headers={"X-Request-Start": ARRIVAL_FORMS[0][1]},
        ))
        response = self.client.get(
            "/audit/v1/traces/search?events=false", headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        traces = response.get_json()["traces"]
        self.assertEqual(len(traces), 1)
        tags = traces[0]["root_span"]["tags"]
        self.assertEqual(tags["producer_id"], self.api_key_id)
        self.assertAlmostEqual(tags["queue_ms"], 8.921, places=2)


class TestSelfEventsContract(_AuditAppTestCase):
    """What campus.audit records about calls to its own API."""

    def test_successful_ingest_writes_no_event(self):
        response = self._ingest(self._span())
        self.assertEqual(response.status_code, 201)
        self.assertEqual(get_audit_spans("audit.traces.ingest"), [])

    def test_rejected_ingest_writes_an_event_with_the_batch(self):
        invalid = self._span("d" * 16)
        del invalid["method"]
        response = self._ingest(invalid)
        self.assertEqual(response.status_code, 400)

        events = get_audit_spans("audit.traces.ingest")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status_code"], 400)
        self.assertEqual(events[0]["api_key_id"], self.api_key_id)
        self.assertEqual(events[0]["request_body"]["spans"][0]["span_id"], "d" * 16)

    def test_rate_limited_ingest_writes_an_event(self):
        """A 429 used to exist only as a WARN line in the service log."""
        env.set("AUDIT_RATE_LIMIT_PER_MINUTE", "1")
        self.addCleanup(env.set, "AUDIT_RATE_LIMIT_PER_MINUTE", "")
        first = self._ingest(self._span("b" * 16))
        second = self._ingest(self._span("c" * 16))
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 429)

        events = get_audit_spans("audit.traces.ingest")
        self.assertEqual([event["status_code"] for event in events], [429])

    def test_scope_denial_writes_an_event(self):
        from campus.audit.resources.apikeys import APIKeysResource
        _, write_only_value = APIKeysResource().new(
            name="Write Only Key", owner_id="test-user", scopes="traces:write",
        )
        response = self.client.get(
            "/audit/v1/traces/",
            headers={"Authorization": f"Bearer {write_only_value}"},
        )
        self.assertEqual(response.status_code, 403)

        events = get_audit_spans("audit.traces.list")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status_code"], 403)

    def test_successful_authentication_writes_no_auth_success_event(self):
        response = self.client.get("/audit/v1/traces/", headers=self.auth_headers)
        self.assertEqual(response.status_code, 200)

        self.assertEqual(get_audit_spans("audit.apikeys.auth.success"), [])

    def test_the_route_event_records_the_calling_key(self):
        self.client.get("/audit/v1/traces/", headers=self.auth_headers)

        events = get_audit_spans("audit.traces.list")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["api_key_id"], self.api_key_id)
        self.assertIsNotNone(events[0]["client_ip"])

    def test_failed_authentication_still_writes_auth_failed(self):
        self.client.get(
            "/audit/v1/traces/", headers={"Authorization": "Bearer not-an-audit-key"},
        )

        events = get_audit_spans("audit.apikeys.auth.failed")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status_code"], 401)
        self.assertIn("reason", events[0]["tags"])

    def test_failed_read_writes_an_event(self):
        response = self.client.get(
            "/audit/v1/traces/" + "0" * 32 + "/", headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 404)

        events = get_audit_spans("audit.traces.get")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status_code"], 404)
        self.assertIn("error", events[0]["response_body"])

    def test_successful_read_keeps_no_copy_of_its_response(self):
        self._ingest(self._span())
        response = self.client.get(
            "/audit/v1/traces/search?events=false", headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()["traces"]), 1)

        events = get_audit_spans("audit.traces.search")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["response_body"], {})


if __name__ == "__main__":
    unittest.main()
