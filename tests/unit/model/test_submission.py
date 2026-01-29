"""Unit tests for Submission model."""

import unittest

from campus.model.submission import Submission, Response, Feedback
from campus.common import schema


class TestResponse(unittest.TestCase):
    """Tests for the Response dataclass."""

    def test_response_creation(self):
        """Response should create with question_id and response_text."""
        response = Response(
            question_id="q1",
            response_text="This is my answer"
        )
        self.assertEqual(response.question_id, "q1")
        self.assertEqual(response.response_text, "This is my answer")

    def test_response_with_nested_question_id(self):
        """Response should work with hierarchical question IDs."""
        response = Response(
            question_id="q1.a.i",
            response_text="Nested answer"
        )
        self.assertEqual(response.question_id, "q1.a.i")

    def test_response_with_empty_text(self):
        """Response can have empty response_text."""
        response = Response(
            question_id="q1",
            response_text=""
        )
        self.assertEqual(response.response_text, "")


class TestFeedback(unittest.TestCase):
    """Tests for the Feedback dataclass."""

    def test_feedback_creation(self):
        """Feedback should create with required fields."""
        feedback = Feedback(
            question_id="q1",
            feedback_text="Good work!",
            teacher_id=schema.UserID("teacher@example.com")
        )
        self.assertEqual(feedback.question_id, "q1")
        self.assertEqual(feedback.feedback_text, "Good work!")
        self.assertEqual(feedback.teacher_id, "teacher@example.com")

    def test_feedback_created_at_defaults(self):
        """created_at should default to current time."""
        feedback = Feedback(
            question_id="q1",
            feedback_text="Feedback",
            teacher_id=schema.UserID("teacher@example.com")
        )
        self.assertIsNotNone(feedback.created_at)
        self.assertIsInstance(feedback.created_at, schema.DateTime)

    def test_feedback_with_nested_question_id(self):
        """Feedback should work with hierarchical question IDs."""
        feedback = Feedback(
            question_id="q1.a.i",
            feedback_text="Excellent analysis",
            teacher_id=schema.UserID("teacher@example.com")
        )
        self.assertEqual(feedback.question_id, "q1.a.i")


class TestSubmission(unittest.TestCase):
    """Tests for the Submission model."""

    def test_submission_creation(self):
        """Submission should create with required fields."""
        submission = Submission(
            id=schema.CampusID("submission_test12"),
            assignment_id=schema.CampusID("assignment_test12"),
            student_id=schema.UserID("student@example.com"),
            course_id="course123"
        )
        self.assertEqual(submission.id, "submission_test12")
        self.assertEqual(submission.assignment_id, "assignment_test12")
        self.assertEqual(submission.student_id, "student@example.com")
        self.assertEqual(submission.course_id, "course123")
        self.assertEqual(submission.responses, [])
        self.assertEqual(submission.feedback, [])
        self.assertIsNone(submission.submitted_at)

    def test_submission_with_responses(self):
        """Submission can contain multiple responses."""
        responses = [
            Response(question_id="q1", response_text="Answer 1"),
            Response(question_id="q1.a", response_text="Answer 1a"),
        ]
        submission = Submission(
            id=schema.CampusID("submission_test12"),
            assignment_id=schema.CampusID("assignment_test12"),
            student_id=schema.UserID("student@example.com"),
            course_id="course123",
            responses=responses
        )
        self.assertEqual(len(submission.responses), 2)
        self.assertEqual(submission.responses[0].question_id, "q1")

    def test_submission_with_feedback(self):
        """Submission can contain multiple feedback items."""
        feedback = [
            Feedback(
                question_id="q1",
                feedback_text="Good",
                teacher_id=schema.UserID("teacher@example.com")
            ),
            Feedback(
                question_id="q1.a",
                feedback_text="Excellent",
                teacher_id=schema.UserID("teacher@example.com")
            ),
        ]
        submission = Submission(
            id=schema.CampusID("submission_test12"),
            assignment_id=schema.CampusID("assignment_test12"),
            student_id=schema.UserID("student@example.com"),
            course_id="course123",
            feedback=feedback
        )
        self.assertEqual(len(submission.feedback), 2)
        self.assertEqual(submission.feedback[0].question_id, "q1")

    def test_submission_with_submitted_at(self):
        """Submission can have submitted_at timestamp."""
        now = schema.DateTime.utcnow()
        submission = Submission(
            id=schema.CampusID("submission_test12"),
            assignment_id=schema.CampusID("assignment_test12"),
            student_id=schema.UserID("student@example.com"),
            course_id="course123",
            submitted_at=now
        )
        self.assertEqual(submission.submitted_at, now)

    def test_submission_created_at_defaults(self):
        """created_at should default to current time."""
        submission = Submission(
            id=schema.CampusID("submission_test12"),
            assignment_id=schema.CampusID("assignment_test12"),
            student_id=schema.UserID("student@example.com"),
            course_id="course123"
        )
        self.assertIsNotNone(submission.created_at)
        self.assertIsInstance(submission.created_at, schema.DateTime)

    def test_submission_updated_at_defaults(self):
        """updated_at should default to current time."""
        submission = Submission(
            id=schema.CampusID("submission_test12"),
            assignment_id=schema.CampusID("assignment_test12"),
            student_id=schema.UserID("student@example.com"),
            course_id="course123"
        )
        self.assertIsNotNone(submission.updated_at)
        self.assertIsInstance(submission.updated_at, schema.DateTime)

    def test_submission_to_resource(self):
        """to_resource() should convert Submission to dict."""
        response = Response(question_id="q1", response_text="Answer")
        feedback = Feedback(
            question_id="q1",
            feedback_text="Good",
            teacher_id=schema.UserID("teacher@example.com")
        )
        submission = Submission(
            id=schema.CampusID("submission_test12"),
            assignment_id=schema.CampusID("assignment_test12"),
            student_id=schema.UserID("student@example.com"),
            course_id="course123",
            responses=[response],
            feedback=[feedback]
        )

        resource = submission.to_resource()
        self.assertEqual(resource["id"], "submission_test12")
        self.assertEqual(resource["assignment_id"], "assignment_test12")
        self.assertEqual(resource["student_id"], "student@example.com")
        self.assertEqual(resource["course_id"], "course123")
        self.assertEqual(len(resource["responses"]), 1)
        self.assertEqual(len(resource["feedback"]), 1)
        self.assertIsNone(resource["submitted_at"])

    def test_submission_to_storage(self):
        """to_storage() should convert Submission with nested objects to dict."""
        response = Response(question_id="q1", response_text="Answer")
        feedback = Feedback(
            question_id="q1",
            feedback_text="Good",
            teacher_id=schema.UserID("teacher@example.com")
        )
        submission = Submission(
            id=schema.CampusID("submission_test12"),
            assignment_id=schema.CampusID("assignment_test12"),
            student_id=schema.UserID("student@example.com"),
            course_id="course123",
            responses=[response],
            feedback=[feedback]
        )

        storage = submission.to_storage()
        self.assertEqual(storage["id"], "submission_test12")
        # Nested objects should be converted to dicts
        self.assertIsInstance(storage["responses"], list)
        self.assertIsInstance(storage["responses"][0], dict)
        self.assertEqual(storage["responses"][0]["question_id"], "q1")
        self.assertIsInstance(storage["feedback"], list)
        self.assertIsInstance(storage["feedback"][0], dict)
        self.assertEqual(storage["feedback"][0]["question_id"], "q1")

    def test_submission_from_resource(self):
        """from_resource() should create Submission from dict."""
        resource = {
            "id": "submission_test12",
            "created_at": schema.DateTime.utcnow(),
            "assignment_id": "assignment_test12",
            "student_id": "student@example.com",
            "course_id": "course123",
            "responses": [
                {"question_id": "q1", "response_text": "Answer"}
            ],
            "feedback": [
                {
                    "question_id": "q1",
                    "feedback_text": "Good",
                    "teacher_id": "teacher@example.com",
                    "created_at": schema.DateTime.utcnow()
                }
            ],
            "submitted_at": None,
            "updated_at": schema.DateTime.utcnow(),
        }

        submission = Submission.from_resource(resource)
        self.assertEqual(submission.id, "submission_test12")
        self.assertEqual(submission.assignment_id, "assignment_test12")
        self.assertEqual(len(submission.responses), 1)
        self.assertIsInstance(submission.responses[0], Response)
        self.assertEqual(len(submission.feedback), 1)
        self.assertIsInstance(submission.feedback[0], Feedback)


if __name__ == '__main__':
    unittest.main()
