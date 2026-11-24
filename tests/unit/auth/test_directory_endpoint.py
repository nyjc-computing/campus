"""Unit tests for campus.auth's read-only directory surface (#1226).

The /directory surface is the facade's forward target: the operator or
an AUTH_DIRECTORY_CLIENT_IDS-allowlisted client may read; any other
client fails closed; a user principal is denied by design (end users
traverse campus.api's circles authorization, never auth internals).
"""

import unittest
from types import SimpleNamespace

import flask

from campus.common import env

# Configure test storage before importing storage-backed modules
env.set('STORAGE_MODE', "1")

DIRECTORY_CLIENT = "svc-campus-api"
OTHER_CLIENT = "other-client"
DIRECTORY_USER = "directory-user@campus.test"


class TestDirectoryEndpoint(unittest.TestCase):
    """Gate + happy path for the read-only directory routes."""

    def setUp(self):
        from campus.auth.resources import user as user_resource
        from campus.auth.routes.directory import DIRECTORY_CLIENT_IDS_ENVVAR

        user_resource.init_storage()
        env.set(DIRECTORY_CLIENT_IDS_ENVVAR, DIRECTORY_CLIENT)
        user_resource.get_or_create(
            email=DIRECTORY_USER, name="Directory User"
        )

    def tearDown(self):
        from campus.auth.routes.directory import DIRECTORY_CLIENT_IDS_ENVVAR

        env.set(DIRECTORY_CLIENT_IDS_ENVVAR, "")

    def _call_list(self, *, client=None, user=None):
        from campus.auth.routes.directory import list_users

        app = flask.Flask(__name__)
        with app.test_request_context():
            if client is not None:
                flask.g.current_client = client
            if user is not None:
                flask.g.current_user = user
            return list_users()

    def _call_get(self, user_id: str, *, client=None, user=None):
        from campus.auth.routes.directory import get_user

        app = flask.Flask(__name__)
        with app.test_request_context():
            if client is not None:
                flask.g.current_client = client
            if user is not None:
                flask.g.current_user = user
            return get_user(user_id=user_id)

    def test_allowlisted_client_reads(self):
        body, status = self._call_list(client=SimpleNamespace(id=DIRECTORY_CLIENT))
        self.assertEqual(status, 200)
        self.assertIn(
            DIRECTORY_USER, [u["id"] for u in body["users"]]
        )
        record, status = self._call_get(
            DIRECTORY_USER, client=SimpleNamespace(id=DIRECTORY_CLIENT)
        )
        self.assertEqual(status, 200)
        self.assertEqual(record["id"], DIRECTORY_USER)

    def test_unlisted_client_denied(self):
        from campus.common.errors import api_errors

        with self.assertRaises(api_errors.ForbiddenError) as ctx:
            self._call_list(client=SimpleNamespace(id=OTHER_CLIENT))
        self.assertIn("not allowlisted", str(ctx.exception))

    def test_user_principal_denied(self):
        from campus.common.errors import api_errors

        with self.assertRaises(api_errors.ForbiddenError) as ctx:
            self._call_list(user={"id": DIRECTORY_USER})
        self.assertIn("campus.api users facade", str(ctx.exception))

    def test_no_principal_denied(self):
        from campus.common.errors import api_errors

        with self.assertRaises(api_errors.ForbiddenError):
            self._call_list()
