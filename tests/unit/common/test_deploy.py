"""Suite-side consumer tests for campus.deploy (campus#1042 carve).

campus.deploy now ships in the campus-deploy distribution; the suite
declares the wheel and keeps only the consumer-side tests that need
co-installed suite portions:

- TestSessionCookieName reads the suite's campus.config
  (SESSION_COOKIE_NAMES) through create_app.
- TestBuildSpecFromModule exercises the AppModule-to-spec glue through
  the campus.flask_campus.openapi provider seam.

The route-configuration behavior tests (health/landing/PUBLIC_PREFIX,
#842) moved to nyjc-computing/campus-deploy (tests/unit/test_deploy.py),
which owns the module. File: tests/unit/common/test_deploy.py.
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
