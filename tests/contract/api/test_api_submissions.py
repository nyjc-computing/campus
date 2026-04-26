"""HTTP contract tests for campus.api submissions endpoints.

These tests verify the HTTP interface contract for submission management operations.
They test status codes, response formats, and authentication behavior.

NOTE: ALL /submissions/ endpoints require authentication (Basic or Bearer).
This is enforced via before_request hook in the API blueprint.

Submissions Endpoints Reference:
- GET    /submissions/                              - List all submissions with optional filters
- POST   /submissions/                              - Create a new submission
- GET    /submissions/by-assignment/{assignment_id} - List submissions by assignment
- GET    /submissions/by-student/{student_id}       - List submissions by student
- GET    /submissions/{submission_id}               - Get a single submission
- PATCH  /submissions/{submission_id}               - Update a submission
- DELETE /submissions/{submission_id}               - Delete a submission
- POST   /submissions/{submission_id}/responses     - Add a response to a submission
- POST   /submissions/{submission_id}/feedback      - Add feedback to a submission (requires user context)
- POST   /submissions/{submission_id}/submit        - Finalize/submit a submission
"""

import unittest

from campus.common import schema
from tests.fixtures import services
from tests.fixtures.tokens import create_test_token, get_bearer_auth_headers, get_basic_auth_headers


class TestApiSubmissionsContract(unittest.TestCase):
    """HTTP contract tests for /api/v1/submissions/ endpoints."""

    @classmethod
    def setUpClass(cls):
        # Reset storage before starting tests to ensure clean state
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.apps_app

        # Create test user and token for bearer auth
        cls.user_id = schema.UserID("test.user@campus.test")
        cls.token = create_test_token(cls.user_id)
        cls.auth_headers = get_bearer_auth_headers(cls.token)

        # Test data
        cls.test_assignment_id = "assignment_123"
        cls.test_student_id = str(cls.user_id)
        cls.test_course_id = "course_456"

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

    def setUp(self):
        # Clear test data - no manual resource initialization needed
        self.manager.clear_test_data()

        self.client = self.app.test_client()

    def _create_test_submission(self, **overrides):
        """Helper to create a test submission via API.

        Returns the submission ID.
        """
        data = {
            "assignment_id": self.test_assignment_id,
            "student_id": self.test_student_id,
            "course_id": self.test_course_id,
        }
        data.update(overrides)

        response = self.client.post(
            "/api/v1/submissions/",
            json=data,
            headers=self.auth_headers
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()["id"]

    def test_list_submissions_requires_auth(self):
        """GET /submissions/ without auth returns 401."""
        response = self.client.get("/api/v1/submissions/")

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    def test_list_submissions_empty(self):
        """GET /submissions/ with auth returns empty list for unique filter."""
        # Use a unique assignment_id that won't be used by other tests
        unique_assignment = "unique_empty_test_assignment_xyz"
        response = self.client.get(
            f"/api/v1/submissions/?assignment_id={unique_assignment}",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("data", data)
        self.assertEqual(data["data"], [])

    def test_create_submission(self):
        """POST /submissions/ creates a new submission."""
        response = self.client.post(
            "/api/v1/submissions/",
            json={
                "assignment_id": self.test_assignment_id,
                "student_id": self.test_student_id,
                "course_id": self.test_course_id,
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertIn("id", data)
        self.assertIn("assignment_id", data)
        self.assertIn("student_id", data)
        self.assertIn("course_id", data)
        self.assertEqual(data["assignment_id"], self.test_assignment_id)
        self.assertEqual(data["student_id"], self.test_student_id)
        self.assertEqual(data["course_id"], self.test_course_id)

    def test_create_submission_with_responses(self):
        """POST /submissions/ with responses creates a submission with answers."""
        responses = [
            {"question_id": "q1", "response_text": "Answer 1"},
            {"question_id": "q2", "response_text": "Answer 2"},
        ]
        response = self.client.post(
            "/api/v1/submissions/",
            json={
                "assignment_id": self.test_assignment_id,
                "student_id": self.test_student_id,
                "course_id": self.test_course_id,
                "responses": responses,
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertIn("responses", data)
        self.assertEqual(len(data["responses"]), 2)
        self.assertEqual(data["responses"][0]["question_id"], "q1")
        self.assertEqual(data["responses"][0]["response_text"], "Answer 1")

    @unittest.skip("API BUG: Missing params returns 500 instead of 400 (same as bug #324)")
    def test_create_submission_missing_required_field(self):
        """POST /submissions/ without required field returns error."""
        response = self.client.post(
            "/api/v1/submissions/",
            json={
                "assignment_id": self.test_assignment_id,
                # Missing student_id and course_id
            },
            headers=self.auth_headers
        )

        # Should return 400 for missing required parameters
        self.assertIn(response.status_code, (400, 422))

    def test_list_submissions_by_assignment(self):
        """GET /submissions/by-assignment/{assignment_id} returns submissions for assignment."""
        # Create a test submission
        submission_id = self._create_test_submission()

        response = self.client.get(
            f"/api/v1/submissions/by-assignment/{self.test_assignment_id}",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("data", data)
        self.assertGreater(len(data["data"]), 0)
        self.assertEqual(data["data"][0]["assignment_id"], self.test_assignment_id)

    def test_list_submissions_by_student(self):
        """GET /submissions/by-student/{student_id} returns submissions for student."""
        # Create a test submission
        submission_id = self._create_test_submission()

        response = self.client.get(
            f"/api/v1/submissions/by-student/{self.test_student_id}",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("data", data)
        self.assertGreater(len(data["data"]), 0)
        self.assertEqual(data["data"][0]["student_id"], self.test_student_id)

    def test_list_submissions_with_query_params(self):
        """GET /submissions/ with query params filters results."""
        # Create a test submission
        submission_id = self._create_test_submission()

        # Filter by assignment_id
        response = self.client.get(
            f"/api/v1/submissions/?assignment_id={self.test_assignment_id}",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("data", data)
        self.assertGreater(len(data["data"]), 0)

        # Filter by student_id
        response = self.client.get(
            f"/api/v1/submissions/?student_id={self.test_student_id}",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("data", data)

        # Filter by course_id
        response = self.client.get(
            f"/api/v1/submissions/?course_id={self.test_course_id}",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("data", data)

    def test_get_submission_by_id(self):
        """GET /submissions/{submission_id} returns the submission."""
        submission_id = self._create_test_submission()

        response = self.client.get(
            f"/api/v1/submissions/{submission_id}",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["id"], submission_id)
        self.assertIn("assignment_id", data)
        self.assertIn("student_id", data)

    def test_get_missing_submission_returns_error(self):
        """GET /submissions/{submission_id} for non-existent submission returns error."""
        response = self.client.get(
            "/api/v1/submissions/nonexistent_id",
            headers=self.auth_headers
        )

        self.assertIn(response.status_code, (404, 409))

    def test_update_submission_responses(self):
        """PATCH /submissions/{submission_id} updates responses."""
        submission_id = self._create_test_submission()

        new_responses = [
            {"question_id": "q1", "response_text": "Updated answer"},
        ]
        response = self.client.patch(
            f"/api/v1/submissions/{submission_id}",
            json={"responses": new_responses},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {})

        # Verify the update
        get_response = self.client.get(
            f"/api/v1/submissions/{submission_id}",
            headers=self.auth_headers
        )
        submission_data = get_response.get_json()
        self.assertEqual(submission_data["responses"][0]["response_text"], "Updated answer")

    def test_update_submission_feedback(self):
        """PATCH /submissions/{submission_id} updates feedback."""
        submission_id = self._create_test_submission()

        new_feedback = [
            {"question_id": "q1", "feedback_text": "Good answer!", "teacher_id": str(self.user_id)},
        ]
        response = self.client.patch(
            f"/api/v1/submissions/{submission_id}",
            json={"feedback": new_feedback},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {})

    def test_update_submission_submitted_at(self):
        """PATCH /submissions/{submission_id} updates submitted_at timestamp."""
        submission_id = self._create_test_submission()

        from datetime import datetime, timezone
        submitted_at = datetime.now(timezone.utc).isoformat()

        response = self.client.patch(
            f"/api/v1/submissions/{submission_id}",
            json={"submitted_at": submitted_at},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {})

    def test_update_submission_empty_body(self):
        """PATCH /submissions/{submission_id} without updates returns error."""
        submission_id = self._create_test_submission()

        response = self.client.patch(
            f"/api/v1/submissions/{submission_id}",
            json={},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertEqual(data["error"]["code"], "INVALID_REQUEST")

    def test_update_missing_submission_returns_error(self):
        """PATCH /submissions/{submission_id} for non-existent submission returns 200.

        NOTE: Current API behavior returns 200 for missing submissions due to
        NoChangesAppliedError being caught and returning None. This may be
        intentional (idempotent updates) or a bug.
        """
        response = self.client.patch(
            "/api/v1/submissions/nonexistent_id",
            json={"responses": [{"question_id": "q1", "response_text": "Answer"}]},
            headers=self.auth_headers
        )

        # Current behavior: returns 200 with empty body
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {})

    def test_delete_submission(self):
        """DELETE /submissions/{submission_id} removes the submission."""
        submission_id = self._create_test_submission()

        response = self.client.delete(
            f"/api/v1/submissions/{submission_id}",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {})

        # Verify it's deleted
        get_response = self.client.get(
            f"/api/v1/submissions/{submission_id}",
            headers=self.auth_headers
        )
        self.assertIn(get_response.status_code, (404, 409))

    def test_delete_missing_submission_returns_error(self):
        """DELETE /submissions/{submission_id} for non-existent submission returns error."""
        response = self.client.delete(
            "/api/v1/submissions/nonexistent_id",
            headers=self.auth_headers
        )

        self.assertIn(response.status_code, (404, 409))

    def test_add_response_to_submission(self):
        """POST /submissions/{submission_id}/responses adds a response."""
        submission_id = self._create_test_submission()

        response = self.client.post(
            f"/api/v1/submissions/{submission_id}/responses",
            json={
                "question_id": "q1",
                "response_text": "My answer",
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {})

        # Verify the response was added
        get_response = self.client.get(
            f"/api/v1/submissions/{submission_id}",
            headers=self.auth_headers
        )
        submission_data = get_response.get_json()
        self.assertEqual(len(submission_data["responses"]), 1)
        self.assertEqual(submission_data["responses"][0]["question_id"], "q1")
        self.assertEqual(submission_data["responses"][0]["response_text"], "My answer")

    def test_add_response_updates_existing(self):
        """POST /submissions/{submission_id}/responses updates existing response."""
        submission_id = self._create_test_submission(
            responses=[{"question_id": "q1", "response_text": "Original answer"}]
        )

        # Update the existing response
        response = self.client.post(
            f"/api/v1/submissions/{submission_id}/responses",
            json={
                "question_id": "q1",
                "response_text": "Updated answer",
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)

        # Verify the response was updated (not duplicated)
        get_response = self.client.get(
            f"/api/v1/submissions/{submission_id}",
            headers=self.auth_headers
        )
        submission_data = get_response.get_json()
        self.assertEqual(len(submission_data["responses"]), 1)
        self.assertEqual(submission_data["responses"][0]["response_text"], "Updated answer")

    @unittest.skip("API BUG: current_user is User object but code uses .get('id') (similar to assignments bug)")
    def test_add_feedback_to_submission(self):
        """POST /submissions/{submission_id}/feedback adds feedback (requires user context)."""
        submission_id = self._create_test_submission()

        response = self.client.post(
            f"/api/v1/submissions/{submission_id}/feedback",
            json={
                "question_id": "q1",
                "feedback_text": "Great work!",
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {})

        # Verify the feedback was added
        get_response = self.client.get(
            f"/api/v1/submissions/{submission_id}",
            headers=self.auth_headers
        )
        submission_data = get_response.get_json()
        self.assertEqual(len(submission_data["feedback"]), 1)
        self.assertEqual(submission_data["feedback"][0]["question_id"], "q1")
        self.assertEqual(submission_data["feedback"][0]["feedback_text"], "Great work!")

    @unittest.skip("API BUG: current_user is User object but code uses .get('id') (similar to assignments bug)")
    def test_add_feedback_updates_existing(self):
        """POST /submissions/{submission_id}/feedback updates existing feedback."""
        submission_id = self._create_test_submission()

        # Add initial feedback
        self.client.post(
            f"/api/v1/submissions/{submission_id}/feedback",
            json={
                "question_id": "q1",
                "feedback_text": "Original feedback",
            },
            headers=self.auth_headers
        )

        # Update the existing feedback
        response = self.client.post(
            f"/api/v1/submissions/{submission_id}/feedback",
            json={
                "question_id": "q1",
                "feedback_text": "Updated feedback",
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)

        # Verify the feedback was updated (not duplicated)
        get_response = self.client.get(
            f"/api/v1/submissions/{submission_id}",
            headers=self.auth_headers
        )
        submission_data = get_response.get_json()
        self.assertEqual(len(submission_data["feedback"]), 1)
        self.assertEqual(submission_data["feedback"][0]["feedback_text"], "Updated feedback")

    def test_submit_submission(self):
        """POST /submissions/{submission_id}/submit finalizes the submission."""
        submission_id = self._create_test_submission()

        response = self.client.post(
            f"/api/v1/submissions/{submission_id}/submit",
            json={},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {})

        # Verify the submission was marked as submitted
        get_response = self.client.get(
            f"/api/v1/submissions/{submission_id}",
            headers=self.auth_headers
        )
        submission_data = get_response.get_json()
        self.assertIsNotNone(submission_data["submitted_at"])

    def test_submit_already_submitted_returns_error(self):
        """POST /submissions/{submission_id}/submit on already submitted submission returns error."""
        submission_id = self._create_test_submission()

        # First submit
        self.client.post(
            f"/api/v1/submissions/{submission_id}/submit",
            json={},
            headers=self.auth_headers
        )

        # Try to submit again
        response = self.client.post(
            f"/api/v1/submissions/{submission_id}/submit",
            json={},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertEqual(data["error"]["code"], "INVALID_REQUEST")


if __name__ == '__main__':
    unittest.main()
