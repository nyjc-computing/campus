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

    def _new_group(self, name: str) -> str:
        """Create a group circle and return its UID."""
        from campus.api import resources
        from campus.common import schema
        group = resources.circle.new(name=name, tag="group")
        return str(schema.CampusID(group.id))

    def test_group_circle_member_confers_role(self):
        """Membership in a member group circle confers the role (#1196).

        The prod seeding pattern: a school-wide `student` group is
        added to the role circle once; every group member gains the
        role without enumerating user emails into the role circle.
        """
        from campus.api import resources
        from campus.api.resources.circle import circle_storage
        from campus.common import schema

        # The user's circle must exist before members/add accepts the
        # email-shaped member (same rule the fixture enforces).
        if not circle_storage.get_matching({"name": TEST_USER}):
            resources.circle.new(name=TEST_USER, tag="user")
        group_id = self._new_group("students")
        role_id = schema.CampusID(
            circle_storage.get_matching({"name": "circles.admin"})[0][
                schema.CAMPUS_KEY
            ]
        )
        resources.circle.members.add(
            schema.CampusID(group_id), member_id=schema.CampusID(TEST_USER),
            access_value=15,
        )
        resources.circle.members.add(
            role_id, member_id=schema.CampusID(group_id), access_value=15
        )
        self._gate({"id": TEST_USER})

    def test_nested_group_confers_role(self):
        """Resolution walks nested groups (user → group → role circle)."""
        from campus.api import resources
        from campus.api.resources.circle import circle_storage
        from campus.common import schema

        if not circle_storage.get_matching({"name": TEST_USER}):
            resources.circle.new(name=TEST_USER, tag="user")
        outer_id = self._new_group("staff")
        inner_id = self._new_group("teachers")
        role_id = schema.CampusID(
            circle_storage.get_matching({"name": "circles.admin"})[0][
                schema.CAMPUS_KEY
            ]
        )
        resources.circle.members.add(
            schema.CampusID(inner_id), member_id=schema.CampusID(TEST_USER),
            access_value=15,
        )
        resources.circle.members.add(
            schema.CampusID(outer_id), member_id=schema.CampusID(inner_id),
            access_value=15,
        )
        resources.circle.members.add(
            role_id, member_id=schema.CampusID(outer_id), access_value=15
        )
        self._gate({"id": TEST_USER})

    def test_member_group_cycle_terminates(self):
        """A cycle between member groups resolves without hanging (#1196)."""
        from campus.api import resources
        from campus.api.resources.circle import circle_storage
        from campus.common import schema

        if not circle_storage.get_matching({"name": TEST_USER}):
            resources.circle.new(name=TEST_USER, tag="user")
        group_a = self._new_group("cycle-a")
        group_b = self._new_group("cycle-b")
        role_id = schema.CampusID(
            circle_storage.get_matching({"name": "circles.admin"})[0][
                schema.CAMPUS_KEY
            ]
        )
        resources.circle.members.add(
            schema.CampusID(group_a), member_id=schema.CampusID(TEST_USER),
            access_value=15,
        )
        # group_a → group_b → group_a
        resources.circle.members.add(
            schema.CampusID(group_b), member_id=schema.CampusID(group_a),
            access_value=15,
        )
        resources.circle.members.add(
            schema.CampusID(group_a), member_id=schema.CampusID(group_b),
            access_value=15,
        )
        resources.circle.members.add(
            role_id, member_id=schema.CampusID(group_b), access_value=15
        )
        self._gate({"id": TEST_USER})

    def test_stale_member_group_fails_closed_without_blocking_others(self):
        """A deleted member circle denies for it but not for valid ones.

        The stale key (circle removed after being added to the role
        circle) is skipped fail-closed; resolution continues through
        the remaining member groups.
        """
        from campus.api import resources
        from campus.api.resources.circle import circle_storage
        from campus.common import schema

        if not circle_storage.get_matching({"name": TEST_USER}):
            resources.circle.new(name=TEST_USER, tag="user")
        stale_id = self._new_group("graduated-cohort")
        good_id = self._new_group("students")
        role_id = schema.CampusID(
            circle_storage.get_matching({"name": "circles.admin"})[0][
                schema.CAMPUS_KEY
            ]
        )
        resources.circle.members.add(
            schema.CampusID(good_id), member_id=schema.CampusID(TEST_USER),
            access_value=15,
        )
        resources.circle.members.add(
            role_id, member_id=schema.CampusID(stale_id), access_value=15
        )
        resources.circle.members.add(
            role_id, member_id=schema.CampusID(good_id), access_value=15
        )
        circle_storage.delete_by_id(schema.CampusID(stale_id))
        self._gate({"id": TEST_USER})
        with self.assertRaises(api_errors.ForbiddenError):
            self._gate({"id": OUTSIDER})

    def test_gate_is_per_resource(self):
        """Membership in one role circle does not confer another's role."""
        self._grant(TEST_USER, "timetable")
        with self.assertRaises(api_errors.ForbiddenError):
            self._gate({"id": TEST_USER}, resource="circles")
        self._gate({"id": TEST_USER}, resource="timetable")


if __name__ == "__main__":
    unittest.main()
