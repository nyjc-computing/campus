"""Unit tests for the stamps campus.audit adds to spans at ingest
(#1243, #1244).

campus.audit.helpers.span_enrichment records two facts a producer
cannot be trusted with: which API key delivered a span
(``tags.producer_id``), and how long the request waited before the
producer's first line of code ran (``tags.queue_ms``, derived from the
``X-Request-Start`` header).

The header arrives in two forms. Railway's edge sends bare epoch
milliseconds; the gateway stamp that PR #1242 added and #1250 removed
sent ``t=<seconds.milliseconds>``. Stored spans carry both, so the
parser must accept either.
"""

import datetime
import unittest

import campus.model as model
from campus.audit.helpers import span_enrichment
from campus.common import schema

STARTED_AT = "2026-11-24T10:17:58.349921+00:00"
ARRIVAL_SECONDS = 1795515478.341
ARRIVAL_MS = "1795515478341"
ARRIVAL_T = "t=1795515478.341"

EXPECTED_WAIT_MS = (
    datetime.datetime.fromisoformat(STARTED_AT).timestamp() - ARRIVAL_SECONDS
) * 1000


class TestParseRequestStart(unittest.TestCase):
    """Both stored forms of X-Request-Start parse to the same epoch second."""

    def test_edge_form_is_epoch_milliseconds(self):
        value = span_enrichment.parse_request_start(ARRIVAL_MS)
        self.assertAlmostEqual(value, ARRIVAL_SECONDS, places=3)

    def test_gateway_form_is_seconds_with_a_fraction(self):
        value = span_enrichment.parse_request_start(ARRIVAL_T)
        self.assertAlmostEqual(value, ARRIVAL_SECONDS, places=3)

    def test_bare_seconds_are_accepted(self):
        value = span_enrichment.parse_request_start("1795515478.341")
        self.assertAlmostEqual(value, ARRIVAL_SECONDS, places=3)

    def test_prefix_is_case_insensitive_and_whitespace_is_ignored(self):
        value = span_enrichment.parse_request_start("  T=1795515478.341 ")
        self.assertAlmostEqual(value, ARRIVAL_SECONDS, places=3)

    def test_unusable_values_are_none(self):
        unusable = (None, 1795515478.341, "", "  ", "t=", "soon", "nan",
                    "inf", "0", "-1")
        for value in unusable:
            with self.subTest(value=value):
                self.assertIsNone(span_enrichment.parse_request_start(value))


class TestQueueMs(unittest.TestCase):
    """The wait is measured from arrival to the span's start."""

    def test_wait_between_arrival_and_start(self):
        wait = span_enrichment.queue_ms(
            STARTED_AT, {"X-Request-Start": ARRIVAL_MS},
        )
        self.assertAlmostEqual(wait, EXPECTED_WAIT_MS, places=3)

    def test_accepts_schema_datetime_and_either_header_form(self):
        for header_value in (ARRIVAL_MS, ARRIVAL_T):
            with self.subTest(header=header_value):
                wait = span_enrichment.queue_ms(
                    schema.DateTime(STARTED_AT),
                    {"X-Request-Start": header_value},
                )
                self.assertAlmostEqual(wait, EXPECTED_WAIT_MS, places=2)

    def test_header_lookup_is_case_insensitive(self):
        wait = span_enrichment.queue_ms(
            STARTED_AT, {"x-request-start": ARRIVAL_MS},
        )
        self.assertAlmostEqual(wait, EXPECTED_WAIT_MS, places=3)

    def test_none_without_a_usable_header(self):
        for headers in (None, {}, {"X-Request-Start": "soon"}, []):
            with self.subTest(headers=headers):
                self.assertIsNone(
                    span_enrichment.queue_ms(STARTED_AT, headers)
                )

    def test_none_when_the_start_does_not_parse(self):
        headers = {"X-Request-Start": ARRIVAL_MS}
        self.assertIsNone(span_enrichment.queue_ms("not a date", headers))
        self.assertIsNone(span_enrichment.queue_ms(None, headers))

    def test_small_negative_wait_is_kept(self):
        """A producer clock running behind the edge reads as negative."""
        started = datetime.datetime.fromisoformat(STARTED_AT).timestamp()
        # Five whole milliseconds after the start (the stamp has
        # millisecond resolution).
        arrival_ms = int(started * 1000) + 5
        wait = span_enrichment.queue_ms(
            STARTED_AT, {"X-Request-Start": str(arrival_ms)},
        )
        self.assertLess(wait, 0)
        self.assertAlmostEqual(
            wait, (started - arrival_ms / 1000) * 1000, places=2,
        )

    def test_wait_beyond_an_hour_is_discarded(self):
        """Skew or a forged stamp, not queueing: it would poison averages."""
        two_hours_ms = 2 * 3_600 * 1000
        for arrival in (ARRIVAL_SECONDS * 1000 - two_hours_ms,
                        ARRIVAL_SECONDS * 1000 + two_hours_ms):
            with self.subTest(arrival=arrival):
                self.assertIsNone(span_enrichment.queue_ms(
                    STARTED_AT, {"X-Request-Start": str(int(arrival))},
                ))


def _span(*, tags=None, headers=None) -> model.TraceSpan:
    return model.TraceSpan(
        trace_id="a" * 32,
        span_id="b" * 16,
        parent_span_id=None,
        method="GET",
        path="/api/v1/test",
        started_at=STARTED_AT,
        duration_ms=12.5,
        client_ip="127.0.0.1",
        request_headers=dict(headers or {}),
        tags=dict(tags or {}),
    )


class TestStamp(unittest.TestCase):
    """The stamps are the audit service's own assertion."""

    def test_adds_both_stamps_and_keeps_the_other_tags(self):
        span = _span(
            tags={"journey_id": "journey-1"},
            headers={"X-Request-Start": ARRIVAL_MS},
        )
        row = span_enrichment.stamp(span, producer_id="uid-key-1")
        self.assertEqual(row["tags"]["producer_id"], "uid-key-1")
        self.assertEqual(row["tags"]["journey_id"], "journey-1")
        self.assertAlmostEqual(
            row["tags"]["queue_ms"], EXPECTED_WAIT_MS, places=3,
        )

    def test_producer_supplied_stamps_are_replaced(self):
        span = _span(
            tags={"producer_id": "uid-spoofed", "queue_ms": 0.0},
            headers={"X-Request-Start": ARRIVAL_MS},
        )
        row = span_enrichment.stamp(span, producer_id="uid-key-1")
        self.assertEqual(row["tags"]["producer_id"], "uid-key-1")
        self.assertAlmostEqual(
            row["tags"]["queue_ms"], EXPECTED_WAIT_MS, places=3,
        )

    def test_without_a_producer_no_producer_tag_and_the_spoof_is_dropped(self):
        row = span_enrichment.stamp(_span(tags={"producer_id": "uid-spoofed"}))
        self.assertNotIn(span_enrichment.PRODUCER_TAG, row["tags"])
        self.assertNotIn(span_enrichment.QUEUE_TAG, row["tags"])

    def test_queue_stamp_needs_a_usable_header(self):
        row = span_enrichment.stamp(
            _span(headers={"X-Request-Start": "soon"}), producer_id="uid-key-1",
        )
        self.assertEqual(row["tags"]["producer_id"], "uid-key-1")
        self.assertNotIn(span_enrichment.QUEUE_TAG, row["tags"])

    def test_the_model_instance_is_not_mutated(self):
        span = _span(
            tags={"producer_id": "uid-spoofed"},
            headers={"X-Request-Start": ARRIVAL_MS},
        )
        span_enrichment.stamp(span, producer_id="uid-key-1")
        self.assertEqual(span.tags, {"producer_id": "uid-spoofed"})


if __name__ == "__main__":
    unittest.main()
