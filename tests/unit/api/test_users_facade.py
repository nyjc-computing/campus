"""Unit tests for the users directory facade (#1226).

The users family is read-only by construction: group/self read only,
no write semantics for any principal. The staff:viewer baseline
carries group-read (full list); student:guest does not (their slice
is the facade's query rewrite over circles they can read — guest
memberships confer nothing, viewer-or-above confers the circle's
email-member roster, and the caller always sees themselves).
"""

import unittest
from unittest.mock import patch

import flask

from campus.common import env
from campus.common.errors import api_errors

# Configure test storage before importing storage-backed modules
env.set('STORAGE_MODE', "1")

STAFF = "teacher@campus.test"
STUDENT = "student@campus.test"
CLASSMATE = "classmate@campus.test"
ORGANISER = "organiser@campus.test"
OUTSIDER = "outsider@campus.test"


def _ensure_user_circle(user_id: str) -> None:
    """Members address user circles: a roster add needs one first."""
    from campus.api import resources
    from campus.api.resources.circle import circle_storage

    if not circle_storage.get_matching({"name": user_id}):
        resources.circle.new(name=user_id, tag="user")


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

    def _seed_primary_group(self, name: str, member: str, access_value: int):
        """Seed a primary group (a provisioning artifact the bootstrap
        does not create) with one member."""
        from campus.api import resources
        from campus.api.resources.circle import circle_storage
        from campus.common import schema

        _ensure_user_circle(member)
        if not circle_storage.get_matching({"name": name}):
            resources.circle.new(name=name, tag="group")
        circle = circle_storage.get_matching({"name": name})[0]
        circle_id = schema.CampusID(circle[schema.CAMPUS_KEY])
        resources.circle.members.add(
            circle_id,
            member_id=schema.CampusID(member),
            access_value=access_value,
        )

    def _seed_club(self, roster: dict[str, int]) -> None:
        """Seed one member-list circle (tag `group`) with the roster."""
        from campus.api import resources
        from campus.api.resources.circle import circle_storage
        from campus.common import schema

        for member in roster:
            _ensure_user_circle(member)
        resources.circle.new(name="basketball", tag="group")
        circle = circle_storage.get_matching({"name": "basketball"})[0]
        circle_id = schema.CampusID(circle[schema.CAMPUS_KEY])
        for member, access_value in roster.items():
            resources.circle.members.add(
                circle_id,
                member_id=schema.CampusID(member),
                access_value=access_value,
            )


class TestUsersFamilyGate(GateTestBase):
    """The users family honors read only — no write semantics at all."""

    def test_group_write_not_honored(self):
        """Even a campus admin's family table rejects write checks."""
        from campus.api.authz import require_resource_access

        app = flask.Flask(__name__)
        with app.test_request_context():
            flask.g.current_user = {"id": STAFF}
            with self.assertRaises(api_errors.ForbiddenError) as ctx:
                require_resource_access("users", "group", "create")
            self.assertIn("does not honor", str(ctx.exception))

    def test_staff_baseline_group_read_passes(self):
        """The staff:viewer baseline carries group-read on users."""
        from campus.api.authz import require_resource_access
        from tests.fixtures.circles import grant_staff_baseline

        grant_staff_baseline(STAFF)
        app = flask.Flask(__name__)
        with app.test_request_context():
            flask.g.current_user = {"id": STAFF}
            require_resource_access("users", "group", "read")

    def test_student_guest_group_read_denied_self_read_passes(self):
        """student:guest confers no group-read but carries self-read."""
        from campus.api.authz import require_resource_access
        from campus.api.resources.circle import ACCESS_GUEST

        self._seed_primary_group("student", STUDENT, ACCESS_GUEST)
        app = flask.Flask(__name__)
        with app.test_request_context():
            flask.g.current_user = {"id": STUDENT}
            with self.assertRaises(api_errors.ForbiddenError):
                require_resource_access("users", "group", "read")
            require_resource_access("users", "self", "read")


class TestCircleVisibleSet(GateTestBase):
    """The scoped slice: circles the caller can read, plus self."""

    def test_viewer_membership_confers_roster(self):
        """Viewer on a club circle sees its whole email-member roster —
        including members who themselves hold only guest."""
        from campus.api.resources.circle import ACCESS_GUEST, ACCESS_VIEWER
        from campus.api.routes.users import _circle_visible_user_ids

        self._seed_club({
            STUDENT: ACCESS_VIEWER,
            CLASSMATE: ACCESS_GUEST,
            ORGANISER: ACCESS_VIEWER,
        })
        self.assertEqual(
            _circle_visible_user_ids(STUDENT),
            {STUDENT, CLASSMATE, ORGANISER},
        )

    def test_guest_membership_confers_nothing(self):
        """A guest membership on a circle does not expose its roster."""
        from campus.api.resources.circle import ACCESS_GUEST, ACCESS_VIEWER
        from campus.api.routes.users import _circle_visible_user_ids

        self._seed_club({STUDENT: ACCESS_GUEST, CLASSMATE: ACCESS_VIEWER})
        self.assertEqual(_circle_visible_user_ids(STUDENT), {STUDENT})

    def test_caller_without_memberships_sees_themselves(self):
        """No readable circles: the slice is the caller's own record."""
        from campus.api.routes.users import _circle_visible_user_ids

        self.assertEqual(_circle_visible_user_ids(OUTSIDER), {OUTSIDER})


class TestFacadeList(GateTestBase):
    """The list view: staff full lane, scoped lane, search, pagination."""

    DIRECTORY = [
        {"id": STAFF, "name": "Tan Jin Wui", "activated_at": None},
        {"id": STUDENT, "name": "Student Tan", "activated_at": None},
        {"id": CLASSMATE, "name": "Classmate Lim", "activated_at": None},
        {"id": ORGANISER, "name": "Organiser Ong", "activated_at": None},
    ]

    def _call_list(self, user: str, **query):
        from campus.api.routes import users as users_routes

        app = flask.Flask(__name__)
        with app.test_request_context("/users/", query_string=query):
            flask.g.current_user = {"id": user}
            return users_routes.list_users()

    def test_staff_gets_full_list(self):
        from tests.fixtures.circles import grant_staff_baseline

        grant_staff_baseline(STAFF)
        with patch.object(
            users_module(), "_fetch_directory", return_value=self.DIRECTORY
        ):
            body, status = self._call_list(STAFF)
        self.assertEqual(status, 200)
        self.assertIsNone(body["next_cursor"])
        self.assertEqual(
            [record["id"] for record in body["users"]],
            [CLASSMATE, ORGANISER, STUDENT, STAFF],  # sorted by id
        )

    def test_scoped_student_gets_slice_with_search_and_paging(self):
        from campus.api.resources.circle import ACCESS_GUEST, ACCESS_VIEWER

        self._seed_club({
            STUDENT: ACCESS_VIEWER,
            CLASSMATE: ACCESS_GUEST,
            ORGANISER: ACCESS_VIEWER,
        })
        with patch.object(
            users_module(), "_fetch_directory", return_value=self.DIRECTORY
        ):
            body, status = self._call_list(STUDENT)
        self.assertEqual(status, 200)
        self.assertEqual(
            [record["id"] for record in body["users"]],
            [CLASSMATE, ORGANISER, STUDENT],  # STAFF invisible
        )
        # search narrows the slice
        with patch.object(
            users_module(), "_fetch_directory", return_value=self.DIRECTORY
        ):
            body, _ = self._call_list(STUDENT, q="lim")
        self.assertEqual(
            [record["id"] for record in body["users"]], [CLASSMATE]
        )
        # pagination: one per page, cursor walks the slice
        with patch.object(
            users_module(), "_fetch_directory", return_value=self.DIRECTORY
        ):
            page1, _ = self._call_list(STUDENT, limit="1")
        self.assertEqual(len(page1["users"]), 1)
        self.assertIsNotNone(page1["next_cursor"])
        with patch.object(
            users_module(), "_fetch_directory", return_value=self.DIRECTORY
        ):
            page2, _ = self._call_list(
                STUDENT, limit="1", cursor=page1["next_cursor"]
            )
        self.assertNotEqual(
            page1["users"][0]["id"], page2["users"][0]["id"]
        )

    def test_client_principal_denied(self):
        from campus.api.routes import users as users_routes

        app = flask.Flask(__name__)
        with app.test_request_context("/users/"):
            flask.g.current_user = None
            with self.assertRaises(api_errors.ForbiddenError):
                users_routes.list_users()


def users_module():
    from campus.api.routes import users as users_routes

    return users_routes
