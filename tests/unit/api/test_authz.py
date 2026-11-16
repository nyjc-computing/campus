"""Unit tests for campus.api.authz (circle-backed route gates).

require_resource_admin must fail closed: only a user principal whose
ID (email, = user-circle name) is a member of the <resource>.admin
role circle passes. Client principals, missing role circles, and
non-members are denied. action_label only shapes the message.
"""

import unittest
from types import SimpleNamespace

import flask

from campus.common import env
from campus.common.errors import api_errors

# Configure test storage before importing storage-backed modules
env.set('STORAGE_MODE', "1")

TEST_USER = "teacher@campus.test"
OUTSIDER = "outsider@campus.test"


class TestRequireResourceAdmin(unittest.TestCase):
    """The circles-backed gate denies everything but role members."""

    def setUp(self):
        from campus.api.resources.circle import (
            CirclesResource,
            circle_storage,
        )

        circle_storage.delete_matching({})
        CirclesResource.init_storage()

    def tearDown(self):
        from campus.api.resources.circle import circle_storage
        circle_storage.delete_matching({})

    def _grant(self, user_id: str, family: str = "circles"):
        from tests.fixtures.circles import grant_circle_admin
        grant_circle_admin(user_id, family)

    def _gate(self, user, resource: str = "circles", **kwargs):
        from campus.api.authz import require_resource_admin

        app = flask.Flask(__name__)
        with app.test_request_context():
            flask.g.current_user = user
            require_resource_admin(resource, **kwargs)

    def test_member_dict_principal_passes(self):
        """A member user principal (dict shape) passes the gate."""
        self._grant(TEST_USER)
        self._gate({"id": TEST_USER})

    def test_member_object_principal_passes(self):
        """A member user principal (model-object shape) passes the gate."""
        self._grant(TEST_USER)
        self._gate(SimpleNamespace(id=TEST_USER))

    def test_non_member_user_denied(self):
        """An authenticated user without the role is denied."""
        with self.assertRaises(api_errors.ForbiddenError):
            self._gate({"id": OUTSIDER})

    def test_client_principal_denied(self):
        """A client principal (no user) is denied even for a member id."""
        self._grant(TEST_USER)
        with self.assertRaises(api_errors.ForbiddenError) as ctx:
            self._gate(None)
        self.assertIn("Client principals", str(ctx.exception))

    def test_missing_role_circle_denied(self):
        """A missing role circle denies fail-closed (no 500, no pass)."""
        with self.assertRaises(api_errors.ForbiddenError) as ctx:
            self._gate({"id": TEST_USER}, resource="bookings")
        self.assertIn("bookings.admin", str(ctx.exception))

    def test_action_label_in_message(self):
        """A provided action_label appears in the denial message."""
        with self.assertRaises(api_errors.ForbiddenError) as ctx:
            self._gate({"id": OUTSIDER}, action_label="create bookings")
        self.assertIn("create bookings", str(ctx.exception))

    def test_missing_action_label_degrades_message(self):
        """Omitting action_label degrades the message, never the gate."""
        with self.assertRaises(api_errors.ForbiddenError) as ctx:
            self._gate({"id": OUTSIDER})
        self.assertIn("perform this action", str(ctx.exception))

    def test_gate_is_per_resource(self):
        """Membership in one role circle does not confer another's role."""
        self._grant(TEST_USER, "timetable")
        with self.assertRaises(api_errors.ForbiddenError):
            self._gate({"id": TEST_USER}, resource="circles")
        self._gate({"id": TEST_USER}, resource="timetable")


if __name__ == "__main__":
    unittest.main()
