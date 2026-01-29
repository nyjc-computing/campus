"""Unit tests for Assignment model."""

import unittest

from campus.model import Assignment, ClassroomLink, Question
from campus.common import schema


class TestQuestion(unittest.TestCase):
    """Tests for the Question dataclass."""

    def test_question_level_top(self):
        """Top-level question should have level 1."""
        q = Question(id="q1", prompt="P", question="Q?")
        self.assertEqual(q.level, 1)

    def test_question_level_part(self):
        """Part question should have level 2."""
        q = Question(id="q1.a", prompt="", question="Q?")
        self.assertEqual(q.level, 2)

    def test_question_level_subpart(self):
        """Subpart question should have level 3."""
        q = Question(id="q1.a.i", prompt="", question="Q?")
        self.assertEqual(q.level, 3)

    def test_question_level_deep(self):
        """Deeply nested question should have correct level."""
        q = Question(id="q1.a.i.1", prompt="", question="Q?")
        self.assertEqual(q.level, 4)

    def test_parent_id_top_level(self):
        """Top-level question should have no parent."""
        q = Question(id="q1", prompt="P", question="Q?")
        self.assertIsNone(q.parent_id)

    def test_parent_id_part(self):
        """Part question parent should be root."""
        q = Question(id="q1.a", prompt="", question="Q?")
        self.assertEqual(q.parent_id, "q1")

    def test_parent_id_subpart(self):
        """Subpart question parent should be part."""
        q = Question(id="q1.a.i", prompt="", question="Q?")
        self.assertEqual(q.parent_id, "q1.a")

    def test_root_id(self):
        """All questions should have same root."""
        q1 = Question(id="q1", prompt="P", question="Q?")
        q1a = Question(id="q1.a", prompt="", question="Q?")
        q1ai = Question(id="q1.a.i", prompt="", question="Q?")
        q2 = Question(id="q2", prompt="", question="Q?")

        self.assertEqual(q1.root_id, "q1")
        self.assertEqual(q1a.root_id, "q1")
        self.assertEqual(q1ai.root_id, "q1")
        self.assertEqual(q2.root_id, "q2")


class TestClassroomLink(unittest.TestCase):
    """Tests for the ClassroomLink dataclass."""

    def test_classroom_link_creation(self):
        """ClassroomLink should create with all fields."""
        link = ClassroomLink(
            course_id="course123",
            coursework_id="work456",
            attachment_id="attach789"
        )
        self.assertEqual(link.course_id, "course123")
        self.assertEqual(link.coursework_id, "work456")
        self.assertEqual(link.attachment_id, "attach789")

    def test_classroom_link_without_attachment(self):
        """ClassroomLink can be created without attachment_id."""
        link = ClassroomLink(
            course_id="course123",
            coursework_id="work456"
        )
        self.assertEqual(link.course_id, "course123")
        self.assertEqual(link.coursework_id, "work456")
        self.assertIsNone(link.attachment_id)

    def test_classroom_link_linked_at_defaults(self):
        """linked_at should default to current time."""
        link = ClassroomLink(
            course_id="course123",
            coursework_id="work456"
        )
        self.assertIsNotNone(link.linked_at)


class TestAssignment(unittest.TestCase):
    """Tests for the Assignment model."""

    def test_assignment_creation(self):
        """Assignment should create with all required fields."""
        assignment = Assignment(
            id=schema.CampusID("assignment_test12345"),
            title="Test Assignment",
            description="A test assignment",
            created_by="teacher@example.com"
        )
        self.assertEqual(assignment.title, "Test Assignment")
        self.assertEqual(assignment.description, "A test assignment")
        self.assertEqual(assignment.questions, [])
        self.assertEqual(assignment.classroom_links, [])
        self.assertEqual(assignment.created_by, "teacher@example.com")

    def test_assignment_with_questions(self):
        """Assignment can contain multiple questions."""
        questions = [
            Question(id="q1", prompt="Read...", question="What?"),
            Question(id="q1.a", prompt="", question="Explain..."),
            Question(id="q2", prompt="Consider...", question="Analyze...")
        ]
        assignment = Assignment(
            id=schema.CampusID("assignment_test12345"),
            title="Test",
            created_by="teacher@example.com",
            questions=questions
        )
        self.assertEqual(len(assignment.questions), 3)
        self.assertEqual(assignment.questions[0].id, "q1")
        self.assertEqual(assignment.questions[1].id, "q1.a")

    def test_assignment_with_classroom_links(self):
        """Assignment can have multiple Classroom links."""
        links = [
            ClassroomLink(course_id="c1", coursework_id="w1"),
            ClassroomLink(course_id="c2", coursework_id="w2")
        ]
        assignment = Assignment(
            id=schema.CampusID("assignment_test12345"),
            title="Test",
            created_by="teacher@example.com",
            classroom_links=links
        )
        self.assertEqual(len(assignment.classroom_links), 2)
        self.assertEqual(assignment.classroom_links[0].course_id, "c1")

    def test_get_question(self):
        """get_question should find question by ID."""
        questions = [
            Question(id="q1", prompt="P1", question="Q1?"),
            Question(id="q1.a", prompt="", question="Q1a?"),
        ]
        assignment = Assignment(
            id=schema.CampusID("assignment_test12345"),
            title="Test",
            created_by="teacher@example.com",
            questions=questions
        )

        self.assertIsNotNone(assignment.get_question("q1"))
        self.assertEqual(assignment.get_question("q1").question, "Q1?")
        self.assertIsNotNone(assignment.get_question("q1.a"))
        self.assertIsNone(assignment.get_question("q2"))

    def test_get_question_tree(self):
        """get_question_tree should return nested structure."""
        questions = [
            Question(id="q1", prompt="P1", question="Q1?"),
            Question(id="q1.a", prompt="", question="Q1a?"),
            Question(id="q1.a.i", prompt="", question="Q1ai?"),
            Question(id="q2", prompt="P2", question="Q2?"),
        ]
        assignment = Assignment(
            id=schema.CampusID("assignment_test12345"),
            title="Test",
            created_by="teacher@example.com",
            questions=questions
        )

        tree = assignment.get_question_tree()
        self.assertIn("q1", tree)
        self.assertIn("q2", tree)
        self.assertEqual(len(tree["q1"]["children"]), 1)
        self.assertEqual(tree["q1"]["children"][0]["id"], "q1.a")

    def test_get_questions_for_root(self):
        """get_questions_for_root should return root and all descendants."""
        questions = [
            Question(id="q1", prompt="P1", question="Q1?"),
            Question(id="q1.a", prompt="", question="Q1a?"),
            Question(id="q1.a.i", prompt="", question="Q1ai?"),
            Question(id="q2", prompt="P2", question="Q2?"),
        ]
        assignment = Assignment(
            id=schema.CampusID("assignment_test12345"),
            title="Test",
            created_by="teacher@example.com",
            questions=questions
        )

        q1_questions = assignment.get_questions_for_root("q1")
        self.assertEqual(len(q1_questions), 3)
        q1_ids = [q.id for q in q1_questions]
        self.assertIn("q1", q1_ids)
        self.assertIn("q1.a", q1_ids)
        self.assertIn("q1.a.i", q1_ids)
        self.assertNotIn("q2", q1_ids)

    def test_to_resource(self):
        """to_resource should convert to dict."""
        assignment = Assignment(
            id=schema.CampusID("assignment_test12345"),
            title="Test",
            description="Desc",
            created_by="teacher@example.com",
            questions=[Question(id="q1", prompt="P", question="Q?")]
        )
        resource = assignment.to_resource()
        self.assertEqual(resource["title"], "Test")
        self.assertEqual(resource["created_by"], "teacher@example.com")
        self.assertIsInstance(resource["questions"], list)

    def test_to_storage(self):
        """to_storage should convert to dict for database."""
        assignment = Assignment(
            id=schema.CampusID("assignment_test12345"),
            title="Test",
            created_by="teacher@example.com",
            questions=[Question(id="q1", prompt="P", question="Q?")]
        )
        storage = assignment.to_storage()
        self.assertEqual(storage["title"], "Test")
        self.assertEqual(storage["created_by"], "teacher@example.com")
        self.assertIsInstance(storage["questions"], list)


if __name__ == '__main__':
    unittest.main()
