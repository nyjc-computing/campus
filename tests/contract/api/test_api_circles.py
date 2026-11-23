"""HTTP contract tests for campus.api circles endpoints.

These tests verify the HTTP interface contract for circle management operations.
They test status codes, response formats, and authentication behavior.

NOTE: ALL /circles/ endpoints require authentication (Basic or Bearer).
This is enforced via before_request hook in the API blueprint.

Circles Endpoints Reference:
- GET    /circles/                              - List all circles with optional tag filter
- POST   /circles/                              - Create a new circle
- GET    /circles/{circle_id}/                  - Get a single circle
- PATCH  /circles/{circle_id}/                  - Update a circle (name, description)
- DELETE /circles/{circle_id}/                  - Delete a circle
- POST   /circles/{circle_id}/move              - Move circle (not implemented - 501)
- GET    /circles/{circle_id}/members/          - Get circle members
- GET    /circles/{circle_id}/members/{member_id} - Probe one membership
                                                   (default resolves transitively; ?resolve=direct is direct-only)
- POST   /circles/{circle_id}/members/add       - Add a member to a circle
- DELETE /circles/{circle_id}/members/remove    - Remove a member from a circle
- PATCH  /circles/{circle_id}/members/          - Update member access level
- GET    /circles/{circle_id}/users             - Get users in circle (not implemented - 501)
"""

import unittest

from campus.common import schema
from tests.fixtures import services
from tests.fixtures.circles import grant_circle_admin
from tests.fixtures.tokens import create_test_token, get_bearer_auth_headers


class TestApiCirclesContract(unittest.TestCase):
    """HTTP contract tests for /api/v1/circles/ endpoints."""

    @classmethod
    def setUpClass(cls):
        # Reset storage before starting tests to ensure clean state

        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.apps_app

        # Create test user; the bearer token is re-created per test in
        # setUp() because clear_test_data() wipes the credentials storage.
        cls.user_id = schema.UserID("test.user@campus.test")

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        # Clear test data - no manual resource initialization needed
        self.manager.clear_test_data()

        self.client = self.app.test_client()

        # Re-create the bearer token after the clear: the token lives in
        # credentials storage, which clear_test_data() wipes.
        self.token = create_test_token(self.user_id)
        self.auth_headers = get_bearer_auth_headers(self.token)

        # Mutation routes are gated behind circles.admin; grant the
        # test user the role (clear_test_data wipes the circles).
        grant_circle_admin(str(self.user_id), "circles")

    def _create_test_circle(self, **overrides):
        """Helper to create a test circle via resource layer.

        Returns the circle ID.
        """
        from campus.api import resources

        data = {
            "name": "Test Circle",
            "description": "A test circle for contract testing",
            "tag": "test",
            "parents": {},
        }
        data.update(overrides)

        circle = resources.circle.new(**data)
        return str(circle.id)

    def _create_test_user_circle(self, email: str) -> str:
        """Helper to create a user circle (named after the email account).

        Returns the circle ID.
        """
        return self._create_test_circle(
            name=email,
            description=f"Personal circle for {email}",
            tag="user",
        )

    # Gate Tests (circle access control)

    def test_mutation_without_role_membership_returns_403(self):
        """POST /circles/ without circles.admin membership returns 403."""
        outsider = schema.UserID("outsider@campus.test")
        token = create_test_token(outsider)

        response = self.client.post(
            "/api/v1/circles/",
            json={
                "name": "Outsider Circle",
                "tag": "test",
            },
            headers=get_bearer_auth_headers(token)
        )

        self.assertEqual(response.status_code, 403)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "FORBIDDEN")

    def test_mutation_member_passes_and_reads_stay_open(self):
        """A circles.admin member can create; reads need no membership."""
        # The setUp grant makes the test user a circles.admin member.
        response = self.client.post(
            "/api/v1/circles/",
            json={
                "name": "Member Created Circle",
                "tag": "test",
            },
            headers=self.auth_headers
        )
        self.assertEqual(response.status_code, 201)
        circle_id = response.get_json()["id"]

        # Reads stay open: an outsider may list and read.
        outsider = schema.UserID("outsider@campus.test")
        outsider_headers = get_bearer_auth_headers(
            create_test_token(outsider)
        )
        listed = self.client.get(
            "/api/v1/circles/", headers=outsider_headers
        )
        self.assertEqual(listed.status_code, 200)
        detail = self.client.get(
            f"/api/v1/circles/{circle_id}/", headers=outsider_headers
        )
        self.assertEqual(detail.status_code, 200)

    def test_member_add_requires_role_membership(self):
        """POST /circles/{id}/members/add is member-only (escalation guard)."""
        self._create_test_user_circle("teacher@campus.test")
        circle_id = self._create_test_circle(name="Escalation Guard Circle")
        outsider = schema.UserID("outsider@campus.test")
        outsider_headers = get_bearer_auth_headers(
            create_test_token(outsider)
        )

        response = self.client.post(
            f"/api/v1/circles/{circle_id}/members/add",
            json={
                "member_id": "teacher@campus.test",
                "access_value": 126,
            },
            headers=outsider_headers
        )

        self.assertEqual(response.status_code, 403)

    # List Circles Tests

    def test_list_circles_requires_auth(self):
        """GET /circles/ without auth returns 401."""
        response = self.client.get("/api/v1/circles/")

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    def test_list_circles_unknown_token_returns_401(self):
        """GET /circles/ with an unknown bearer token returns 401 (#614)."""
        response = self.client.get(
            "/api/v1/circles/",
            headers={"Authorization": "Bearer not-a-real-token"}
        )

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    def test_list_circles_unknown_client_returns_401(self):
        """GET /circles/ with unknown Basic credentials returns 401 (#614)."""
        import base64
        credentials = base64.b64encode(
            b"no-such-client:no-such-secret").decode()

        response = self.client.get(
            "/api/v1/circles/",
            headers={"Authorization": f"Basic {credentials}"}
        )

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    def test_list_circles_returns_circles(self):
        """GET /circles/ returns list of circles."""
        # Create a test circle
        self._create_test_circle(name="List Test Circle", tag="list-test")

        response = self.client.get("/api/v1/circles/", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("data", data)
        self.assertIsInstance(data["data"], list)
        self.assertGreater(len(data["data"]), 0)

    def test_list_circles_with_tag_filter(self):
        """GET /circles/?tag={tag} filters circles by tag."""
        # Create a circle with specific tag
        self._create_test_circle(name="Tagged Circle", tag="filter-test")

        response = self.client.get(
            "/api/v1/circles/?tag=filter-test",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("data", data)
        # Should have at least our test circle
        self.assertGreater(len(data["data"]), 0)

    # Create Circle Tests

    def test_create_circle_requires_auth(self):
        """POST /circles/ without auth returns 401."""
        response = self.client.post(
            "/api/v1/circles/",
            json={
                "name": "Unauthorized Circle",
                "description": "Should not be created",
                "tag": "test",
            }
        )

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    def test_create_circle(self):
        """POST /circles/ creates a new circle."""
        response = self.client.post(
            "/api/v1/circles/",
            json={
                "name": "New Circle",
                "description": "A new test circle",
                "tag": "test",
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertIn("id", data)
        self.assertIn("name", data)
        self.assertEqual(data["name"], "New Circle")
        self.assertIn("description", data)
        self.assertIn("tag", data)

    def test_create_circle_with_parents(self):
        """POST /circles/ with parents creates circle with parent relationships."""
        # First create a parent circle
        parent_id = self._create_test_circle(name="Parent Circle", tag="parent")

        response = self.client.post(
            "/api/v1/circles/",
            json={
                "name": "Child Circle",
                "description": "A child circle",
                "tag": "child",
                "parents": {parent_id: 126},
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertIn("id", data)

    def test_create_circle_missing_name_returns_error(self):
        """POST /circles/ without name returns error."""
        response = self.client.post(
            "/api/v1/circles/",
            json={
                "description": "Missing name",
                "tag": "test",
            },
            headers=self.auth_headers
        )

        self.assertIn(response.status_code, (400, 422))

    def test_create_circle_missing_tag_returns_error(self):
        """POST /circles/ without tag returns error."""
        response = self.client.post(
            "/api/v1/circles/",
            json={
                "name": "Missing Tag",
            },
            headers=self.auth_headers
        )

        self.assertIn(response.status_code, (400, 422))

    def test_create_root_circle_with_parents_returns_error(self):
        """POST /circles/ with tag=root and parents returns 409."""
        response = self.client.post(
            "/api/v1/circles/",
            json={
                "name": "Invalid Root",
                "tag": "root",
                "parents": {"some-parent": 126},
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertEqual(data["error"]["code"], "CONFLICT")

    # Get Circle Tests

    def test_get_circle_by_id(self):
        """GET /circles/{circle_id}/ returns the circle."""
        circle_id = self._create_test_circle(name="Get Test Circle")

        response = self.client.get(
            f"/api/v1/circles/{circle_id}/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["id"], circle_id)
        self.assertIn("name", data)
        self.assertIn("description", data)
        self.assertIn("tag", data)
        self.assertIn("members", data)
        self.assertIn("sources", data)

    def test_get_circle_requires_auth(self):
        """GET /circles/{circle_id}/ without auth returns 401."""
        response = self.client.get("/api/v1/circles/some_id/")

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    def test_get_missing_circle_returns_error(self):
        """GET /circles/{circle_id}/ for non-existent circle returns 409."""
        response = self.client.get(
            "/api/v1/circles/nonexistent_id/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertEqual(data["error"]["code"], "CONFLICT")

    # Update Circle Tests

    def test_update_circle_name(self):
        """PATCH /circles/{circle_id}/ updates name (description optional)."""
        circle_id = self._create_test_circle(name="Original Name")

        response = self.client.patch(
            f"/api/v1/circles/{circle_id}/",
            json={"name": "Updated Name"},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {})

        # Verify the update
        get_response = self.client.get(
            f"/api/v1/circles/{circle_id}/",
            headers=self.auth_headers
        )
        circle_data = get_response.get_json()
        self.assertEqual(circle_data["name"], "Updated Name")

    def test_update_circle_description_only_returns_error(self):
        """PATCH /circles/{circle_id}/ with description only returns 422 (#501).

        The decided contract requires name; description alone is invalid.
        """
        circle_id = self._create_test_circle(description="Original Description")

        response = self.client.patch(
            f"/api/v1/circles/{circle_id}/",
            json={"description": "Updated Description"},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 422)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "VALIDATION_FAILED")

    def test_update_circle_both_fields(self):
        """PATCH /circles/{circle_id}/ updates both name and description."""
        circle_id = self._create_test_circle()

        response = self.client.patch(
            f"/api/v1/circles/{circle_id}/",
            json={
                "name": "New Name",
                "description": "New Description",
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)

    def test_update_circle_empty_body_returns_error(self):
        """PATCH /circles/{circle_id}/ without updates returns 400."""
        circle_id = self._create_test_circle()

        response = self.client.patch(
            f"/api/v1/circles/{circle_id}/",
            json={},
            headers=self.auth_headers
        )

        self.assertIn(response.status_code, (400, 422))
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertIn(data["error"]["code"], ("INVALID_REQUEST", "VALIDATION_FAILED"))

    def test_update_circle_requires_auth(self):
        """PATCH /circles/{circle_id}/ without auth returns 401."""
        circle_id = self._create_test_circle()

        response = self.client.patch(
            f"/api/v1/circles/{circle_id}/",
            json={"name": "Updated Name"}
        )

        self.assertEqual(response.status_code, 401)

    def test_update_missing_circle_returns_error(self):
        """PATCH /circles/{circle_id}/ for non-existent circle returns 409."""
        response = self.client.patch(
            "/api/v1/circles/nonexistent_id/",
            json={"name": "Updated Name"},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "CONFLICT")

    def test_create_circle_duplicate_name_returns_409(self):
        """POST /circles/ with an existing name returns 409 (#761)."""
        self._create_test_circle(name="Duplicate Name", tag="first")

        response = self.client.post(
            "/api/v1/circles/",
            json={
                "name": "Duplicate Name",
                "description": "Collides on name only",
                "tag": "second",
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "CONFLICT")

    def test_update_circle_duplicate_name_returns_409(self):
        """PATCH /circles/{circle_id}/ to another circle's name returns 409 (#761)."""
        first_id = self._create_test_circle(name="First Circle")
        second_id = self._create_test_circle(name="Second Circle")

        response = self.client.patch(
            f"/api/v1/circles/{second_id}/",
            json={"name": "First Circle"},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "CONFLICT")

        # The failed rename must not have touched either circle
        first_response = self.client.get(
            f"/api/v1/circles/{first_id}/",
            headers=self.auth_headers
        )
        self.assertEqual(first_response.get_json()["name"], "First Circle")

    def test_update_circle_same_name_is_noop(self):
        """PATCH /circles/{circle_id}/ with its own name returns 200 (#761)."""
        circle_id = self._create_test_circle(name="Stable Name")

        response = self.client.patch(
            f"/api/v1/circles/{circle_id}/",
            json={"name": "Stable Name"},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)

    # Delete Circle Tests

    def test_delete_circle(self):
        """DELETE /circles/{circle_id}/ removes the circle."""
        circle_id = self._create_test_circle(name="To Be Deleted")

        response = self.client.delete(
            f"/api/v1/circles/{circle_id}/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {})

        # Verify it's deleted
        get_response = self.client.get(
            f"/api/v1/circles/{circle_id}/",
            headers=self.auth_headers
        )
        self.assertEqual(get_response.status_code, 409)

    def test_delete_circle_requires_auth(self):
        """DELETE /circles/{circle_id}/ without auth returns 401."""
        circle_id = self._create_test_circle()

        response = self.client.delete(
            f"/api/v1/circles/{circle_id}/"
        )

        self.assertEqual(response.status_code, 401)

    def test_delete_missing_circle_returns_error(self):
        """DELETE /circles/{circle_id}/ for non-existent circle returns 409."""
        response = self.client.delete(
            "/api/v1/circles/nonexistent_id/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)

    # Move Circle Tests (Not Implemented)

    def test_move_circle_not_implemented(self):
        """POST /circles/{circle_id}/move returns 501."""
        circle_id = self._create_test_circle()

        self.client.post(
            f"/api/v1/circles/{circle_id}/move",
            headers=self.auth_headers
        )

    # Circle Members Tests

    def test_get_circle_members(self):
        """GET /circles/{circle_id}/members/ returns members dict."""
        circle_id = self._create_test_circle()

        response = self.client.get(
            f"/api/v1/circles/{circle_id}/members/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsInstance(data, dict)

    def test_get_circle_members_requires_auth(self):
        """GET /circles/{circle_id}/members/ without auth returns 401."""
        circle_id = self._create_test_circle()

        response = self.client.get(
            f"/api/v1/circles/{circle_id}/members/"
        )

        self.assertEqual(response.status_code, 401)

    def test_probe_circle_member(self):
        """GET /circles/{id}/members/{member_id} returns the transitive shape."""
        self._create_test_user_circle("teacher.probe@campus.test")
        circle_id = self._create_test_circle(name="Probe Circle")
        self.client.post(
            f"/api/v1/circles/{circle_id}/members/add",
            json={
                "member_id": "teacher.probe@campus.test",
                "access_value": 126,
            },
            headers=self.auth_headers
        )

        response = self.client.get(
            f"/api/v1/circles/{circle_id}/members/teacher.probe@campus.test/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["member_id"], "teacher.probe@campus.test")
        self.assertEqual(data["access_value"], 126)
        # The #1207 default: transitive shape, direct edge flagged.
        self.assertEqual(
            set(data), {"member_id", "access_value", "direct", "via"}
        )
        self.assertIs(data["direct"], True)
        self.assertEqual(data["via"], [])

    def test_probe_absent_member_returns_404(self):
        """GET /circles/{id}/members/{member_id} for a non-member returns 404."""
        circle_id = self._create_test_circle(name="Probe Absent Circle")

        response = self.client.get(
            f"/api/v1/circles/{circle_id}/members/ghost@campus.test/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 404)

    def test_probe_member_missing_circle_returns_409(self):
        """GET /circles/{id}/members/{member_id} for a missing circle returns 409."""
        response = self.client.get(
            "/api/v1/circles/nonexistent_id/members/some-member-id/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "CONFLICT")

    def test_probe_member_requires_auth(self):
        """GET /circles/{id}/members/{member_id} without auth returns 401."""
        circle_id = self._create_test_circle()

        response = self.client.get(
            f"/api/v1/circles/{circle_id}/members/some-member-id/"
        )

        self.assertEqual(response.status_code, 401)

    def test_probe_member_reads_stay_open(self):
        """The probe needs no role membership, like the members listing."""
        self._create_test_user_circle("teacher.open@campus.test")
        circle_id = self._create_test_circle(name="Probe Open Circle")
        self.client.post(
            f"/api/v1/circles/{circle_id}/members/add",
            json={
                "member_id": "teacher.open@campus.test",
                "access_value": 126,
            },
            headers=self.auth_headers
        )
        outsider = schema.UserID("outsider@campus.test")
        outsider_headers = get_bearer_auth_headers(
            create_test_token(outsider)
        )

        response = self.client.get(
            f"/api/v1/circles/{circle_id}/members/teacher.open@campus.test/",
            headers=outsider_headers
        )

        self.assertEqual(response.status_code, 200)

    # Membership probe (#1202/#1207): the default resolves transitively
    # through the shared resolver — the enforcement gate's semantics;
    # ?resolve=direct is the explicit direct-only spelling.

    def _wire_group_membership(
            self, email: str, group_name: str, circle_name: str,
    ) -> str:
        """Create circle -> group -> user circle; returns the circle ID."""
        self._create_test_user_circle(email)
        group_id = self._create_test_circle(name=group_name, tag="group")
        circle_id = self._create_test_circle(name=circle_name)
        self.client.post(
            f"/api/v1/circles/{group_id}/members/add",
            json={"member_id": email, "access_value": 18},
            headers=self.auth_headers
        )
        self.client.post(
            f"/api/v1/circles/{circle_id}/members/add",
            json={"member_id": group_id, "access_value": 126},
            headers=self.auth_headers
        )
        return circle_id

    def test_probe_default_is_transitive(self):
        """#1207: an unparameterized probe resolves group-only members."""
        circle_id = self._wire_group_membership(
            "teacher.grouponly@campus.test",
            "grouponly-group",
            "Probe Default Circle",
        )

        response = self.client.get(
            f"/api/v1/circles/{circle_id}/members/"
            "teacher.grouponly@campus.test/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertFalse(data["direct"])
        self.assertEqual(data["via"], ["grouponly-group"])

    def test_probe_direct_mode_stays_direct_only(self):
        """?resolve=direct keeps answering the direct dict only."""
        circle_id = self._wire_group_membership(
            "teacher.explicitdirect@campus.test",
            "explicitdirect-group",
            "Probe Explicit Direct Circle",
        )

        response = self.client.get(
            f"/api/v1/circles/{circle_id}/members/"
            "teacher.explicitdirect@campus.test/?resolve=direct",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 404)
        message = response.get_json()["error"]["message"]
        # The direct-mode caller asked for exactly that: no
        # switchover hint in the message.
        self.assertNotIn("resolve=direct", message)

    def test_probe_default_unreachable_404_hints_at_direct(self):
        """A transitive-mode miss points direct-only callers at the
        explicit spelling (#1207 footgun guard)."""
        circle_id = self._wire_group_membership(
            "teacher.detached404@campus.test",
            "detached404-group",
            "Probe Hint Circle",
        )
        # Detach the group from the circle: reachable nowhere. Members
        # are keyed by the identifier they were added with — the UID.
        from campus.api.resources.circle import circle_storage
        from campus.common import schema as schema_mod

        group_record = circle_storage.get_matching(
            {"name": "detached404-group"}
        )[0]
        self.client.delete(
            f"/api/v1/circles/{circle_id}/members/remove",
            json={"member_id": str(schema_mod.CampusID(
                group_record[schema_mod.CAMPUS_KEY]
            ))},
            headers=self.auth_headers
        )

        response = self.client.get(
            f"/api/v1/circles/{circle_id}/members/"
            "teacher.detached404@campus.test/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 404)
        message = response.get_json()["error"]["message"]
        self.assertIn("resolve=direct", message)

    def test_probe_transitive_resolves_group_member(self):
        """?resolve=transitive answers a group-only member with the chain."""
        circle_id = self._wire_group_membership(
            "teacher.viagroup@campus.test",
            "viagroup-group",
            "Probe Transitive Circle",
        )

        response = self.client.get(
            f"/api/v1/circles/{circle_id}/members/"
            "teacher.viagroup@campus.test/?resolve=transitive",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["member_id"], "teacher.viagroup@campus.test")
        self.assertEqual(data["access_value"], 18)
        self.assertFalse(data["direct"])
        self.assertEqual(data["via"], ["viagroup-group"])

    def test_probe_transitive_direct_member(self):
        """A direct member probes direct=True with an empty via."""
        self._create_test_user_circle("teacher.direct@campus.test")
        circle_id = self._create_test_circle(name="Probe Direct Circle")
        self.client.post(
            f"/api/v1/circles/{circle_id}/members/add",
            json={
                "member_id": "teacher.direct@campus.test",
                "access_value": 126,
            },
            headers=self.auth_headers
        )

        response = self.client.get(
            f"/api/v1/circles/{circle_id}/members/"
            "teacher.direct@campus.test/?resolve=transitive",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["direct"])
        self.assertEqual(data["via"], [])

    def test_probe_transitive_reports_max_access_value(self):
        """Multi-path hits report the max; ?resolve=direct the edge."""
        email = "teacher.multipath@campus.test"
        self._create_test_user_circle(email)
        group_id = self._create_test_circle(name="multipath-group", tag="group")
        circle_id = self._create_test_circle(name="Probe Multipath Circle")
        self.client.post(
            f"/api/v1/circles/{group_id}/members/add",
            json={"member_id": email, "access_value": 18},
            headers=self.auth_headers
        )
        self.client.post(
            f"/api/v1/circles/{circle_id}/members/add",
            json={"member_id": group_id, "access_value": 126},
            headers=self.auth_headers
        )
        # Direct edge with a LOWER value than the group path.
        self.client.post(
            f"/api/v1/circles/{circle_id}/members/add",
            json={"member_id": email, "access_value": 2},
            headers=self.auth_headers
        )

        direct_response = self.client.get(
            f"/api/v1/circles/{circle_id}/members/{email}/"
            "?resolve=direct",
            headers=self.auth_headers
        )
        default_response = self.client.get(
            f"/api/v1/circles/{circle_id}/members/{email}/",
            headers=self.auth_headers
        )

        self.assertEqual(direct_response.status_code, 200)
        self.assertEqual(direct_response.get_json()["access_value"], 2)
        self.assertEqual(default_response.status_code, 200)
        self.assertEqual(default_response.get_json()["access_value"], 18)

    def test_probe_transitive_unreachable_returns_404(self):
        """?resolve=transitive 404s when no path reaches the member."""
        self._create_test_user_circle("teacher.detached@campus.test")
        detached_id = self._create_test_circle(
            name="Detached Group", tag="group"
        )
        self.client.post(
            f"/api/v1/circles/{detached_id}/members/add",
            json={
                "member_id": "teacher.detached@campus.test",
                "access_value": 126,
            },
            headers=self.auth_headers
        )
        circle_id = self._create_test_circle(name="Probe Detached Circle")

        response = self.client.get(
            f"/api/v1/circles/{circle_id}/members/"
            "teacher.detached@campus.test/?resolve=transitive",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 404)

    def test_probe_rejects_unknown_resolve_value(self):
        """An unknown resolve value is a 422 validation error."""
        self._create_test_user_circle("teacher.typo@campus.test")
        circle_id = self._create_test_circle(name="Probe Typo Circle")

        response = self.client.get(
            f"/api/v1/circles/{circle_id}/members/"
            "teacher.typo@campus.test/?resolve=recursivce",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 422)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "VALIDATION_FAILED")

    def test_probe_direct_mode_returns_direct_shape(self):
        """?resolve=direct keeps the two-field shape (#1207)."""
        self._create_test_user_circle("teacher.optedin@campus.test")
        circle_id = self._create_test_circle(name="Probe Optedin Circle")
        self.client.post(
            f"/api/v1/circles/{circle_id}/members/add",
            json={
                "member_id": "teacher.optedin@campus.test",
                "access_value": 126,
            },
            headers=self.auth_headers
        )

        response = self.client.get(
            f"/api/v1/circles/{circle_id}/members/"
            "teacher.optedin@campus.test/?resolve=direct",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(set(data), {"member_id", "access_value"})
        self.assertEqual(data["access_value"], 126)

    def test_get_members_missing_circle_returns_error(self):
        """GET /circles/{circle_id}/members/ for non-existent circle returns 409."""
        response = self.client.get(
            "/api/v1/circles/nonexistent_id/members/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)

    def test_add_circle_member(self):
        """POST /circles/{circle_id}/members/add adds a member."""
        # Create two circles
        parent_id = self._create_test_circle(name="Parent Circle")
        child_id = self._create_test_circle(name="Child Circle")

        response = self.client.post(
            f"/api/v1/circles/{parent_id}/members/add",
            json={
                "member_id": child_id,
                "access_value": 126,
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {})

        # Verify member was added
        members_response = self.client.get(
            f"/api/v1/circles/{parent_id}/members/",
            headers=self.auth_headers
        )
        members_data = members_response.get_json()
        self.assertIn(child_id, members_data)

    def test_add_user_member(self):
        """POST /members/add adds a user via their email-named user circle."""
        self._create_test_user_circle("teacher@campus.test")
        circle_id = self._create_test_circle(name="User Member Circle")

        response = self.client.post(
            f"/api/v1/circles/{circle_id}/members/add",
            json={
                "member_id": "teacher@campus.test",
                "access_value": 126,
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)

        members_response = self.client.get(
            f"/api/v1/circles/{circle_id}/members/",
            headers=self.auth_headers
        )
        self.assertEqual(
            members_response.get_json().get("teacher@campus.test"), 126
        )

    def test_add_user_member_without_user_circle_returns_error(self):
        """POST /members/add with no user circle for the email returns 409."""
        circle_id = self._create_test_circle(name="No User Circle Member")

        response = self.client.post(
            f"/api/v1/circles/{circle_id}/members/add",
            json={
                "member_id": "ghost@campus.test",
                "access_value": 126,
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)

    def test_add_user_member_with_dotted_email(self):
        """Dots in a user-circle member key survive storage (no splitting)."""
        self._create_test_user_circle("t.user@campus.test")
        circle_id = self._create_test_circle(name="Dotted Email Member Circle")

        response = self.client.post(
            f"/api/v1/circles/{circle_id}/members/add",
            json={
                "member_id": "t.user@campus.test",
                "access_value": 126,
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        members_response = self.client.get(
            f"/api/v1/circles/{circle_id}/members/",
            headers=self.auth_headers
        )
        self.assertIn("t.user@campus.test", members_response.get_json())

    def test_remove_user_member(self):
        """DELETE /members/remove removes a user-circle member."""
        self._create_test_user_circle("teacher.remove@campus.test")
        circle_id = self._create_test_circle(name="User Member Remove Circle")
        self.client.post(
            f"/api/v1/circles/{circle_id}/members/add",
            json={
                "member_id": "teacher.remove@campus.test",
                "access_value": 126,
            },
            headers=self.auth_headers
        )

        response = self.client.delete(
            f"/api/v1/circles/{circle_id}/members/remove",
            json={
                "member_id": "teacher.remove@campus.test",
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        members_response = self.client.get(
            f"/api/v1/circles/{circle_id}/members/",
            headers=self.auth_headers
        )
        self.assertNotIn(
            "teacher.remove@campus.test", members_response.get_json()
        )

    def test_add_circle_member_requires_auth(self):
        """POST /circles/{circle_id}/members/add without auth returns 401."""
        circle_id = self._create_test_circle()

        response = self.client.post(
            f"/api/v1/circles/{circle_id}/members/add",
            json={
                "member_id": "some-member-id",
                "access_value": 126,
            }
        )

        self.assertEqual(response.status_code, 401)

    def test_add_member_to_missing_circle_returns_error(self):
        """POST /circles/{circle_id}/members/add for non-existent circle returns 409."""
        response = self.client.post(
            "/api/v1/circles/nonexistent_id/members/add",
            json={
                "member_id": "some-member-id",
                "access_value": 126,
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)

    def test_add_nonexistent_member_returns_error(self):
        """POST /circles/{circle_id}/members/add with non-existent member returns 409."""
        circle_id = self._create_test_circle()

        response = self.client.post(
            f"/api/v1/circles/{circle_id}/members/add",
            json={
                "member_id": "nonexistent-member-id",
                "access_value": 126,
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)

    def test_remove_circle_member(self):
        """DELETE /circles/{circle_id}/members/remove removes a member."""
        # Create two circles and add member relationship
        parent_id = self._create_test_circle(name="Parent Circle Remove")
        child_id = self._create_test_circle(name="Child Circle Remove")

        # Add the member first
        self.client.post(
            f"/api/v1/circles/{parent_id}/members/add",
            json={
                "member_id": child_id,
                "access_value": 126,
            },
            headers=self.auth_headers
        )

        # Remove the member
        response = self.client.delete(
            f"/api/v1/circles/{parent_id}/members/remove",
            json={
                "member_id": child_id,
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {})

        # Verify member was removed
        members_response = self.client.get(
            f"/api/v1/circles/{parent_id}/members/",
            headers=self.auth_headers
        )
        members_data = members_response.get_json()
        self.assertNotIn(child_id, members_data)

    def test_remove_circle_member_requires_auth(self):
        """DELETE /circles/{circle_id}/members/remove without auth returns 401."""
        circle_id = self._create_test_circle()

        response = self.client.delete(
            f"/api/v1/circles/{circle_id}/members/remove",
            json={"member_id": "some-member-id"}
        )

        self.assertEqual(response.status_code, 401)

    def test_remove_member_from_missing_circle_returns_error(self):
        """DELETE /circles/{circle_id}/members/remove for non-existent circle returns 409."""
        response = self.client.delete(
            "/api/v1/circles/nonexistent_id/members/remove",
            json={"member_id": "some-member-id"},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)

    def test_remove_nonexistent_member_returns_error(self):
        """DELETE /circles/{circle_id}/members/remove for non-existent member returns 409."""
        circle_id = self._create_test_circle()

        response = self.client.delete(
            f"/api/v1/circles/{circle_id}/members/remove",
            json={"member_id": "nonexistent-member-id"},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)

    def test_patch_circle_member_access(self):
        """PATCH /circles/{circle_id}/members/ updates member access level."""
        # Create two circles and add member relationship
        parent_id = self._create_test_circle(name="Parent Circle Patch")
        child_id = self._create_test_circle(name="Child Circle Patch")

        # Add the member first
        self.client.post(
            f"/api/v1/circles/{parent_id}/members/add",
            json={
                "member_id": child_id,
                "access_value": 126,
            },
            headers=self.auth_headers
        )

        # Update the access level
        response = self.client.patch(
            f"/api/v1/circles/{parent_id}/members/",
            json={
                "member_id": child_id,
                "access_value": 126,
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)

        # Verify access was updated
        members_response = self.client.get(
            f"/api/v1/circles/{parent_id}/members/",
            headers=self.auth_headers
        )
        members_data = members_response.get_json()
        self.assertEqual(members_data[child_id], 126)

    def test_patch_circle_member_requires_auth(self):
        """PATCH /circles/{circle_id}/members/ without auth returns 401."""
        circle_id = self._create_test_circle()

        response = self.client.patch(
            f"/api/v1/circles/{circle_id}/members/",
            json={
                "member_id": "some-member-id",
                "access_value": 126,
            }
        )

        self.assertEqual(response.status_code, 401)

    def test_patch_member_for_missing_circle_returns_error(self):
        """PATCH /circles/{circle_id}/members/ for non-existent circle returns 409."""
        response = self.client.patch(
            "/api/v1/circles/nonexistent_id/members/",
            json={
                "member_id": "some-member-id",
                "access_value": 126,
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)

    # Get Circle Users Tests (Not Implemented)

    def test_probe_family_access_answers_authority(self):
        """GET /circles/{id}/access/{member} answers what the gate does.

        A committee member resolves group-admin on the family through
        the member circle's edge; an outsider resolves zeros; the
        wildcard answers admin on any circle."""
        from campus.api.resources.circle import (
            ACCESS_ADMIN,
            ACCESS_VIEWER,
            circle_storage,
        )
        from tests.fixtures.circles import grant_campus_admin

        email = "chair.access@campus.test"
        self._create_test_user_circle(email)
        family_id = str(schema.CampusID(
            circle_storage.get_matching({"name": "timetable"})[0][
                schema.CAMPUS_KEY
            ]
        ))
        committee_id = self._create_test_circle(
            name="committees.timetabling", tag="group"
        )
        self.client.post(
            f"/api/v1/circles/{committee_id}/members/add",
            json={"member_id": email, "access_value": ACCESS_VIEWER},
            headers=self.auth_headers
        )
        self.client.post(
            f"/api/v1/circles/{family_id}/members/add",
            json={"member_id": committee_id, "access_value": ACCESS_ADMIN},
            headers=self.auth_headers
        )

        chair = self.client.get(
            f"/api/v1/circles/{family_id}/access/{email}/",
            headers=self.auth_headers
        )
        self.assertEqual(chair.status_code, 200)
        data = chair.get_json()
        self.assertTrue(data["g"] & 0b1000000, "group-create bit expected")

        outsider = self.client.get(
            f"/api/v1/circles/{family_id}/access/nobody@campus.test/",
            headers=self.auth_headers
        )
        self.assertEqual(outsider.status_code, 200)
        self.assertEqual(outsider.get_json()["g"], 0)

        wildcard_email = "wildcard.access@campus.test"
        grant_campus_admin(wildcard_email)
        wildcard = self.client.get(
            f"/api/v1/circles/{family_id}/access/{wildcard_email}/",
            headers=self.auth_headers
        )
        self.assertEqual(wildcard.status_code, 200)
        self.assertTrue(wildcard.get_json()["wildcard"])

    def test_get_circle_users_lists_transitive_users(self):
        """GET /circles/{circle_id}/users enumerates contained users."""
        email = "teacher.users@campus.test"
        group_id = self._create_test_circle(name="users-group", tag="group")
        circle_id = self._create_test_circle(name="Users Circle")
        self._create_test_user_circle(email)
        self.client.post(
            f"/api/v1/circles/{group_id}/members/add",
            json={"member_id": email, "access_value": 126},
            headers=self.auth_headers
        )
        self.client.post(
            f"/api/v1/circles/{circle_id}/members/add",
            json={"member_id": group_id, "access_value": 126},
            headers=self.auth_headers
        )

        response = self.client.get(
            f"/api/v1/circles/{circle_id}/users",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["circle_id"], circle_id)
        self.assertEqual(data["users"], [email])


if __name__ == '__main__':
    unittest.main()
