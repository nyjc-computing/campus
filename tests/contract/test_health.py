"""Health-endpoint contract: every campus deployment serves GET /health (#842).

Pins the fleet's common liveness endpoint on the single-origin topology,
so the convention stays available to whatever needs a liveness signal —
Railway healthchecks (#1107), the campus-gateway dispatch (#995), and
any harness or smoke logic that waits for a service to be up. The
gateway routes paths unchanged, which works only because each service's
routes already carry its public prefix; /health is the one endpoint
that exists on every service regardless of prefix placement.

No auth required, no storage touched: the route answers from the app
factory alone.
"""

import unittest

from tests.fixtures import services


class TestHealthConvention(unittest.TestCase):
    """GET /health answers 200 on every served deployment (#842)."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager(shared=False)
        cls.manager.initialize()

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def test_health_on_every_service(self):
        for name, app in (
            ("campus.auth", self.manager.auth_app),
            ("campus.api", self.manager.apps_app),
            ("campus.audit", self.manager.audit_app),
        ):
            with self.subTest(service=name):
                response = app.test_client().get("/health")
                self.assertEqual(response.status_code, 200)

    def test_health_requires_no_auth(self):
        """The health endpoint never 401s: it must answer pre-auth."""
        response = self.manager.auth_app.test_client().get("/health")
        self.assertNotEqual(response.status_code, 401)
