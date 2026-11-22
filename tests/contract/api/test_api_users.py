"""HTTP contract tests for campus.api users endpoints (#1202).

These tests verify the HTTP interface contract for the inverted
membership check: which role circles a user holds, resolved
transitively through the shared membership resolver.

NOTE: All /users/ endpoints require authentication (Basic or Bearer).
This is enforced via before_request hook in the API blueprint. Reads
stay open (no role membership required), consistent with the circles
reads.

Users Endpoints Reference:
- GET    /users/{user_id}/roles - List the user's role memberships (transitive)
"""

import unittest

from campus.common import schema
from tests.fixtures import services
from tests.fixtures.tokens import create_test_token, get_bearer_auth_headers


class TestApiUsersContract(unittest.TestCase):
    """HTTP contract tests for /api/v1/users/ endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.apps_app
        cls.user_id = schema.UserID("test.user@campus.test")

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        self.manager.clear_test_data()

        self.client = self.app.test_client()

        self.token = create_test_token(self.user_id)
        self.auth_headers = get_bearer_auth_headers(self.token)

    def _resource_circle(self, role_circle_name: str) -> str:
        """Resolve a seeded role circle's ID by name (bootstrap)."""
        from campus.api.resources.circle import circle_storage
        from campus.common import schema

        role = circle_storage.get_matching({"name": role_circle_name})
        assert role, f"No '{role_circle_name}' circle: run the bootstrap"
        return str(schema.CampusID(role[0][schema.CAMPUS_KEY]))

    def _grant_direct(self, email: str, role_circle_name: str) -> None:
        """Add the user's circle directly to a role circle."""
        from campus.api import resources
        from campus.api.resources.circle import circle_storage
        from campus.common import schema

        if not circle_storage.get_matching({"name": email}):
            resources.circle.new(name=email, tag="user")
        role_id = schema.CampusID(self._resource_circle(role_circle_name))
        resources.circle.members.add(
            role_id,
            member_id=schema.CampusID(email),
            access_value=15,
        )

    def _grant_via_group(
            self, email: str, group_name: str, role_circle_name: str,
    ) -> None:
        """Put the user in a group and the group in a role circle."""
        from campus.api import resources
        from campus.api.resources.circle import circle_storage
        from campus.common import schema

        if not circle_storage.get_matching({"name": email}):
            resources.circle.new(name=email, tag="user")
        group = resources.circle.new(name=group_name, tag="group")
        group_id = schema.CampusID(group.id)
        resources.circle.members.add(
            group_id,
            member_id=schema.CampusID(email),
            access_value=15,
        )
        role_id = schema.CampusID(self._resource_circle(role_circle_name))
        resources.circle.members.add(
            role_id,
            member_id=group_id,
            access_value=15,
        )

    def test_get_user_roles_lists_direct_and_transitive(self):
        """GET /users/{id}/roles answers direct and group-held roles."""
        email = "roles.mixed@campus.test"
        self._grant_direct(email, "bookings.admin")
        self._grant_via_group(email, "timetable-staff", "timetable.admin")

        response = self.client.get(
            f"/api/v1/users/{email}/roles",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["user_id"], email)
        names = [role["name"] for role in data["roles"]]
        self.assertEqual(names, ["bookings.admin", "timetable.admin"])
        by_name = {role["name"]: role for role in data["roles"]}
        self.assertTrue(by_name["bookings.admin"]["direct"])
        self.assertEqual(by_name["bookings.admin"]["via"], [])
        self.assertFalse(by_name["timetable.admin"]["direct"])
        self.assertEqual(
            by_name["timetable.admin"]["via"], ["timetable-staff"]
        )

    def test_get_user_roles_unknown_user_returns_empty(self):
        """A user with no memberships answers an empty list, not 404."""
        response = self.client.get(
            "/api/v1/users/nobody@campus.test/roles",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["user_id"], "nobody@campus.test")
        self.assertEqual(data["roles"], [])

    def test_get_user_roles_requires_auth(self):
        """GET /users/{id}/roles without auth returns 401."""
        response = self.client.get("/api/v1/users/nobody@campus.test/roles")

        self.assertEqual(response.status_code, 401)

    def test_get_user_roles_reads_stay_open(self):
        """No role membership required, consistent with circles reads."""
        email = "roles.open@campus.test"
        self._grant_direct(email, "circles.admin")
        outsider = schema.UserID("outsider.read@campus.test")
        outsider_headers = get_bearer_auth_headers(
            create_test_token(outsider)
        )

        response = self.client.get(
            f"/api/v1/users/{email}/roles",
            headers=outsider_headers
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [role["name"] for role in response.get_json()["roles"]],
            ["circles.admin"],
        )

    def test_get_user_roles_ignores_non_role_circles(self):
        """Only role circles (tag "role") are enumerated."""
        from campus.api import resources
        from campus.api.resources.circle import circle_storage
        from campus.common import schema

        email = "roles.plain@campus.test"
        if not circle_storage.get_matching({"name": email}):
            resources.circle.new(name=email, tag="user")
        group = resources.circle.new(name="plain-group", tag="group")
        resources.circle.members.add(
            schema.CampusID(group.id),
            member_id=schema.CampusID(email),
            access_value=15,
        )

        response = self.client.get(
            f"/api/v1/users/{email}/roles",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["roles"], [])


if __name__ == "__main__":
    unittest.main()
