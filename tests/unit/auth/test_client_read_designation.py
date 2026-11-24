"""Unit tests for the read-level client designation carve-out (#1226).

Client principals are denied on the management level vocabularies
(#854/#865) with exactly one exception: a client holding a `read`
grant row passes read-level checks — the users directory facade
forwards its queries under the api service's credential, with the
acting person attributed one layer up at the facade. Write-level
authority is never reachable for clients: mutation attribution stays
person-only.
"""

import unittest
from types import SimpleNamespace

import flask

from campus.common import env
from campus.common.errors import api_errors

# Configure test storage before importing storage-backed modules
env.set('STORAGE_MODE', "1")

SERVICE_CLIENT = "svc-campus-api"
OTHER_CLIENT = "other-client"


class TestClientReadDesignation(unittest.TestCase):
    """The gate honors client grant rows at read level, only there."""

    def setUp(self):
        from campus.auth.resources.grant import grants

        grants.init_storage()

    def tearDown(self):
        from campus.auth.resources.grant import grants

        grants.revoke(
            grantee_type="client",
            grantee_id=SERVICE_CLIENT,
            resource_type="users",
            level="read",
        )
        grants.revoke(
            grantee_type="client",
            grantee_id=SERVICE_CLIENT,
            resource_type="users",
            level="admin",
        )

    def _gate(self, client_id: str, level: str) -> None:
        from campus.auth.authz import require_resource_permission

        app = flask.Flask(__name__)
        with app.test_request_context():
            flask.g.current_client = SimpleNamespace(id=client_id)
            require_resource_permission("users", level)

    def test_read_grant_row_passes_read_check(self):
        """A client holding users:read passes the read-level gate."""
        from campus.auth.resources.grant import grants

        grants.grant(
            grantee_type="client",
            grantee_id=SERVICE_CLIENT,
            resource_type="users",
            level="read",
        )
        self._gate(SERVICE_CLIENT, "read")

    def test_admin_grant_row_covers_read(self):
        """Level coverage is monotonic: users:admin covers read."""
        from campus.auth.resources.grant import grants

        grants.grant(
            grantee_type="client",
            grantee_id=SERVICE_CLIENT,
            resource_type="users",
            level="admin",
        )
        self._gate(SERVICE_CLIENT, "read")

    def test_rowless_client_denied(self):
        """No grant row: the client denial stands (fail-closed)."""
        with self.assertRaises(api_errors.ForbiddenError) as ctx:
            self._gate(OTHER_CLIENT, "read")
        self.assertIn("never other clients", str(ctx.exception))

    def test_write_level_denied_even_with_read_row(self):
        """The carve-out is read-only: write stays person-only (#854)."""
        from campus.auth.resources.grant import grants

        grants.grant(
            grantee_type="client",
            grantee_id=SERVICE_CLIENT,
            resource_type="users",
            level="read",
        )
        with self.assertRaises(api_errors.ForbiddenError) as ctx:
            self._gate(SERVICE_CLIENT, "write")
        self.assertIn("never other clients", str(ctx.exception))
