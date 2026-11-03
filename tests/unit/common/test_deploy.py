"""Unit tests for campus.deploy route configuration (#842).

Campus convention: every standalone deployment serves a landing page at /
and a health check at /health. Services with a web UI (campus.audit)
provide their own root route; the generic landing covers the API-only
services. Deployments behind a shared hostname set PUBLIC_PREFIX: health
moves under the prefix and the shared root is left to the gateway.
deploy.create_app also names each sessionful service's session cookie
distinctly (SESSION_COOKIE_NAMES) so auth and audit sessions can coexist
in one browser jar, and serves the committed OpenAPI artifact at
/{prefix}/openapi.json (#1029). build_spec_from_module is the
AppModule-to-spec glue that keeps campus.flask_campus.openapi a pure
generator core (#993 carve boundary).

File: tests/unit/common/test_deploy.py
Issue: #842
"""

import unittest

import flask

from campus import deploy
from campus.common import env


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


class TestPrefixedDeployment(DeployConfigTestCase):
    """PUBLIC_PREFIX deployments: health under the prefix, no root claim."""

    def setUp(self):
        super().setUp()
        env.set('PUBLIC_PREFIX', '/auth')
        self.addCleanup(env.set, 'PUBLIC_PREFIX', '')

    def test_deployment_registers_prefixed_health(self):
        app = flask.Flask(__name__)
        deploy.configure_for_deployment(app)
        response = app.test_client().get("/auth/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "healthy")
        # The unprefixed path stays unclaimed.
        self.assertEqual(app.test_client().get("/health").status_code, 404)

    def test_prefixed_deployment_does_not_claim_root(self):
        """The shared root belongs to the gateway, not the service."""
        app = flask.Flask(__name__)
        deploy.configure_for_deployment(app)
        self.assertEqual(app.test_client().get("/").status_code, 404)

    def test_prefixed_development_registers_prefixed_health(self):
        app = flask.Flask(__name__)
        deploy.configure_for_development(app)
        self.assertEqual(
            app.test_client().get("/auth/health").status_code, 200)
        # No dev route index at the shared root either.
        self.assertEqual(app.test_client().get("/").status_code, 404)

    def test_prefixed_health_registration_is_idempotent(self):
        app = flask.Flask(__name__)
        deploy.configure_for_development(app)
        deploy.configure_for_deployment(app)
        self.assertEqual(
            app.test_client().get("/auth/health").status_code, 200)

    def test_empty_prefix_falls_back_to_standalone(self):
        env.set('PUBLIC_PREFIX', '')
        app = flask.Flask(__name__)
        deploy.configure_for_deployment(app)
        self.assertEqual(app.test_client().get("/health").status_code, 200)
        self.assertEqual(app.test_client().get("/").status_code, 200)

    def test_prefix_without_leading_slash_is_normalized(self):
        env.set('PUBLIC_PREFIX', 'auth')
        app = flask.Flask(__name__)
        deploy.configure_for_deployment(app)
        self.assertEqual(
            app.test_client().get("/auth/health").status_code, 200)


class _StubAppModule:
    """Minimal AppModule for create_app tests (no service init)."""

    @staticmethod
    def init_app(app: flask.Flask) -> None:
        pass


class TestSessionCookieName(DeployConfigTestCase):
    """Each sessionful deployment gets its own session cookie name."""

    def test_auth_gets_distinct_session_cookie(self):
        env.set('DEPLOY', 'campus.auth')
        # Skip the tracing middleware: not under test here.
        env.set('AUDIT_TRACING_ENABLED', '0')
        self.addCleanup(env.set, 'AUDIT_TRACING_ENABLED', '0')
        app = deploy.create_app(_StubAppModule)
        self.assertEqual(
            app.config['SESSION_COOKIE_NAME'], 'campus_auth_session')

    def test_audit_gets_distinct_session_cookie(self):
        env.set('DEPLOY', 'campus.audit')
        app = deploy.create_app(_StubAppModule)
        self.assertEqual(
            app.config['SESSION_COOKIE_NAME'], 'campus_audit_session')

    def test_unlisted_deployment_keeps_default_cookie(self):
        app = deploy.create_app(_StubAppModule)  # DEPLOY=campus.test
        self.assertEqual(app.config['SESSION_COOKIE_NAME'], 'session')


class TestBuildSpecFromModule(DeployConfigTestCase):
    """build_spec_from_module: the AppModule-to-spec glue (#1029).

    The glue lives in campus.deploy — beside create_app — so
    campus.flask_campus.openapi stays a pure generator core with no
    service-repo imports (#993 carve boundary). The version is required:
    the generator never guesses whose release it is pinning.
    """

    def test_builds_spec_from_dummy_appmodule(self):
        import os
        import sys
        import types

        from openapi_spec_validator import validate

        module = types.ModuleType("campus_deploy_spec_test_dummy")
        # Multi-line docstring exercises _service_info's docstring
        # fallback only when OPENAPI_INFO lacks title/description.
        module.__doc__ = "Dummy service. Module docstring description."
        module.OPENAPI_INFO = {
            "title": "Dummy API",
            "description": "Info description.",
        }
        module.init_app = _StubAppModule.init_app
        sys.modules["campus_deploy_spec_test_dummy"] = module
        saved = dict(os.environ)
        try:
            env.set("DEPLOY", "campus.deploy-spec-test")
            spec = deploy.build_spec_from_module(
                "campus_deploy_spec_test_dummy", version="9.9.9"
            )
        finally:
            sys.modules.pop("campus_deploy_spec_test_dummy", None)
            os.environ.clear()
            os.environ.update(saved)
        validate(spec)
        self.assertEqual(spec["info"]["title"], "Dummy API")
        self.assertTrue(
            spec["info"]["description"].startswith("Info description.")
        )
        self.assertIn("308 redirect", spec["info"]["description"])
        self.assertEqual(spec["info"]["version"], "9.9.9")

    def test_rejects_module_without_init_app(self):
        import sys
        import types

        module = types.ModuleType("campus_deploy_spec_test_broken")
        self.assertNotIn("campus_deploy_spec_test_broken", sys.modules)
        sys.modules["campus_deploy_spec_test_broken"] = module
        try:
            with self.assertRaises(TypeError):
                deploy.build_spec_from_module(
                    "campus_deploy_spec_test_broken", version="9.9.9"
                )
        finally:
            sys.modules.pop("campus_deploy_spec_test_broken", None)

    def test_rejects_missing_version(self):
        with self.assertRaises(TypeError):
            deploy.build_spec_from_module("campus.auth")  # type: ignore


if __name__ == "__main__":
    unittest.main()
