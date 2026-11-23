"""Unit tests for campus.api.authz (circle-backed route gates).

The ratified access model (campus#1216): authority is the effective
access value on a family — baseline (primary-group membership) +
family-directed edges, reduced per scope (G fields for group ops, S
for self ops), with the `campus` wildcard short-circuiting and
category subcircles narrowing group scope. Gates fail closed: client
principals, missing grant circles, and principals without the
required bit are denied. action_label only shapes the message.
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


class GateTestBase(unittest.TestCase):
    """Shared harness: fresh bootstrapped circle store per test."""

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

    def _gate_admin(self, user, resource: str = "circles", **kwargs):
        from campus.api.authz import require_resource_admin

        app = flask.Flask(__name__)
        with app.test_request_context():
            flask.g.current_user = user
            require_resource_admin(resource, **kwargs)

    def _gate_access(self, user, resource: str, scope: str, permission: str,
                     **kwargs):
        from campus.api.authz import require_resource_access

        app = flask.Flask(__name__)
        with app.test_request_context():
            flask.g.current_user = user
            require_resource_access(resource, scope, permission, **kwargs)


class TestRequireResourceAdmin(GateTestBase):
    """The CRUD gate (group-scope create) denies everything but holders."""

    def test_direct_edge_passes(self):
        """A family:admin edge passes the gate (dict principal shape)."""
        from tests.fixtures.circles import grant_circle_admin
        grant_circle_admin(TEST_USER, "circles")
        self._gate_admin({"id": TEST_USER})

    def test_direct_edge_passes_object_principal(self):
        """A family:admin edge passes (model-object principal shape)."""
        from tests.fixtures.circles import grant_circle_admin
        grant_circle_admin(TEST_USER, "circles")
        self._gate_admin(SimpleNamespace(id=TEST_USER))

    def test_non_holder_denied(self):
        """An authenticated user with no applicable edge is denied."""
        with self.assertRaises(api_errors.ForbiddenError):
            self._gate_admin({"id": OUTSIDER})

    def test_client_principal_denied(self):
        """A client principal (no user) is denied even for a holder id."""
        from tests.fixtures.circles import grant_circle_admin
        grant_circle_admin(TEST_USER, "circles")
        with self.assertRaises(api_errors.ForbiddenError) as ctx:
            self._gate_admin(None)
        self.assertIn("Client principals", str(ctx.exception))

    def test_missing_grant_circle_denied(self):
        """A family with no grant circle denies fail-closed (no 500)."""
        from campus.api.resources.circle import circle_storage
        from campus.common import schema

        family_id = schema.CampusID(
            circle_storage.get_matching({"name": "timetable"})[0][
                schema.CAMPUS_KEY
            ]
        )
        circle_storage.delete_by_id(family_id)
        with self.assertRaises(api_errors.ForbiddenError) as ctx:
            self._gate_admin({"id": TEST_USER}, resource="timetable")
        self.assertIn("grant circle", str(ctx.exception))

    def test_action_label_in_message(self):
        """A provided action_label appears in the denial message."""
        with self.assertRaises(api_errors.ForbiddenError) as ctx:
            self._gate_admin({"id": OUTSIDER}, action_label="create bookings")
        self.assertIn("create bookings", str(ctx.exception))

    def test_missing_action_label_degrades_message(self):
        """Omitting action_label degrades the message, never the gate."""
        with self.assertRaises(api_errors.ForbiddenError) as ctx:
            self._gate_admin({"id": OUTSIDER})
        self.assertIn("perform this action", str(ctx.exception))

    def test_group_circle_edge_confers(self):
        """A member circle contained in the family confers its edge value.

        The prod seeding pattern: a committee group joins the family
        grant circle once; every member gains the authority without
        enumerating user emails into the family circle.
        """
        from campus.api import resources
        from campus.api.resources.circle import ACCESS_ADMIN, circle_storage
        from campus.common import schema
        from tests.fixtures.circles import _ensure_user_circle

        _ensure_user_circle(TEST_USER)
        family_id = schema.CampusID(
            circle_storage.get_matching({"name": "circles"})[0][
                schema.CAMPUS_KEY
            ]
        )
        committee = resources.circle.new(
            name="committees.timetabling", tag="group",
            parents={family_id: ACCESS_ADMIN},
        )
        resources.circle.members.add(
            schema.CampusID(committee.id),
            member_id=schema.CampusID(TEST_USER),
            access_value=ACCESS_ADMIN,
        )
        self._gate_admin({"id": TEST_USER})

    def test_nested_groups_confer(self):
        """Resolution walks nested member circles (user → group → family)."""
        from campus.api import resources
        from campus.api.resources.circle import ACCESS_ADMIN, circle_storage
        from campus.common import schema
        from tests.fixtures.circles import _ensure_user_circle

        _ensure_user_circle(TEST_USER)
        family_id = schema.CampusID(
            circle_storage.get_matching({"name": "circles"})[0][
                schema.CAMPUS_KEY
            ]
        )
        outer = resources.circle.new(name="outer-group", tag="group")
        inner = resources.circle.new(
            name="inner-group", tag="group",
            parents={schema.CampusID(outer.id): ACCESS_ADMIN},
        )
        resources.circle.members.add(
            schema.CampusID(inner.id), member_id=schema.CampusID(TEST_USER),
            access_value=ACCESS_ADMIN,
        )
        resources.circle.members.add(
            family_id, member_id=schema.CampusID(outer.id),
            access_value=ACCESS_ADMIN,
        )
        self._gate_admin({"id": TEST_USER})

    def test_member_group_cycle_terminates(self):
        """A cycle between member circles resolves without hanging."""
        from campus.api import resources
        from campus.api.resources.circle import ACCESS_ADMIN, circle_storage
        from campus.common import schema
        from tests.fixtures.circles import _ensure_user_circle

        _ensure_user_circle(TEST_USER)
        family_id = schema.CampusID(
            circle_storage.get_matching({"name": "circles"})[0][
                schema.CAMPUS_KEY
            ]
        )
        group_a = resources.circle.new(name="cycle-a", tag="group")
        group_b = resources.circle.new(name="cycle-b", tag="group")
        resources.circle.members.add(
            schema.CampusID(group_a.id), member_id=schema.CampusID(TEST_USER),
            access_value=ACCESS_ADMIN,
        )
        resources.circle.members.add(
            schema.CampusID(group_b.id), member_id=schema.CampusID(group_a.id),
            access_value=ACCESS_ADMIN,
        )
        resources.circle.members.add(
            schema.CampusID(group_a.id), member_id=schema.CampusID(group_b.id),
            access_value=ACCESS_ADMIN,
        )
        resources.circle.members.add(
            family_id, member_id=schema.CampusID(group_b.id),
            access_value=ACCESS_ADMIN,
        )
        self._gate_admin({"id": TEST_USER})

    def test_stale_member_group_fails_closed_without_blocking_others(self):
        """A deleted member circle denies for it but not for valid ones."""
        from campus.api import resources
        from campus.api.resources.circle import ACCESS_ADMIN, circle_storage
        from campus.common import schema
        from tests.fixtures.circles import _ensure_user_circle

        _ensure_user_circle(TEST_USER)
        stale = resources.circle.new(name="graduated-cohort", tag="group")
        good = resources.circle.new(name="students-group", tag="group")
        family_id = schema.CampusID(
            circle_storage.get_matching({"name": "circles"})[0][
                schema.CAMPUS_KEY
            ]
        )
        resources.circle.members.add(
            schema.CampusID(good.id), member_id=schema.CampusID(TEST_USER),
            access_value=ACCESS_ADMIN,
        )
        resources.circle.members.add(
            family_id, member_id=schema.CampusID(stale.id),
            access_value=ACCESS_ADMIN,
        )
        resources.circle.members.add(
            family_id, member_id=schema.CampusID(good.id),
            access_value=ACCESS_ADMIN,
        )
        circle_storage.delete_by_id(schema.CampusID(stale.id))
        self._gate_admin({"id": TEST_USER})
        with self.assertRaises(api_errors.ForbiddenError):
            self._gate_admin({"id": OUTSIDER})

    def test_gate_is_per_resource(self):
        """Authority on one family does not confer another's."""
        from tests.fixtures.circles import grant_circle_admin
        grant_circle_admin(TEST_USER, "timetable")
        with self.assertRaises(api_errors.ForbiddenError):
            self._gate_admin({"id": TEST_USER}, resource="circles")
        self._gate_admin({"id": TEST_USER}, resource="timetable")


class TestValueSemantics(GateTestBase):
    """The dual-scope constants gate by field, not by membership."""

    def test_editor_can_modify_but_not_create(self):
        """editor's G field carries modify+read, not create."""
        from campus.api.resources.circle import ACCESS_EDITOR
        from tests.fixtures.circles import grant_family_access

        grant_family_access(TEST_USER, "venues", ACCESS_EDITOR)
        self._gate_access(
            {"id": TEST_USER}, "venues", "group", "modify")
        with self.assertRaises(api_errors.ForbiddenError):
            self._gate_access({"id": TEST_USER}, "venues", "group", "create")

    def test_viewer_is_read_only(self):
        """viewer's G field carries read only."""
        from campus.api.resources.circle import ACCESS_VIEWER
        from tests.fixtures.circles import grant_family_access

        grant_family_access(TEST_USER, "timetable", ACCESS_VIEWER)
        self._gate_access({"id": TEST_USER}, "timetable", "group", "read")
        with self.assertRaises(api_errors.ForbiddenError):
            self._gate_access({"id": TEST_USER}, "timetable", "group", "modify")

    def test_staff_baseline_reads_everything(self):
        """staff:viewer baseline reads any family without family edges."""
        from tests.fixtures.circles import grant_staff_baseline

        grant_staff_baseline(TEST_USER)
        self._gate_access({"id": TEST_USER}, "timetable", "group", "read")
        self._gate_access({"id": TEST_USER}, "subjcombi", "group", "read")
        with self.assertRaises(api_errors.ForbiddenError):
            self._gate_access({"id": TEST_USER}, "timetable", "group", "create")

    def test_student_guest_is_own_read_only(self):
        """student:guest reads own-scope where the family honors it."""
        from campus.api import resources
        from campus.api.resources.circle import ACCESS_GUEST, circle_storage
        from campus.common import schema
        if not circle_storage.get_matching({"name": TEST_USER}):
            resources.circle.new(name=TEST_USER, tag="user")
        if not circle_storage.get_matching({"name": "student"}):
            resources.circle.new(name="student", tag="group")
        student_id = schema.CampusID(
            circle_storage.get_matching({"name": "student"})[0][
                schema.CAMPUS_KEY
            ]
        )
        resources.circle.members.add(
            student_id, member_id=schema.CampusID(TEST_USER),
            access_value=ACCESS_GUEST,
        )
        # timetable honors self-scope read (subject-match own timetable)
        self._gate_access({"id": TEST_USER}, "timetable", "self", "read")
        # and nothing beyond it: no group read, no self create
        with self.assertRaises(api_errors.ForbiddenError):
            self._gate_access({"id": TEST_USER}, "timetable", "group", "read")
        with self.assertRaises(api_errors.ForbiddenError):
            self._gate_access({"id": TEST_USER}, "timetable", "self", "create")

    def test_family_table_blanks_vacuous_self_scopes(self):
        """A family without own-semantics denies self-scope checks."""
        from campus.api.resources.circle import ACCESS_ADMIN
        from tests.fixtures.circles import grant_family_access

        grant_family_access(TEST_USER, "assignments", ACCESS_ADMIN)
        with self.assertRaises(api_errors.ForbiddenError) as ctx:
            self._gate_access(
                {"id": TEST_USER}, "assignments", "self", "read")
        self.assertIn("does not honor", str(ctx.exception))

    def test_non_constant_edge_values_rejected(self):
        """members/add rejects values outside the constant set."""
        from campus.api import resources
        from campus.api.resources.circle import circle_storage
        from campus.common import schema
        from tests.fixtures.circles import _ensure_user_circle

        _ensure_user_circle(TEST_USER)
        family_id = schema.CampusID(
            circle_storage.get_matching({"name": "circles"})[0][
                schema.CAMPUS_KEY
            ]
        )
        with self.assertRaises(api_errors.InvalidRequestError):
            resources.circle.members.add(
                family_id, member_id=schema.CampusID(TEST_USER),
                access_value=15,  # legacy value: retired
            )


class TestWildcard(GateTestBase):
    """The campus wildcard confers admin on every family."""

    def test_wildcard_passes_everywhere(self):
        """campus:admin passes gates on families with no other edges."""
        from tests.fixtures.circles import grant_campus_admin

        grant_campus_admin(TEST_USER)
        self._gate_admin({"id": TEST_USER}, resource="circles")
        self._gate_admin({"id": TEST_USER}, resource="subjcombi")
        self._gate_access(
            {"id": TEST_USER}, "venues", "self", "create")

    def test_lesser_campus_membership_does_not_wildcard(self):
        """A non-admin campus membership confers nothing cross-family."""
        from campus.api.resources.circle import ACCESS_GUEST
        from tests.fixtures.circles import grant_family_access

        grant_family_access(TEST_USER, "campus", ACCESS_GUEST)
        with self.assertRaises(api_errors.ForbiddenError):
            self._gate_admin({"id": TEST_USER}, resource="timetable")


class TestCategoryNarrowing(GateTestBase):
    """Category subcircles narrow group scope; self scope never narrows."""

    def _seed_sports(self) -> None:
        from tests.fixtures.circles import (
            grant_category_booking_admin,
            grant_staff_baseline,
        )
        grant_staff_baseline(TEST_USER)
        grant_category_booking_admin(TEST_USER, "Sports Facilities")

    def test_category_edge_decides_own_category(self):
        """A sports approver decides sports bookings (G-m via the edge)."""
        self._seed_sports()
        self._gate_access(
            {"id": TEST_USER}, "venues", "group", "modify",
            category="Sports Facilities",
        )

    def test_category_edge_does_not_decide_elsewhere(self):
        """The narrowest-path rule: no science-labs membership, no G-m
        outside the category — the family-level edges (baseline viewer)
        carry no modify."""
        self._seed_sports()
        with self.assertRaises(api_errors.ForbiddenError):
            self._gate_access(
                {"id": TEST_USER}, "venues", "group", "modify",
                category="Science Labs",
            )

    def test_self_scope_never_narrowed(self):
        """Own-booking powers survive a weaker category edge (the
        science-labs-viewer trap): the S field resolves family-wide."""
        self._seed_sports()
        self._gate_access(
            {"id": TEST_USER}, "venues", "self", "create",
            category="Sports Facilities",
        )

    def test_family_level_admin_decides_any_category(self):
        """A venues:admin holder (no category membership) decides
        everywhere: without a matching category edge, family edges max."""
        from campus.api.resources.circle import ACCESS_ADMIN
        from tests.fixtures.circles import grant_family_access

        grant_family_access(TEST_USER, "venues", ACCESS_ADMIN)
        self._gate_access(
            {"id": TEST_USER}, "venues", "group", "modify",
            category="Sports Facilities",
        )
        self._gate_access(
            {"id": TEST_USER}, "venues", "group", "modify",
            category="Science Labs",
        )


if __name__ == "__main__":
    unittest.main()
