"""Integration tests for a full campus_python.Campus() client.

Exercises the client-level end-to-end path against the patched test
transport (tests.flask_test), which direct Flask test client tests
don't cover: base URL resolution → client_credentials grant →
bearer-authenticated read (campus#736, campus#731).
"""

import campus_python

from campus.common import env
from tests.integration.base import IntegrationTestCase


class TestFullClientEndToEnd(IntegrationTestCase):
    """End-to-end tests for the full Campus client.

    The fixture sets CAMPUS_AUTH_URL/CAMPUS_API_URL to https://campus.test,
    so a full Campus() client resolves base URLs into the Flask test apps
    registered under that origin (campus#736). Without those variables the
    client falls back to the development Railway defaults and the patched
    transport raises
    "No Flask app registered for base_url '...railway.app'".

    These tests were deferred from campus#731 until the fixture fix landed.
    """

    def test_app_session_grant_and_api_bearer_read(self):
        """with_app_session() grants a token and the client makes a bearer read.

        The bearer read targets the api app: its middleware authenticates
        the app-scoped token via auth's /root/authenticate, which falls
        through to app credentials.
        """
        self.assertTrue(env.CLIENT_ID, "fixture must set CLIENT_ID")

        with campus_python.Campus(timeout=10).with_app_session() as client:
            # Entering the context performs the client_credentials grant
            # against the local auth app; the list call is the bearer read.
            assignments = client.api.assignments.list()
            self.assertIsInstance(assignments, list)

    def test_app_session_bearer_read_on_auth_route(self):
        """An app-scoped token authenticates against the auth service itself.

        bearer_authenticate falls through from user credentials to app
        credentials (#739), so GET /auth/v1/clients/<id>/ serves the
        token minted by the client_credentials grant. Before the
        fallthrough, the same read failed with 401 invalid_token.
        """
        self.assertTrue(env.CLIENT_ID, "fixture must set CLIENT_ID")

        with campus_python.Campus(timeout=10).with_app_session() as client:
            client_record = client.auth.clients[env.CLIENT_ID].get()
            self.assertEqual(str(client_record.id), env.CLIENT_ID)
