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

    def _grant_direct(self, email: str, family: str) -> None:
        """Add the user's circle directly to a family's grant circle."""
        from campus.api import resources
        from campus.api.resources.circle import ACCESS_ADMIN, circle_storage
        from campus.common import schema

        if not circle_storage.get_matching({"name": email}):
            resources.circle.new(name=email, tag="user")
        family_id = schema.CampusID(self._resource_circle(family))
        resources.circle.members.add(
            family_id,
            member_id=schema.CampusID(email),
            access_value=ACCESS_ADMIN,
        )

    def _grant_via_group(
            self, email: str, group_name: str, family: str,
    ) -> None:
        """Put the user in a group and the group in a family grant circle."""
        from campus.api import resources
        from campus.api.resources.circle import (
            ACCESS_ADMIN,
            ACCESS_VIEWER,
            circle_storage,
        )
        from campus.common import schema

        if not circle_storage.get_matching({"name": email}):
            resources.circle.new(name=email, tag="user")
        group = resources.circle.new(name=group_name, tag="group")
        group_id = schema.CampusID(group.id)
        resources.circle.members.add(
            group_id,
            member_id=schema.CampusID(email),
            access_value=ACCESS_VIEWER,
        )
        family_id = schema.CampusID(self._resource_circle(family))
        resources.circle.members.add(
            family_id,
            member_id=group_id,
            access_value=ACCESS_ADMIN,
        )

    def test_get_user_roles_lists_direct_and_transitive(self):
        """GET /users/{id}/roles answers direct and group-held memberships."""
        email = "roles.mixed@campus.test"
        self._grant_direct(email, "subjcombi")
        self._grant_via_group(email, "timetable-staff", "timetable")

        response = self.client.get(
            f"/api/v1/users/{email}/roles",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["user_id"], email)
        # Every reachable circle lists (containment ancestors included:
        # the user is transitively "in" the root through their groups).
        by_path = {m["path"]: m for m in data["memberships"]}
        self.assertIn("nyjc.edu.sg", by_path)
        self.assertTrue(by_path["subjcombi"]["direct"])
        self.assertEqual(by_path["subjcombi"]["via"], [])
        self.assertFalse(by_path["timetable"]["direct"])
        self.assertEqual(
            by_path["timetable"]["via"], ["timetable-staff"]
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
        self.assertEqual(data["memberships"], [])

    def test_get_user_roles_requires_auth(self):
        """GET /users/{id}/roles without auth returns 401."""
        response = self.client.get("/api/v1/users/nobody@campus.test/roles")

        self.assertEqual(response.status_code, 401)

    def test_get_user_roles_reads_stay_open(self):
        """No role membership required, consistent with circles reads."""
        email = "roles.open@campus.test"
        self._grant_direct(email, "circles")
        outsider = schema.UserID("outsider.read@campus.test")
        outsider_headers = get_bearer_auth_headers(
            create_test_token(outsider)
        )

        response = self.client.get(
            f"/api/v1/users/{email}/roles",
            headers=outsider_headers
        )

        self.assertEqual(response.status_code, 200)
        paths = [m["path"] for m in response.get_json()["memberships"]]
        self.assertIn("circles", paths)

    def test_get_user_roles_lists_group_memberships(self):
        """Group memberships list with their path and edge value; user
        circles are excluded from the enumeration."""
        from campus.api import resources
        from campus.api.resources.circle import ACCESS_VIEWER, circle_storage
        from campus.common import schema

        email = "roles.plain@campus.test"
        if not circle_storage.get_matching({"name": email}):
            resources.circle.new(name=email, tag="user")
        group = resources.circle.new(name="plain-group", tag="group")
        resources.circle.members.add(
            schema.CampusID(group.id),
            member_id=schema.CampusID(email),
            access_value=ACCESS_VIEWER,
        )

        response = self.client.get(
            f"/api/v1/users/{email}/roles",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        memberships = response.get_json()["memberships"]
        by_path = {m["path"]: m for m in memberships}
        self.assertIn("plain-group", by_path)
        memberships = [by_path["plain-group"]]
        self.assertEqual(memberships[0]["access_value"], ACCESS_VIEWER)


if __name__ == "__main__":
    unittest.main()
