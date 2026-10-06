"""Unit tests for devops.deploy route configuration (#842).

Campus convention: every deployment serves a landing page at / and a
health check at /health. Services with a web UI (campus.audit) provide
their own root route; the generic landing covers the API-only services.

File: tests/unit/common/test_deploy.py
Issue: #842
"""

import unittest

import flask

from campus.common import env
from campus.common.devops import deploy


class DeployConfigTestCase(unittest.TestCase):
    """Base: DEPLOY must be set (real deployments always set it)."""

    def setUp(self):
        env.set('DEPLOY', 'campus.test')
        self.addCleanup(env.set, 'DEPLOY', '')


class TestHealthEndpoint(DeployConfigTestCase):
    """/health is the health check endpoint (#842)."""

    def test_deployment_registers_health_json(self):
        app = flask.Flask(__name__)
        deploy.configure_for_deployment(app)
        response = app.test_client().get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["status"], "healthy")
        self.assertIn("deployment", body)
        self.assertIn("environment", body)

    def test_development_registers_health_json(self):
        app = flask.Flask(__name__)
        deploy.configure_for_development(app)
        response = app.test_client().get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "healthy")

    def test_health_registration_is_idempotent(self):
        """Applying both configure functions to one app must not double-map."""
        app = flask.Flask(__name__)
        deploy.configure_for_development(app)
        deploy.configure_for_deployment(app)
        response = app.test_client().get("/health")
        self.assertEqual(response.status_code, 200)


class TestLandingPage(DeployConfigTestCase):
    """/ is a landing page (#842)."""

    def test_deployment_adds_generic_landing_when_root_unowned(self):
        """API-only services get the generic HTML landing at /."""
        app = flask.Flask(__name__)
        deploy.configure_for_deployment(app)
        response = app.test_client().get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.content_type)
        self.assertIn(b"Campus", response.data)
        self.assertIn(b"/health", response.data)

    def test_deployment_keeps_service_owned_root(self):
        """A service with its own / (campus.audit) keeps it."""
        app = flask.Flask(__name__)

        @app.get("/")
        def root():
            return "service landing", 200

        deploy.configure_for_deployment(app)
        response = app.test_client().get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"service landing")

    def test_development_defers_to_service_owned_root(self):
        """The dev route index does not shadow a service landing page."""
        app = flask.Flask(__name__)

        @app.get("/")
        def root():
            return "service landing", 200

        deploy.configure_for_development(app)
        response = app.test_client().get("/")
        self.assertEqual(response.data, b"service landing")

    def test_development_adds_route_index_when_root_unowned(self):
        """API-only services keep the dev route index as their landing."""
        app = flask.Flask(__name__)
        deploy.configure_for_development(app)
        response = app.test_client().get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Campus Development Server", response.data)


if __name__ == "__main__":
    unittest.main()
