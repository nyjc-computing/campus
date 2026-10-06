"""Unit tests for the audit ingest rate gate + breaker feed (#831).

The producer side of campus.audit's per-identity ingest rate limit
(campus PR #835): the local AuditClient's traces.new feeds the SDK
circuit breaker on every ingest response, and the tracing middleware's
fail-closed gate (AUDIT_TRACING_FAIL_CLOSED=1) 503s matching requests
at entry.
"""

import os
import unittest
from unittest import mock

import flask
from campus_python.audit import ratelimit


def _set_env(test: unittest.TestCase, name: str, value: str) -> None:
    """Set an env var for the duration of a test."""
    os.environ[name] = value
    test.addCleanup(os.environ.pop, name, None)


def _429_body(bucket: str) -> dict:
    """Error envelope as emitted by campus.audit #835."""
    return {"error": {"code": "RATE_LIMITED", "details": {"bucket": bucket}}}


def _make_app(**identity) -> flask.Flask:
    """Flask app with the tracing middleware and a stub identity hook.

    The identity stub is registered BEFORE middleware.init_app so the
    gate (a later before_request hook) observes it — mirroring how
    app-level hooks registered earlier run first.
    """
    app = flask.Flask(__name__)
    app.config["TESTING"] = True

    @app.before_request
    def stub_identity():
        for key, value in identity.items():
            setattr(flask.g, key, value)

    from campus.audit.middleware import init_app as init_tracing

    init_tracing(app)

    @app.route("/")
    def index():
        return "ok"

    return app


class TestRateGate(unittest.TestCase):
    """The fail-closed gate short-circuits tripped buckets at entry."""

    def setUp(self):
        ratelimit.breaker.reset()
        self.addCleanup(ratelimit.breaker.reset)

    def test_flag_off_is_fail_open_even_when_tripped(self):
        _set_env(self, "AUDIT_TRACING_FAIL_CLOSED", "")
        ratelimit.breaker.observe(429, {"Retry-After": "60"}, _429_body("user=u1"))
        client = _make_app().test_client()
        response = client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_tripped_identity_bucket_returns_503(self):
        _set_env(self, "AUDIT_TRACING_FAIL_CLOSED", "1")
        ratelimit.breaker.observe(429, {"Retry-After": "60"}, _429_body("user=u1"))
        client = _make_app(user_id="u1").test_client()
        response = client.get("/")
        self.assertEqual(response.status_code, 503)
        self.assertIn("Retry-After", response.headers)
        self.assertGreaterEqual(int(response.headers["Retry-After"]), 1)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "RATE_LIMITED")

    def test_other_identities_unaffected(self):
        _set_env(self, "AUDIT_TRACING_FAIL_CLOSED", "1")
        ratelimit.breaker.observe(429, {"Retry-After": "60"}, _429_body("user=u1"))
        client = _make_app(user_id="u2").test_client()
        self.assertEqual(client.get("/").status_code, 200)

    def test_identityless_uses_learned_fallback_bucket(self):
        _set_env(self, "AUDIT_TRACING_FAIL_CLOSED", "1")
        ratelimit.breaker.observe(
            429, {"Retry-After": "60"}, _429_body("apikey=k-123")
        )
        client = _make_app().test_client()
        self.assertEqual(client.get("/").status_code, 503)

    def test_identityless_before_learning_uses_wildcard(self):
        _set_env(self, "AUDIT_TRACING_FAIL_CLOSED", "1")
        ratelimit.breaker.observe(
            429, {"Retry-After": "60"}, _429_body(ratelimit.WILDCARD)
        )
        client = _make_app().test_client()
        self.assertEqual(client.get("/").status_code, 503)

    def test_availability_error_does_not_trip_gate(self):
        _set_env(self, "AUDIT_TRACING_FAIL_CLOSED", "1")
        # 503 from audit is an availability error: neutral.
        ratelimit.breaker.observe(503, None, None)
        client = _make_app().test_client()
        self.assertEqual(client.get("/").status_code, 200)

    def test_verifying_state_gate_is_open(self):
        _set_env(self, "AUDIT_TRACING_FAIL_CLOSED", "1")
        ratelimit.breaker.observe(429, {"Retry-After": "60"}, _429_body("user=u1"))
        # Force the cooldown into the past (verifying): gate opens...
        ratelimit.breaker._tripped["user=u1"]["until"] -= 10_000
        client = _make_app(user_id="u1").test_client()
        self.assertEqual(client.get("/").status_code, 200)
        # ...and a 2xx ingest fully clears the trip.
        ratelimit.breaker.observe(201, None, None)
        self.assertEqual(ratelimit.breaker._tripped, {})


class TestClientObserveHook(unittest.TestCase):
    """AuditClient traces.new feeds the SDK breaker (#831)."""

    def setUp(self):
        ratelimit.breaker.reset()
        self.addCleanup(ratelimit.breaker.reset)

    def _traces_with_response(self, status: int, body: dict, raises: bool):
        from campus.audit.client.v1.traces import Traces

        response = mock.Mock()
        response.status_code = status
        response.headers = {"Retry-After": "30"}
        response.json.return_value = body
        if raises:
            response.raise_for_status.side_effect = RuntimeError(status)
        client = mock.Mock()
        client.post.return_value = response
        return Traces(client=client, root=mock.Mock()), response

    def test_429_trips_breaker_and_still_raises(self):
        traces, _ = self._traces_with_response(
            429, _429_body("client=c1;user=u1"), raises=True
        )
        with self.assertRaises(RuntimeError):
            traces.new({"span_id": "s1"})
        self.assertIsNotNone(
            ratelimit.breaker.check_request(client_id="c1", user_id="u1")
        )

    def test_201_does_not_trip(self):
        traces, _ = self._traces_with_response(
            201, {"created": ["s1"]}, raises=False
        )
        traces.new({"span_id": "s1"})
        self.assertEqual(ratelimit.breaker._tripped, {})

    def test_stale_sdk_degrades_silently(self):
        """A missing campus_python.audit.ratelimit must not break ingest."""
        traces, response = self._traces_with_response(
            201, {"created": ["s1"]}, raises=False
        )
        import builtins

        real_import = builtins.__import__

        def blocked_import(name, *args, **kwargs):
            if name.startswith("campus_python"):
                raise ImportError("simulated stale SDK")
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=blocked_import):
            traces.new({"span_id": "s1"})  # no raise
        self.assertEqual(response.status_code, 201)


if __name__ == "__main__":
    unittest.main()
