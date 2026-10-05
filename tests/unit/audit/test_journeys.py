"""Unit tests for the action-journey lifecycle (#828).

Journeys group one user-initiated action episode: the navigation that
began it, its XHRs/form posts (cookie continuation), and the
server-to-server calls those spawn (forwarded X-Journey-ID headers).
No storage, no network — pure request/response behavior via the Flask
test client.
"""

import unittest

import flask

import campus.config
from campus.audit.middleware import init_journeys, tracing
from campus.flask_campus import journey


class JourneyAppTestCase(unittest.TestCase):
    """Base: a Flask app with init_journeys and probe routes."""

    def setUp(self):
        self.app = flask.Flask(__name__)
        init_journeys(self.app)

        @self.app.get("/probe")
        def probe():
            return {
                "journey_id": getattr(flask.g, "journey_id", None),
                "journey_name": getattr(flask.g, "journey_name", None),
            }

        self.client = self.app.test_client()

    def _cookie_of(self, response):
        return response.headers.get("Set-Cookie")

    def _with_action_cookie(self, value):
        """Set the action cookie the way werkzeug's test client accepts."""
        self.client.set_cookie(
            campus.config.ACTION_JOURNEY_COOKIE, value
        )


class TestAdoption(JourneyAppTestCase):
    """Inbound journeys are adopted: header > cookie > nothing."""

    def test_header_adopted_and_wins_over_cookie(self):
        self._with_action_cookie("uid-journey-cookie1")
        resp = self.client.get(
            "/probe", headers={"X-Journey-ID": "uid-journey-header01"}
        )
        self.assertEqual(resp.json["journey_id"], "uid-journey-header01")

    def test_cookie_adopted_on_plain_request(self):
        """An XHR/form post with the cookie continues the episode."""
        self._with_action_cookie("uid-journey-cookie1")
        resp = self.client.get(
            "/probe", headers={"Accept": "application/json"}
        )
        self.assertEqual(resp.json["journey_id"], "uid-journey-cookie1")

    def test_no_journey_on_unjournaled_plain_request(self):
        resp = self.client.get("/probe", headers={"Accept": "application/json"})
        self.assertIsNone(resp.json["journey_id"])
        self.assertIsNone(self._cookie_of(resp))


class TestMinting(JourneyAppTestCase):
    """Navigations with no active journey mint a fresh episode."""

    def test_mints_on_sec_fetch_navigation(self):
        resp = self.client.get(
            "/probe", headers={"Sec-Fetch-Mode": "navigate"}
        )
        self.assertTrue(resp.json["journey_id"].startswith("uid-journey-"))
        self.assertIn(campus.config.ACTION_JOURNEY_COOKIE, self._cookie_of(resp))

    def test_mints_on_accept_html_fallback(self):
        resp = self.client.get("/probe", headers={"Accept": "text/html"})
        self.assertTrue(resp.json["journey_id"].startswith("uid-journey-"))

    def test_navigation_continues_live_episode(self):
        """A navigation with a still-live cookie continues the journey —
        a POST-redirect-GET result page must not split the episode. The
        episode ends on idle expiry or a fresh=True boundary instead."""
        first = self.client.get(
            "/probe", headers={"Sec-Fetch-Mode": "navigate"}
        )
        second = self.client.get(
            "/probe",
            headers={"Sec-Fetch-Mode": "navigate", "Accept": "text/html"},
        )
        self.assertEqual(first.json["journey_id"], second.json["journey_id"])

    def test_adopt_only_mode_never_mints(self):
        """mint_on_navigation=False (auth/api profile): adopt header/cookie
        only — a bare navigation stays unjournaled."""
        app = flask.Flask(__name__)
        init_journeys(app, mint_on_navigation=False)

        @app.get("/probe")
        def probe():
            return {"journey_id": getattr(flask.g, "journey_id", None)}

        bare = app.test_client().get(
            "/probe", headers={"Sec-Fetch-Mode": "navigate"}
        )
        self.assertIsNone(bare.json["journey_id"])

        adopted = app.test_client().get(
            "/probe", headers={"X-Journey-ID": "uid-journey-fwd01"}
        )
        self.assertEqual(adopted.json["journey_id"], "uid-journey-fwd01")

    def test_static_requests_skipped(self):
        """Static requests never adopt or mint (#819 interplay).

        Hits the app's built-in static endpoint (endpoint 'static'),
        which exists even without a static folder on disk.
        """
        resp = self.client.get(
            "/static/nonexistent.css",
            headers={
                "Sec-Fetch-Mode": "navigate",
                "X-Journey-ID": "uid-journey-header01",
            },
        )
        self.assertEqual(resp.status_code, 404)
        self.assertNotIn(
            campus.config.ACTION_JOURNEY_COOKIE, resp.headers.get("Set-Cookie") or ""
        )


class TestCookieContinuation(JourneyAppTestCase):
    """The cookie slides forward on every journeyed request."""

    def test_cookie_set_on_minted_navigation(self):
        resp = self.client.get(
            "/probe", headers={"Sec-Fetch-Mode": "navigate"}
        )
        cookie = self._cookie_of(resp)
        self.assertIn(
            f"{campus.config.ACTION_JOURNEY_COOKIE}={resp.json['journey_id']}",
            cookie,
        )
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertIn(
            f"Max-Age={campus.config.ACTION_JOURNEY_COOKIE_MAX_AGE}", cookie
        )

    def test_cookie_refreshed_with_adopted_journey(self):
        """The same id comes back, keeping the episode alive."""
        self._with_action_cookie("uid-journey-cookie1")
        resp = self.client.get(
            "/probe", headers={"Accept": "application/json"}
        )
        self.assertIn(
            f"{campus.config.ACTION_JOURNEY_COOKIE}=uid-journey-cookie1",
            self._cookie_of(resp),
        )


class TestBlueprintScoping(unittest.TestCase):
    """init_journeys accepts a blueprint for scoped opt-in."""

    def test_blueprint_routes_journeyed(self):
        app = flask.Flask(__name__)
        bp = flask.Blueprint("area", __name__)

        @bp.get("/in-area")
        def in_area():
            return {"journey_id": getattr(flask.g, "journey_id", None)}

        init_journeys(bp)

        @app.get("/outside")
        def outside():
            return {"journey_id": getattr(flask.g, "journey_id", None)}

        app.register_blueprint(bp)
        client = app.test_client()

        inside = client.get(
            "/in-area", headers={"Sec-Fetch-Mode": "navigate"}
        )
        self.assertTrue(inside.json["journey_id"].startswith("uid-journey-"))

        out = client.get("/outside", headers={"Sec-Fetch-Mode": "navigate"})
        self.assertIsNone(out.json["journey_id"])


class TestJourneyDecorator(unittest.TestCase):
    """@flask_campus.journey: soft default, fresh opt-in."""

    def _app(self, **dec_kwargs):
        app = flask.Flask(__name__)
        init_journeys(app)

        @app.get("/named")
        @journey("submit-assignment", **dec_kwargs)
        def named():
            return {
                "journey_id": flask.g.journey_id,
                "journey_name": flask.g.journey_name,
            }

        return app.test_client()

    def test_names_active_journey_without_changing_it(self):
        """Soft default: the middleware-adopted id stays; name attaches."""
        client = self._app()
        resp = client.get(
            "/named",
            headers={
                "X-Journey-ID": "uid-journey-active1",
                "Accept": "application/json",
            },
        )
        self.assertEqual(resp.json["journey_id"], "uid-journey-active1")
        self.assertEqual(resp.json["journey_name"], "submit-assignment")

    def test_mints_and_names_when_no_journey_active(self):
        client = self._app()
        resp = client.get("/named", headers={"Accept": "application/json"})
        self.assertTrue(resp.json["journey_id"].startswith("uid-journey-"))
        self.assertEqual(resp.json["journey_name"], "submit-assignment")
        # Standalone continuation: the cookie is set even mid-episode.
        self.assertIn(
            f"{campus.config.ACTION_JOURNEY_COOKIE}={resp.json['journey_id']}",
            resp.headers.get("Set-Cookie"),
        )

    def test_fresh_starts_new_journey(self):
        client = self._app(fresh=True)
        resp = client.get(
            "/named",
            headers={
                "X-Journey-ID": "uid-journey-active1",
                "Accept": "application/json",
            },
        )
        self.assertNotEqual(resp.json["journey_id"], "uid-journey-active1")
        self.assertTrue(resp.json["journey_id"].startswith("uid-journey-"))
        self.assertEqual(resp.json["journey_name"], "submit-assignment")


class TestSpanTags(unittest.TestCase):
    """build_span_from_context carries the journey name (#828)."""

    def setUp(self):
        self.app = flask.Flask(__name__)

    def _build_span(self):
        with self.app.test_request_context("/"):
            tracing.start_span()
            return tracing.build_span_from_context(
                flask.g.trace_id,
                flask.g.span_id,
                flask.Response(status=200),
                duration_ms=1.0,
            )

    def test_journey_name_in_tags_when_stashed(self):
        with self.app.test_request_context("/"):
            tracing.start_span()
            flask.g.journey_id = "uid-journey-x"
            flask.g.journey_name = "submit-assignment"
            span = tracing.build_span_from_context(
                flask.g.trace_id,
                flask.g.span_id,
                flask.Response(status=200),
                duration_ms=1.0,
            )

        self.assertEqual(span["tags"]["journey_name"], "submit-assignment")
        self.assertEqual(span["tags"]["journey_id"], "uid-journey-x")

    def test_no_name_leaves_tag_out(self):
        span = self._build_span()

        self.assertNotIn("journey_name", span["tags"])


if __name__ == "__main__":
    unittest.main()
